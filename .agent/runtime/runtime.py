# runtime/runtime.py

import os
from uuid import uuid4

from runtime.execution_engine import (
    ExecutionEngine
)

from runtime.recovery_loop import (
    RecoveryLoop
)

from memory.state_manager import (
    StateManager
)

from execution.executor import (
    Executor
)

from repository.file_manager import (
    FileManager
)

from context.assembler import (
    ContextAssembler
)

from context.prompt_builder import (
    PromptBuilder
)

from llm.ollama_client import (
    OllamaClient
)


class Runtime:

    MAX_ITERATIONS = 20

    def __init__(self):
        # Auto-create database schema if tables are missing
        try:
            from repository_intelligence.db.connection import Base, engine
            from repository_intelligence.models.repository import Repository
            from repository_intelligence.models.file import File
            from repository_intelligence.models.symbol import (
                Symbol,
                Embedding,
                IndexJob,
                RepairPattern,
                SymbolRelationship,
                Test
            )
            Base.metadata.create_all(bind=engine)
            print(f"[Runtime] Database schema initialized with tables: {list(Base.metadata.tables.keys())}")
        except Exception as e:
            print(f"[Runtime] Warning: Database schema auto-creation skipped: {e}")

        self.state_manager = (
            StateManager()
        )

        self.llm = OllamaClient()

        self.context = (
            ContextAssembler()
        )

        self.prompts = (
            PromptBuilder()
        )

        self.file_manager = (
            FileManager("..")
        )

        self.executor = Executor(
            self.file_manager,
            self.state_manager
        )

        self.engine = (
            ExecutionEngine(
                self.executor,
                self.state_manager
            )
        )

        self.recovery = (
            RecoveryLoop(
                self.state_manager,
                self.executor
            )
        )

    # ==========================================
    # START
    # ==========================================

    def start(self):

        print(
            "Autonomous Runtime Started"
        )

        while True:

            goal = input(
                "\nGoal > "
            )

            if goal.lower() in [
                "exit",
                "quit"
            ]:
                break

            self.run_goal(goal)

    # ==========================================
    # TASK
    # ==========================================

    def run_goal(
        self,
        goal,
        on_progress=None
    ):

        # Reuse existing task_id and state if already created by the server
        if self.state_manager.task_id is not None and self.state_manager.state is not None:
            task_id = self.state_manager.task_id
            state = self.state_manager.state
        else:
            task_id = str(uuid4())
            state = (
                self.state_manager.create_task(
                    goal=goal,
                    task_id=task_id
                )
            )

        if on_progress:
            on_progress("status", "Thinking...")

        # Resolve active_file and editor_context
        editor_context = getattr(state, "runtime_context", None)
        active_file = None
        if editor_context:
            active_file = getattr(editor_context, "active_file", None)
        if not active_file:
            from context.session_cache import SessionCache
            active_file = SessionCache.get_session("default").active_file

        # Resolve routing decision using FastPathRouter
        from runtime.fast_path_router import FastPathRouter
        from routing.intent_router import ExecutionMode
        
        route_decision = FastPathRouter.route(goal, editor_context)
        execution_mode = route_decision.execution_mode

        # =====================================================================
        # MODE 0 — ASSIST PIPELINE (retrieve → answer, no planning, < 2s target)
        # =====================================================================
        if execution_mode == ExecutionMode.ASSIST:
            print("[Runtime] Running Mode 0: Assist Pipeline...")
            from context.context_builder import ContextBuilder
            from inference.router import TaskType
            from context.context_router import ContextBuilderEnum

            builder = ContextBuilder(self.executor.retrieval_pipeline, self.state_manager)
            
            # Stage 1: Immediate local context (mode="inline")
            if on_progress:
                on_progress("status", "Analyzing local editor context...")
            stage1_context = builder.build_planning_context(goal, state, mode="inline")
            
            # Format Stage 1 context
            s1_compressed = self.context.compressor.compress_chunks(stage1_context.retrieved_chunks)
            s1_text = ""
            for chunk in s1_compressed:
                s1_text += f"\nFILE: {chunk.get('file')}\nSYMBOL: {chunk.get('symbol')}\n{chunk.get('content')}\n"

            prompt1 = f"""You are an expert AI software engineer assistant.
Answer the user's question/assist request using the provided local context.

LOCAL CONTEXT:
{s1_text}

USER GOAL/QUESTION:
{goal}
"""
            # Cache the assembled prompt, tokenized prompt, and symbol context
            from context.cache import ContextCache
            tokenized_p = [hash(word) % 100000 for word in prompt1.split()]
            ContextCache.set(
                task_id=task_id,
                active_file=active_file,
                repo_root=None,
                assembled_prompt=prompt1,
                tokenized_prompt=tokenized_p,
                symbol_context=stage1_context
            )
            # Start inference immediately
            if on_progress:
                on_progress("status", "Generating initial response...")
                token_stream = self.llm.chat([
                    {"role": "user", "content": prompt1}
                ], task_type=TaskType.CHAT, stream=True)
                full_response = []
                for token in token_stream:
                    full_response.append(token)
                    on_progress("token", token)
                response = "".join(full_response)
            else:
                response = self.llm.chat([
                    {"role": "user", "content": prompt1}
                ], task_type=TaskType.CHAT)

            # Stage 2: Background expansion (if context_mode is not selection only)
            if route_decision.context_mode != ContextBuilderEnum.SELECTION:
                if on_progress:
                    on_progress("status", "Expanding context with background search...")
                
                # Fetch Stage 2 context
                stage2_context = builder.build_planning_context(goal, state, mode=route_decision.context_mode.value)
                
                # Find new chunks
                s1_chunk_ids = {c.get("chunk_id") for c in stage1_context.retrieved_chunks}
                new_chunks = [c for c in stage2_context.retrieved_chunks if c.get("chunk_id") not in s1_chunk_ids]
                
                if new_chunks:
                    if on_progress:
                        on_progress("status", "Enriching answer with background repository details...")
                        on_progress("token", "\n\n### Enriched Background Analysis\n")
                    
                    s2_compressed = self.context.compressor.compress_chunks(new_chunks)
                    s2_text = ""
                    for chunk in s2_compressed:
                        s2_text += f"\nFILE: {chunk.get('file')}\nSYMBOL: {chunk.get('symbol')}\n{chunk.get('content')}\n"
                    
                    prompt2 = f"""You are an expert AI software engineer assistant.
Enrich your previous explanation with the following newly retrieved background context.
Only explain new details, do not repeat what you already explained.

PREVIOUS EXPLANATION:
{response}

NEW REPOSITORY CONTEXT:
{s2_text}
"""
                    if on_progress:
                        token_stream2 = self.llm.chat([
                            {"role": "user", "content": prompt2}
                        ], task_type=TaskType.CHAT, stream=True)
                        full_response2 = []
                        for token in token_stream2:
                            full_response2.append(token)
                            on_progress("token", token)
                        response += "\n\n### Enriched Background Analysis\n" + "".join(full_response2)
                    else:
                        response2 = self.llm.chat([
                            {"role": "user", "content": prompt2}
                        ], task_type=TaskType.CHAT)
                        response += "\n\n### Enriched Background Analysis\n" + response2

            # Create virtual completed plan for Assist
            from planning.execution_plan import ExecutionPlan, ExecutionStage
            from planning.task_node import TaskNode
            from planning.task_status import TaskStatus
            from planning.task_types import TaskType as PlanningTaskType
            from planning.planning_strategy import PlanningStrategy

            task_node = TaskNode(
                id="assist-task",
                type=PlanningTaskType.RETRIEVE_CONTEXT,
                description=response.strip(),
                status=TaskStatus.COMPLETED,
                outputs={"response": response.strip()}
            )
            execution_plan = ExecutionPlan(
                goal=goal,
                plan_id=task_id,
                strategy=PlanningStrategy.ANALYSIS,
                tasks=[task_node],
                stages=[ExecutionStage(stage_id="assist-stage", parallel_tasks=["assist-task"])]
            )
            self.state_manager.set_execution_plan(execution_plan)
            self.state_manager.set_execution_state("COMPLETED")
            state.status = "completed"
            self.state_manager.save_state()
            print("[Runtime] Assist Pipeline completed.")
            return

        # =====================================================================
        # MODE 3 — INLINE PIPELINE (Lane 1: Local inline edit / tool queries)
        # =====================================================================
        elif execution_mode == ExecutionMode.INLINE or self._is_inline_tool_query(goal):
            if self._is_inline_tool_query(goal):
                print("[Runtime] Running Mode 3: Inline Tool Command Pipeline...")
                result = self._execute_inline_tool_query(goal)
                
                if on_progress:
                    on_progress("status", "Executing inline query...")
                    on_progress("token", result)
                
                from planning.execution_plan import ExecutionPlan, ExecutionStage
                from planning.task_node import TaskNode
                from planning.task_status import TaskStatus
                from planning.task_types import TaskType as PlanningTaskType
                from planning.planning_strategy import PlanningStrategy

                task_node = TaskNode(
                    id="inline-task",
                    type=PlanningTaskType.RETRIEVE_CONTEXT,
                    description=result.strip(),
                    status=TaskStatus.COMPLETED,
                    outputs={"response": result.strip()}
                )
                execution_plan = ExecutionPlan(
                    goal=goal,
                    plan_id=task_id,
                    strategy=PlanningStrategy.ANALYSIS,
                    tasks=[task_node],
                    stages=[ExecutionStage(stage_id="inline-stage", parallel_tasks=["inline-task"])]
                )
                self.state_manager.set_execution_plan(execution_plan)
                self.state_manager.set_execution_state("COMPLETED")
                state.status = "completed"
                self.state_manager.save_state()
                print("[Runtime] Inline Tool Pipeline completed.")
                return
            else:
                print("[Runtime] Running Lane 1: Local Inline Edit Pipeline...")
                result = self._execute_lane1_inline_edit(goal, editor_context, active_file, task_id, on_progress)
                primary_file = active_file
                validation_passed = result.startswith("SUCCESS")

        # =====================================================================
        # MODE 1 — PATCH PIPELINE (Lane 2: Symbol Edit via SymbolEditor)
        # =====================================================================
        elif execution_mode == ExecutionMode.PATCH:
            print("[Runtime] Running Lane 2: Symbol Edit Pipeline...")
            result = self._execute_lane2_symbol_edit(goal, editor_context, active_file, task_id, on_progress)
            primary_file = active_file
            if editor_context and getattr(editor_context, "active_file", None):
                primary_file = editor_context.active_file
            validation_passed = result.startswith("SUCCESS")

        # Shared wrap-up block for Lane 1 (Inline edit) and Lane 2 (Symbol edit)
        if (execution_mode == ExecutionMode.INLINE and not self._is_inline_tool_query(goal)) or execution_mode == ExecutionMode.PATCH:
            from planning.execution_plan import ExecutionPlan, ExecutionStage
            from planning.task_node import TaskNode
            from planning.task_status import TaskStatus
            from planning.task_types import TaskType as PlanningTaskType
            from planning.planning_strategy import PlanningStrategy

            status = TaskStatus.COMPLETED if validation_passed else TaskStatus.FAILED
            task_node = TaskNode(
                id="edit-task",
                type=PlanningTaskType.MODIFY_SYMBOL,
                description=f"Direct edit in {primary_file or active_file}",
                status=status,
                outputs={"applied": validation_passed, "result": result}
            )
            execution_plan = ExecutionPlan(
                goal=goal,
                plan_id=task_id,
                strategy=PlanningStrategy.BUGFIX,
                tasks=[task_node],
                stages=[ExecutionStage(stage_id="edit-stage", parallel_tasks=["edit-task"])]
            )
            self.state_manager.set_execution_plan(execution_plan)
            if validation_passed:
                self.state_manager.set_execution_state("COMPLETED")
                state.status = "completed"
            else:
                self.state_manager.set_execution_state("FAILED")
                state.status = "failed"
            
            self.state_manager.save_state()
            print(f"[Runtime] Edit completed with result: {result}")
            return

        # =====================================================================
        # MODE 2 — AGENT PIPELINE (Full planning, validation, reflection loop)
        # =====================================================================
        else:
            print("[Runtime] Running Mode 2: Agent Pipeline...")
            if on_progress:
                on_progress("status", "Analyzing workspace index...")
                
            from context.context_builder import ContextBuilder
            builder = ContextBuilder(self.executor.retrieval_pipeline, self.state_manager)
            planning_context = builder.build_planning_context(goal, state, mode=route_decision.context_mode.value)
            state.modification_targets = planning_context.related_files

            if on_progress:
                on_progress("status", "Compiling execution plan...")

            from planning.plan_compiler import PlanCompiler
            from planning.plan_validator import PlanValidator

            compiler = PlanCompiler()
            execution_plan = compiler.compile(planning_context)

            validator = PlanValidator(repo_root=self.file_manager.root)
            validation_errors = validator.validate(execution_plan)
            if validation_errors:
                print("\n[Runtime] PLAN VALIDATION FAILED:")
                for err in validation_errors:
                    print(f"  - {err}")
                raise RuntimeError(f"Plan validation failed with errors: {validation_errors}")
            else:
                print("\n[Runtime] Plan validation passed successfully.")

            plan_dir = os.path.join(os.path.dirname(__file__), "..", "logs", "plans")
            os.makedirs(plan_dir, exist_ok=True)
            plan_path = os.path.join(plan_dir, f"{execution_plan.plan_id}.json")
            try:
                execution_plan.save(plan_path)
                print(f"[Runtime] Plan persisted to {plan_path}")
            except Exception as e:
                print(f"[Runtime] Warning: Plan persistence failed: {e}")

            self.state_manager.set_execution_plan(execution_plan)

            if on_progress:
                on_progress("status", "Executing tasks and running validators...")

            iteration = 0
            while iteration < self.MAX_ITERATIONS:
                iteration += 1
                state.runtime_memory.total_iterations += 1
                self.engine.run()

                plan = self.state_manager.get_execution_plan()
                if plan:
                    if plan.is_finished():
                        break
                else:
                    recovered = self.recovery.run()
                    if not recovered:
                        break

            plan = self.state_manager.get_execution_plan()
            if plan:
                if plan.is_successful():
                    self.state_manager.set_execution_state("COMPLETED")
                else:
                    self.state_manager.set_execution_state("FAILED")
            else:
                self.state_manager.set_execution_state("COMPLETED")

            state.status = "completed"
            self.state_manager.save_state()
            print("\nTask Complete")

    def _is_inline_tool_query(self, goal: str) -> bool:
        g = goal.lower().strip()
        if g.startswith("/"):
            g = g[1:].strip()
        return (
            g == "list files" or g == "show files" or g.startswith("list files ") or
            g == "list directories" or g == "show directories" or
            g.startswith("read file ") or g.startswith("show file ") or g.startswith("view file ") or
            g.startswith("search symbol ") or g.startswith("find symbol ") or g.startswith("locate symbol ")
        )

    def _execute_inline_tool_query(self, goal: str) -> str:
        g = goal.lower().strip()
        if g.startswith("/"):
            g = g[1:].strip()
        
        # 1. LIST FILES
        if g == "list files" or g == "show files" or g.startswith("list files ") or g == "list directories" or g == "show directories":
            import os
            all_files = []
            root_dir = self.file_manager.root
            for root, dirs, files in os.walk(root_dir):
                # Skip ignored directories
                dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", "node_modules", ".agent", ".venv", "venv"]]
                for file in files:
                    if not file.endswith((".pyc", ".pyo", ".pkl")):
                        rel = os.path.relpath(os.path.join(root, file), root_dir)
                        all_files.append(rel)
            result = "Files in repository:\n" + "\n".join(all_files[:100])
            if len(all_files) > 100:
                result += f"\n... and {len(all_files) - 100} more files."
            return result

        # 2. READ FILE
        elif g.startswith("read file ") or g.startswith("show file ") or g.startswith("view file "):
            parts = goal.split(maxsplit=2)
            if len(parts) >= 3:
                file_path = parts[2].strip().strip("'\"")
            else:
                file_path = goal.replace("read file", "").replace("show file", "").replace("view file", "").strip().strip("'\"")
            
            try:
                content = self.file_manager.read_file(file_path)
                if content is not None:
                    return f"### File: {file_path}\n```python\n{content}\n```"
                else:
                    return f"File '{file_path}' could not be read (returned None)."
            except Exception as e:
                return f"Error reading file '{file_path}': {e}"

        # 3. SEARCH SYMBOL
        elif g.startswith("search symbol ") or g.startswith("find symbol ") or g.startswith("locate symbol "):
            symbol_name = goal.replace("search symbol", "").replace("find symbol", "").replace("locate symbol", "").strip().strip("'\"")
            from repository_intelligence.db.connection import SessionLocal
            from repository_intelligence.models.symbol import Symbol
            db = SessionLocal()
            try:
                symbols = db.query(Symbol).filter(Symbol.name.ilike(f"%{symbol_name}%")).limit(10).all()
                if symbols:
                    return "Found symbols:\n" + "\n".join([f"- {s.name} ({s.file_path}:{s.start_line})" for s in symbols])
                else:
                    return f"No symbols matching '{symbol_name}' found."
            except Exception as e:
                return f"Error searching for symbol '{symbol_name}': {e}"
            finally:
                db.close()
        
        return "Unknown inline command."

    def _execute_lane1_inline_edit(self, goal: str, editor_context, active_file: str, task_id: str, on_progress) -> str:
        if not active_file and editor_context:
            active_file = getattr(editor_context, "active_file", None)
            
        if not active_file:
            return "FAILED: No active file resolved for inline edit."
            
        try:
            original_code = self.file_manager.read_file(active_file)
        except Exception as e:
            return f"FAILED: Error reading file '{active_file}': {e}"

        start_line = None
        end_line = None
        
        # 1. Check selection range
        if editor_context:
            sel_range = getattr(editor_context, "selection_range", None) or getattr(editor_context, "selection", None)
            if sel_range and isinstance(sel_range, (list, tuple)) and len(sel_range) >= 2:
                try:
                    start_line = sel_range[0][0]
                    end_line = sel_range[1][0]
                except Exception:
                    pass
                    
        # 2. Check cursor position enclosing AST node
        if (start_line is None or end_line is None) and editor_context:
            cursor_pos = getattr(editor_context, "cursor_position", None) or getattr(editor_context, "cursor", None)
            cursor_line = None
            if cursor_pos and isinstance(cursor_pos, (list, tuple)) and len(cursor_pos) >= 1:
                try:
                    cursor_line = cursor_pos[0]
                except Exception:
                    pass
            elif cursor_pos and isinstance(cursor_pos, int):
                cursor_line = cursor_pos
                
            if cursor_line is not None:
                from editing.ast_locator import ASTLocator
                try:
                    locator = ASTLocator()
                    node_info = locator.find_enclosing_node(active_file, cursor_line, original_code)
                    if node_info:
                        start_line = node_info.start_line
                        end_line = node_info.end_line
                except Exception as e:
                    print(f"[Lane 1] AST enclosing node resolution failed: {e}")

        # Fallback to entire file if span resolution failed
        if start_line is None or end_line is None:
            lines = original_code.splitlines()
            start_line = 1
            end_line = max(1, len(lines))

        # Retrieve target code range
        try:
            lines = original_code.splitlines()
            target_code = "\n".join(lines[start_line - 1:end_line])
        except Exception:
            target_code = original_code

        # Minimal prompt with no retrieval/planning context
        prompt = f"""You are a precise developer coding assistant.
The user wants to perform a local inline edit in: {active_file}
Target Region: lines {start_line} to {end_line}

USER GOAL/REQUEST:
{goal}

Here is the exact code block to be replaced:
```
{target_code}
```

Please output ONLY the new rewritten code block for this region.
Your output must be a direct drop-in replacement for the code block above.
Do NOT include any explanations, markdown code blocks, or commentary in your response. Just output the raw code.
"""
        if on_progress:
            on_progress("status", "Generating inline patch...")

        from inference.router import TaskType
        response = self.llm.chat([
            {"role": "user", "content": prompt}
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
            on_progress("status", "Applying inline patch...")

        # Apply using low-level PatchEngine directly
        from editing.patch_engine import PatchEngine
        patch_engine = PatchEngine(self.file_manager)
        success = patch_engine.apply_patch(active_file, start_line, end_line, cleaned_code)

        if success:
            # Fast tree-sitter based syntax sanity validation
            from editing.ast_locator import ASTLocator
            try:
                locator = ASTLocator()
                lang_str = locator.get_language(active_file)
                lang = locator.langs.get(lang_str)
                if lang:
                    from tree_sitter import Parser
                    parser = Parser(lang)
                    new_content = self.file_manager.read_file(active_file)
                    tree = parser.parse(new_content.encode("utf-8"))
                    
                    def has_error(node) -> bool:
                        if node.type in ("ERROR", "MISSING"):
                            return True
                        for child in node.children:
                            if has_error(child):
                                return True
                        return False
                        
                    if has_error(tree.root_node):
                        print("[Lane 1] Syntax error detected in inline edit. Reverting.")
                        self.file_manager.write_file(active_file, original_code)
                        return "FAILED: Syntax error in generated code."
            except Exception as e:
                print(f"[Lane 1] Fast syntax check warning: {e}")
                
            return "SUCCESS"
        else:
            return "FAILED: Patch engine rejected changes."

    def _execute_lane2_symbol_edit(self, goal: str, editor_context, active_file: str, task_id: str, on_progress) -> str:
        symbol_name = None
        from editing.ast_locator import ASTLocator
        locator = ASTLocator()
        
        cursor_line = None
        if editor_context:
            cursor_pos = getattr(editor_context, "cursor_position", None) or getattr(editor_context, "cursor", None)
            if cursor_pos and isinstance(cursor_pos, (list, tuple)) and len(cursor_pos) >= 1:
                try:
                    cursor_line = cursor_pos[0]
                except Exception:
                    pass
            elif cursor_pos and isinstance(cursor_pos, int):
                cursor_line = cursor_pos
                
        primary_file = active_file
        if editor_context and getattr(editor_context, "active_file", None):
            primary_file = editor_context.active_file
            
        if cursor_line is not None and primary_file:
            try:
                node_info = locator.find_enclosing_node(primary_file, cursor_line)
                if node_info:
                    symbol_name = node_info.name
            except Exception as e:
                print(f"[Lane 2] Failed to resolve enclosing node for symbol: {e}")

        # Extract symbol from goal if not resolved, otherwise fallback to class/file name
        if not symbol_name:
            import re
            symbol_regex = re.compile(r"\b\w+\.\w+\b")
            match = symbol_regex.search(goal)
            if match:
                symbol_name = match.group(0)
            else:
                if primary_file:
                    symbol_name = os.path.splitext(os.path.basename(primary_file))[0]
                else:
                    symbol_name = "Global"

        if on_progress:
            on_progress("status", f"Modifying symbol '{symbol_name}' using SymbolEditor...")

        from engines.patch_engine import _get_symbol_editor
        symbol_editor = _get_symbol_editor(self)
        try:
            res = symbol_editor.modify(
                symbol_name=symbol_name,
                instruction=goal,
                file_path=primary_file,
                operation="modify_symbol"
            )
            if res.get("success", False):
                return "SUCCESS"
            else:
                return f"FAILED: {res.get('error', 'Unknown symbol edit error')}"
        except Exception as e:
            return f"FAILED: Exception: {e}"
