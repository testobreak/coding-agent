# editing/symbol_editor.py
#
# SymbolEditor orchestrates AST-backed symbol edits and validation checks.

import os
from editing.ast_locator import ASTLocator, ASTNodeInfo
from editing.patch_generator import PatchGenerator
from editing.patch_applier import PatchApplier
from editing.edit_transaction import EditTransaction
from editing.symbol_handle import SymbolHandle
from editing.patch import Patch
from editing.symbol_resolver import SymbolResolver
from context.assembler import ContextAssembler
from context.prompt_builder import PromptBuilder

class SymbolEditor:
    def __init__(
        self,
        file_manager,
        state_manager,
        git_manager,
        validator,
        compile_validator,
        test_runner,
        impact_analyzer,
        retrieval_pipeline,
        llm=None
    ):
        self.file_manager = file_manager
        self.state_manager = state_manager
        self.git = git_manager
        self.validator = validator
        self.compile_validator = compile_validator
        self.tests = test_runner
        self.impact_analyzer = impact_analyzer
        self.retrieval_pipeline = retrieval_pipeline
        
        self.resolver = SymbolResolver()
        self.ast_locator = ASTLocator()
        self.patch_generator = PatchGenerator(llm=llm)
        self.patch_applier = PatchApplier()
        
        self.context_assembler = ContextAssembler()
        self.prompt_builder = PromptBuilder()

    def _get_dependencies_context(self, symbol_fqn: str) -> list[str]:
        dependencies = []
        try:
            from repository_intelligence.db.connection import SessionLocal
            from repository_intelligence.models.symbol import Symbol, SymbolRelationship
        except ImportError:
            return dependencies
        
        session = SessionLocal()
        try:
            # Find the symbol in DB
            db_symbol = session.query(Symbol).filter(
                (Symbol.name == symbol_fqn) | (Symbol.qualified_name == symbol_fqn)
            ).first()
            
            if db_symbol:
                # Find callers (source_symbol_id where target is this symbol)
                relations = session.query(SymbolRelationship).filter(
                    (SymbolRelationship.target_symbol_id == db_symbol.id) |
                    (SymbolRelationship.target_name == db_symbol.name)
                ).limit(5).all()
                
                for rel in relations:
                    if rel.source_symbol_id:
                        caller_sym = session.query(Symbol).filter(Symbol.id == rel.source_symbol_id).first()
                        if caller_sym:
                            snippet = f"// Called by: {caller_sym.name} ({caller_sym.symbol_type}) in {caller_sym.file_path}"
                            if caller_sym.signature:
                                snippet += f"\nSignature: {caller_sym.signature}"
                            dependencies.append(snippet)
        except Exception as e:
            print(f"[SymbolEditor] Warning: Failed fetching dependencies context: {e}")
        finally:
            session.close()
        return dependencies

    def edit(self, symbol: SymbolHandle, instruction: str, operation: str = "modify_symbol") -> Patch:
        """
        Surgically extracts symbol from file, prompts LLM for modifications,
        and constructs a Patch object. Does not write to disk.
        """
        print(f"[SymbolEditor] Surgical edit ({operation}) on symbol: {symbol.fqn} ({symbol.file_path})")
        
        # 1. Read current file content
        original_content = self.file_manager.read_file(symbol.file_path)
        if original_content is None:
            raise RuntimeError(f"Could not read file: {symbol.file_path}")
            
        resolved_file_path = self.file_manager.resolve_path(symbol.file_path)
        
        # 2. Locate AST node for symbol
        symbol_info = self.ast_locator.find_symbol(resolved_file_path, symbol.fqn, original_content)
        
        if not symbol_info:
            print(f"[SymbolEditor] Warning: AST locator could not locate symbol. Falling back to handle boundaries.")
            lines = original_content.splitlines()
            start_idx = max(0, symbol.start_line - 1)
            end_idx = min(len(lines), symbol.end_line)
            content_snippet = "\n".join(lines[start_idx:end_idx])
            start_byte = sum(len(l) + 1 for l in lines[:start_idx])
            end_byte = start_byte + len(content_snippet)
            
            symbol_info = ASTNodeInfo(
                node_type=symbol.kind,
                name=symbol.fqn,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                start_byte=start_byte,
                end_byte=end_byte,
                content=content_snippet
            )
            
        # 3. Fetch dependencies context
        dependencies_ctx = self._get_dependencies_context(symbol.fqn)
        
        # 4. Construct SymbolEditRequest
        from editing.symbol_edit_request import SymbolEditRequest
        edit_req = SymbolEditRequest(
            symbol_id=symbol.symbol_id,
            qualified_name=symbol.fqn,
            current_source=symbol_info.content,
            goal=instruction,
            dependencies=dependencies_ctx
        )
        
        # 5. Assemble prompt context and generate search-replace patch string
        state = self.state_manager.get_state()
        context = self.context_assembler.build(state)
        execution_context = self.prompt_builder.build_execution_prompt(context)
        
        # We can construct structured instruction based on operation type
        enhanced_instruction = instruction
        if operation == "create_symbol":
            enhanced_instruction = f"CREATE SYMBOL OPERATION:\nAdd the new symbol/method defined by this instruction to the parent symbol:\n{instruction}"
        elif operation == "rename_symbol":
            enhanced_instruction = f"RENAME SYMBOL OPERATION:\nRename this symbol according to the instruction:\n{instruction}"
            
        patch_str = self.patch_generator.generate_patch(
            symbol_info=symbol_info,
            instruction=enhanced_instruction,
            file_path=symbol.file_path,
            execution_context=execution_context,
            edit_request=edit_req
        )
        
        # Parse the new text from patch_str
        modified_content = self.patch_applier.apply(original_content, patch_str, symbol_info)
        
        # Extract new_text specifically for the symbol boundaries
        # For simplicity and correctness, the Patch holds old_text as symbol_info.content
        # and new_text as the replacement or search/replace block
        return Patch(
            symbol_fqn=symbol.fqn,
            file_path=symbol.file_path,
            old_text=symbol_info.content,
            new_text=modified_content,
            patch_block=patch_str
        )

    def apply_patch(self, patch: Patch) -> bool:
        """
        Applies a Patch, runs syntax, compilation, and test suite validations,
        and commits or rolls back changes inside a transaction boundary.
        """
        resolved_file_path = self.file_manager.resolve_path(patch.file_path)
        
        # Initialize Transaction boundary
        tx = EditTransaction(
            git_manager=self.git,
            state_manager=self.state_manager,
            goal=f"Modify symbol {patch.symbol_fqn} in {patch.file_path}"
        )
        tx.begin()
        
        success = False
        try:
            # 1. Apply patch content and write to disk
            print(f"[SymbolEditor] Applying patch to {patch.file_path}...")
            self.file_manager.write_file(patch.file_path, patch.new_text)
            tx.modified_files.append(patch.file_path)
            tx.save_to_db()
            
            # 2. Syntax validation
            print(f"[SymbolEditor] Validating file syntax...")
            try:
                self.validator.validate_file_syntax(resolved_file_path)
            except Exception as e:
                raise RuntimeError(f"Syntax validation failed: {e}")
            self.state_manager.increment_validations()
            
            # 3. Compile validation
            print(f"[SymbolEditor] Validating compilation...")
            try:
                self.compile_validator.validate(resolved_file_path)
            except Exception as e:
                raise RuntimeError(f"Compilation validation failed: {e}")
            
            # 4. Run tests
            print(f"[SymbolEditor] Running test verification...")
            test_filter = None
            try:
                dep_graph = getattr(self.retrieval_pipeline.retriever, "dependency_graph", None)
                if dep_graph and dep_graph._built:
                    self.impact_analyzer.graph = dep_graph
                impact = self.impact_analyzer.analyze(patch.file_path)
                test_filter = impact.get("test_filter")
                if test_filter:
                    print(f"[ImpactAnalyzer] Targeted tests: {test_filter}")
            except Exception as e:
                print(f"[ImpactAnalyzer] Dependency impact resolution skipped: {e}")
                
            test_result = self.tests.run_backend_tests(test_filter=test_filter)
            if not test_result.get("success", False):
                failures = test_result.get("failures", [])
                if hasattr(self.state_manager, "add_test_failure"):
                    for f in failures:
                        self.state_manager.add_test_failure(f)
                failure_summary = "; ".join([f"{f.get('error_type')}: {f.get('message')}" for f in failures[:3]]) or "Backend test failure"
                raise RuntimeError(f"Test suite validation failed: {failure_summary}")
                
            # Commit changes on validation success
            tx.commit()
            success = True
            
        except Exception as err:
            validation_error = str(err)
            print(f"[SymbolEditor] Validation failed, rolling back: {validation_error}")
            tx.rollback(reason=validation_error)
            raise
            
        # Update metrics and memory state
        state = self.state_manager.get_state()
        if success:
            if hasattr(state, "modified_files"):
                if state.modified_files is None:
                    state.modified_files = []
                if patch.file_path not in state.modified_files:
                    state.modified_files.append(patch.file_path)
            if hasattr(state, "generated_code"):
                if state.generated_code is None:
                    state.generated_code = []
                state.generated_code.append({
                    "path": patch.file_path,
                    "content": patch.new_text
                })
            self.state_manager.increment_modifications()
            
        return success

    def modify(self, symbol_name: str, instruction: str, file_path: str = None, operation: str = "modify_symbol") -> dict:
        """
        Orchestrates symbol resolution, decoupled patch editing, and validation end-to-end.
        Keeps compatibility with the existing modify_symbol tool.
        """
        print(f"[SymbolEditor] Decoupled modify flow ({operation}) for: {symbol_name}")
        
        # 1. Resolve to SymbolHandle
        handles = self.resolver.resolve(symbol_name, file_path=file_path)
        if not handles:
            raise RuntimeError(f"Symbol '{symbol_name}' could not be resolved to any file or database record.")
            
        symbol = handles[0]
        
        success = False
        validation_error = None
        patch_str = ""
        
        try:
            if operation == "delete_symbol":
                # Deterministic deletion without LLM
                resolved_file_path = self.file_manager.resolve_path(symbol.file_path)
                original_content = self.file_manager.read_file(symbol.file_path)
                
                # Locate AST node
                symbol_info = self.ast_locator.find_symbol(resolved_file_path, symbol.fqn, original_content)
                if not symbol_info:
                    raise RuntimeError(f"Could not locate AST boundaries for symbol to delete: {symbol.fqn}")
                
                # Delete the byte range
                file_bytes = original_content.encode("utf-8")
                modified_bytes = file_bytes[:symbol_info.start_byte] + file_bytes[symbol_info.end_byte:]
                new_text = modified_bytes.decode("utf-8", errors="replace")
                
                patch = Patch(
                    symbol_fqn=symbol.fqn,
                    file_path=symbol.file_path,
                    old_text=symbol_info.content,
                    new_text=new_text,
                    patch_block=f"// Deleted symbol {symbol.fqn}"
                )
                success = self.apply_patch(patch)
            else:
                # MODIFY_SYMBOL, CREATE_SYMBOL, RENAME_SYMBOL, etc.
                patch = self.edit(symbol, instruction, operation=operation)
                patch_str = patch.patch_block
                
                # Validate and apply patch
                success = self.apply_patch(patch)
            
        except Exception as err:
            validation_error = str(err)
            success = False
            
        result = {
            "success": success,
            "path": symbol.file_path,
            "patch": patch_str
        }
        if validation_error:
            result["error"] = validation_error
        return result
