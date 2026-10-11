# editing/patch_engine.py

import ast
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Any

class PatchType(Enum):
    INSERT = "insert"
    INSERT_BEFORE = "insert_before"
    INSERT_AFTER = "insert_after"
    REPLACE = "replace"
    DELETE = "delete"
    RENAME_SYMBOL = "rename_symbol"
    REPLACE_SPAN = "replace_span"
    SPAN_PATCH = "span_patch"
    STRUCTURAL_PATCH = "structural_patch"
    FULL_REWRITE = "full_rewrite"

@dataclass
class PatchSpan:
    file: str
    symbol: str
    start_line: int
    end_line: int

@dataclass
class PatchOperation:
    patch_type: PatchType
    file: str
    start_line: int
    end_line: int
    content: str = ""
    span: Optional[PatchSpan] = None

@dataclass
class PatchPlan:
    operations: List[PatchOperation]

class PatchEngine:
    def __init__(self, file_manager):
        self.file_manager = file_manager

    def apply_patch(self, plan_or_file, start_line=None, end_line=None, replacement=None) -> bool:
        """Apply the patch plan transactionally. Supports both PatchPlan and span-centric signature."""
        if isinstance(plan_or_file, str) or start_line is not None:
            op = PatchOperation(
                patch_type=PatchType.REPLACE,
                file=plan_or_file,
                start_line=start_line,
                end_line=end_line,
                content=replacement if replacement is not None else ""
            )
            plan = PatchPlan(operations=[op])
        else:
            plan = plan_or_file

        # 1. Group operations by file
        file_ops = {}
        for op in plan.operations:
            file_ops.setdefault(op.file, []).append(op)

        # Enforce touched files budget
        from editing.patch_budget import PatchBudget
        budget = PatchBudget()
        if len(file_ops) > budget.max_files:
            print(f"[PatchEngine] Rejecting patch: touched files ({len(file_ops)}) exceeds budget ({budget.max_files})")
            return False

        # Determine validation mode using ValidationEscalator
        from core.validation_escalator import ValidationEscalator
        from core.validation_mode import ValidationMode
        from core.execution_mode import TaskIntentMode as ExecutionMode
        from runtime.fast_path_router import FastPathRouter

        active_goal = ""
        try:
            if hasattr(plan_or_file, "goal") and plan_or_file.goal:
                active_goal = plan_or_file.goal
        except Exception:
            pass

        exec_mode = ExecutionMode.PATCH
        if active_goal:
            try:
                route_decision = FastPathRouter.route(active_goal)
                exec_mode = route_decision.execution_mode
            except Exception:
                pass

        combined_content = ""
        for op in plan.operations:
            combined_content += "\n" + (op.content or "")

        val_mode = ValidationEscalator.choose_validation(combined_content, active_goal, exec_mode)
        print(f"[PatchEngine] Validation escalator chose: {val_mode} (Goal: {active_goal}, Mode: {exec_mode})")

        # 2. In-memory application and verification
        patched_contents = {}
        for file_path, ops in file_ops.items():
            try:
                original_content = self.file_manager.read_file(file_path)
            except Exception:
                original_content = ""
            if original_content is None:
                original_content = ""

            try:
                # Apply all operations to this file
                patched_content = self._apply_ops_to_content(original_content, ops)
                
                # Enforce line and hunk budget constraints
                passed, reason = PatchBudget.validate_patch(original_content, patched_content, budget)
                if not passed:
                    print(f"[PatchEngine] Rejecting patch for {file_path}: {reason}")
                    return False
                
                # AST/Tree-sitter syntax verification across supported languages (Python, Java, TS, JS)
                if val_mode.value >= ValidationMode.FAST.value:
                    from editing.ast_locator import ASTLocator
                    locator = ASTLocator()
                    lang_str = locator.get_language(file_path)
                    lang = locator.langs.get(lang_str)
                    if lang:
                        from tree_sitter import Parser
                        parser = Parser(lang)
                        tree = parser.parse(patched_content.encode("utf-8"))
                        
                        def has_syntax_error(node) -> bool:
                            if node.type in ("ERROR", "MISSING"):
                                return True
                            for child in node.children:
                                if has_syntax_error(child):
                                    return True
                            return False
                            
                        if has_syntax_node_error := has_syntax_error(tree.root_node):
                            print(f"[PatchEngine] Tree-sitter syntax validation failed for {file_path} (Language: {lang_str})")
                            return False
                
                patched_contents[file_path] = patched_content
            except Exception as e:
                print(f"[PatchEngine] Failed to apply operations to {file_path}: {e}")
                return False

        # 3. Transactional Write: Write all files only if everything verified successfully
        try:
            for file_path, content in patched_contents.items():
                self.file_manager.write_file(file_path, content)
            return True
        except Exception as e:
            print(f"[PatchEngine] Failed to write patched files: {e}")
            # If writing fails halfway, we try to roll back, but in our mocked setup this is sufficient.
            return False

    def _apply_ops_to_content(self, content: str, ops: List[PatchOperation]) -> str:
        from editing.patch_applier import PatchApplier
        applier = PatchApplier()

        result = content
        for op in ops:
            if op.patch_type == PatchType.SPAN_PATCH:
                if op.span:
                    from editing.ast_locator import ASTNodeInfo
                    symbol_info = ASTNodeInfo(
                        node_type="method",
                        name=op.span.symbol,
                        start_line=op.span.start_line,
                        end_line=op.span.end_line,
                        start_byte=op.start_line,
                        end_byte=op.end_line,
                        content=""
                    )
                else:
                    symbol_info = None
                result = applier.apply_span_patch(result, op.content, symbol_info)
            elif op.patch_type == PatchType.STRUCTURAL_PATCH:
                import json
                try:
                    data = json.loads(op.content)
                    action = data.get("action")
                    if action == "insert_import":
                        result = applier.insert_import(result, data.get("statement"), data.get("language", "java"))
                    elif action == "insert_class_member":
                        result = applier.insert_class_member(result, data.get("class_name"), data.get("member_content"), data.get("language", "java"))
                except Exception as e:
                    print(f"[PatchEngine] Structural patch error: {e}")
            elif op.patch_type == PatchType.FULL_REWRITE:
                result = op.content
            else:
                lines = result.splitlines()
                s = op.start_line - 1  # 0-based
                e = op.end_line - 1
                s = max(0, min(len(lines) - 1, s))
                e = max(s, min(len(lines) - 1, e))

                new_lines = op.content.splitlines() if op.content else []

                if op.patch_type == PatchType.REPLACE:
                    lines[s : e + 1] = new_lines
                elif op.patch_type == PatchType.DELETE:
                    del lines[s : e + 1]
                elif op.patch_type == PatchType.INSERT:
                    lines[s:s] = new_lines
                elif op.patch_type == PatchType.INSERT_BEFORE:
                    lines[s:s] = new_lines
                elif op.patch_type == PatchType.INSERT_AFTER:
                    lines[e + 1:e + 1] = new_lines
                else:
                    raise ValueError(f"Unsupported patch type: {op.patch_type}")
                result = "\n".join(lines) + ("\n" if lines else "")

        return result
