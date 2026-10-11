# execution/patch_handler.py
import os
from context.context_builder import ContextBuilder
from editing.patch_engine import PatchEngine
from inference.router import TaskType

class PatchHandler:
    """Stateless single-file localized patch handler."""
    
    def __init__(self, runtime):
        self.runtime = runtime

    def handle(self, prompt: str, editor_state, on_progress=None) -> dict:
        if on_progress:
            on_progress("status", "Resolving target context...")

        builder = ContextBuilder(self.runtime.executor.retrieval_pipeline, self.runtime.state_manager)
        
        class MockState:
            def __init__(self, rc):
                self.runtime_context = rc
        mock_state = MockState(editor_state)
        
        planning_context = builder.build_planning_context(prompt, mock_state, mode="inline")
        
        primary_file = None
        if editor_state and getattr(editor_state, "active_file", None):
            primary_file = editor_state.active_file
        elif planning_context.related_files:
            primary_file = planning_context.related_files[0]
        elif planning_context.retrieved_chunks:
            primary_file = planning_context.retrieved_chunks[0].get("file")

        if not primary_file:
            raise RuntimeError("No target file resolved for patch edit.")

        # Determine lines range
        start_line = None
        end_line = None
        symbol_name = None
        
        try:
            original_code = self.runtime.file_manager.read_file(primary_file)
        except Exception:
            original_code = ""

        # Step 1: Active text selection priority
        sel_range = getattr(editor_state, "selection_range", None)
        if sel_range:
            start_line = sel_range[0][0]
            end_line = sel_range[1][0]
        # Step 2: 4-stage EditLocator pipeline to resolve precise EditSpan
        if start_line is None or end_line is None:
            try:
                from context.edit_locator import EditLocator
                from editing.edit_span import EditSpan
                
                state_chunks = planning_context.retrieved_chunks or []
                if not state_chunks and hasattr(self.runtime.executor, "retrieval_pipeline"):
                    retrieved = self.runtime.executor.retrieval_pipeline.retrieve_relevant_chunks(
                        prompt, top_k=5, expand_context=False
                    )
                    state_chunks = [r.get("chunk", r) for r in retrieved]
                
                import re
                words = re.findall(r"\b\w+\b", prompt)
                active_symbols = [
                    w for w in words 
                    if w.lower() not in ["add", "fix", "update", "change", "delete", "remove", "patch", "modify", "logging", "check", "test", "in", "for", "to", "the"]
                ]
                
                locator = EditLocator(
                    embedding_engine=self.runtime.executor.retrieval_pipeline.retriever.embedding_engine,
                    repo_root="."
                )
                
                spans = locator.locate(
                    query=prompt,
                    state_chunks=state_chunks,
                    active_symbols=active_symbols,
                    git_diff_str="",
                    modification_targets=[primary_file]
                )
                
                if spans:
                    top_span = spans[0]
                    s_line = top_span["localized_start_line"]
                    e_line = top_span["localized_end_line"]
                    
                    lines = original_code.splitlines()
                    ctx_start = max(1, s_line - 50)
                    ctx_end = min(len(lines), e_line + 50)
                    surrounding_ctx = "\n".join(lines[ctx_start - 1 : ctx_end])

                    edit_span = EditSpan(
                        file=top_span["file_path"],
                        start_line=s_line,
                        end_line=e_line,
                        surrounding_context=surrounding_ctx,
                        confidence=top_span["score"]
                    )
                    start_line = edit_span.start_line
                    end_line = edit_span.end_line
                    symbol_name = top_span.get("ast_node_name")
                    print(f"[PatchHandler] EditSpan resolved: {edit_span.file} L{edit_span.start_line}-L{edit_span.end_line} (confidence: {edit_span.confidence})")
            except Exception as e:
                print(f"[PatchHandler] EditLocator pipeline failed: {e}. Falling back to default targets.")

        # Step 3: AST/planning context fallback
        if start_line is None or end_line is None:
            if planning_context.primary_symbol:
                start_line = planning_context.primary_symbol.start_line
                end_line = planning_context.primary_symbol.end_line
                symbol_name = planning_context.primary_symbol.fqn
            elif primary_file:
                try:
                    import re
                    from editing.ast_locator import ASTLocator
                    ast_loc = ASTLocator()
                    words = re.findall(r"\b\w+\b", prompt)
                    for word in words:
                        if word.lower() in ["add", "fix", "update", "change", "delete", "remove", "patch", "modify", "logging", "check", "test", "in", "for", "to", "the"]:
                            continue
                        node_info = ast_loc.find_symbol(primary_file, word, original_code)
                        if node_info:
                            start_line = node_info.start_line
                            end_line = node_info.end_line
                            symbol_name = node_info.name
                            print(f"[PatchHandler] Located target symbol '{word}' via ASTLocator at lines {start_line}-{end_line}")
                            break
                except Exception as ex:
                    print(f"[PatchHandler] AST fallback lookup error: {ex}")

        if start_line is None or end_line is None:
            lines = original_code.splitlines()
            start_line = 1
            end_line = max(1, len(lines))

        # Retrieve target code range and surrounding context
        try:
            lines = original_code.splitlines()
            target_code = "\n".join(lines[start_line - 1:end_line])
            
            # Format surrounding context with line numbers and >>> flags for targeted lines
            context_start = max(1, start_line - 50)
            context_end = min(len(lines), end_line + 50)
            formatted_context = []
            for idx in range(context_start - 1, context_end):
                line_num = idx + 1
                line_content = lines[idx]
                if start_line <= line_num <= end_line:
                    formatted_context.append(f"{line_num:4d} >>> {line_content}")
                else:
                    formatted_context.append(f"{line_num:4d}     {line_content}")
            surrounding_context_str = "\n".join(formatted_context)
        except Exception:
            target_code = original_code
            surrounding_context_str = original_code

        patch_prompt = f"""You are a precise developer coding assistant.
The user wants to edit the following file: {primary_file}
Target Symbol/Block: {symbol_name or 'selected region'} (Lines {start_line} to {end_line}, marked with >>> in the surrounding context below)

Here is the surrounding context (+-50 lines):
```
{surrounding_context_str}
```

USER GOAL/REQUEST:
{prompt}

Please output ONLY the new rewritten code block that replaces the target lines {start_line} to {end_line}.
Your output must be a direct drop-in replacement. Do NOT include line numbers, prefix indicators (>>>), markdown code blocks, or commentary in your response. Just output the raw code.
"""
        if on_progress:
            on_progress("status", "Generating localized patch...")
            
        response = self.runtime.llm.chat([
            {"role": "user", "content": patch_prompt}
        ], task_type=TaskType.CHAT)
        
        cleaned_code = response.strip()
        if cleaned_code.startswith("```"):
            lines = cleaned_code.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_code = "\n".join(lines).strip()
        if cleaned_code.startswith("python"):
            cleaned_code = cleaned_code[6:].strip()

        if on_progress:
            on_progress("status", "Applying localized patch...")

        patch_engine = PatchEngine(self.runtime.file_manager)
        success = patch_engine.apply_patch(primary_file, start_line, end_line, cleaned_code)
        
        validation_passed = success
        if success:
            abs_path = self.runtime.file_manager.resolve_path(primary_file)
            try:
                import py_compile
                py_compile.compile(abs_path, doraise=True)
                validation_passed = True
            except Exception as ve:
                print(f"[PatchHandler] Compilation check failed: {ve}")
                validation_passed = False

                # One-shot repair attempt
                if on_progress:
                    on_progress("status", "Compilation failed. Attempting repair...")
                repair_prompt = f"""You are a precise software engineer. The code in {primary_file} has a syntax error.
ERROR MESSAGE:
{ve}

Please output the corrected code block for the entire file. Do NOT include markdown code fences or explanation.
"""
                repaired_response = self.runtime.llm.chat([
                    {"role": "user", "content": repair_prompt}
                ], task_type=TaskType.CHAT)
                
                cleaned_repair = repaired_response.strip()
                if cleaned_repair.startswith("```"):
                    lines = cleaned_repair.splitlines()
                    if lines:
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    cleaned_repair = "\n".join(lines).strip()
                if cleaned_repair.startswith("python"):
                    cleaned_repair = cleaned_repair[6:].strip()
                
                try:
                    self.runtime.file_manager.write_file(primary_file, cleaned_repair)
                    py_compile.compile(abs_path, doraise=True)
                    validation_passed = True
                except Exception as ve2:
                    print(f"[PatchHandler] One-shot repair failed: {ve2}. Rolling back.")
                    self.runtime.file_manager.write_file(primary_file, original_code)
                    validation_passed = False

        return {
            "success": validation_passed,
            "file_path": primary_file,
            "patch": cleaned_code
        }
