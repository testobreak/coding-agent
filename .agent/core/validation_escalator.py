# core/validation_escalator.py
from dataclasses import dataclass
from .validation_mode import ValidationMode

@dataclass
class PatchMetadata:
    comment_only: bool = False
    local_method_edit: bool = False
    signature_changed: bool = False
    cross_module: bool = False

class ValidationEscalator:
    def choose(self, patch: PatchMetadata) -> ValidationMode:
        if patch.comment_only:
            return ValidationMode.NONE

        if patch.local_method_edit:
            return ValidationMode.FAST

        if patch.signature_changed:
            return ValidationMode.SEMANTIC

        if patch.cross_module:
            return ValidationMode.COMPILE

        return ValidationMode.FAST

    @staticmethod
    def choose_validation(patch_content: str, goal: str, execution_mode) -> ValidationMode:
        from core.execution_mode import TaskIntentMode as ExecutionMode
        
        # AGENT mode always escalates to FULL
        if execution_mode == ExecutionMode.AGENT:
            return ValidationMode.FULL
            
        patch_clean = patch_content.strip()
        lines = patch_clean.splitlines()
        
        is_comment_only = True
        is_log_only = True
        
        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue
            if line_strip.startswith("#") or line_strip.startswith("//") or line_strip.startswith("/*") or line_strip.startswith("*"):
                continue
            is_comment_only = False
            
            if "print(" in line_strip or "logger." in line_strip or "console.log" in line_strip or "System.out.println" in line_strip:
                continue
            is_log_only = False
            
        comment_only = is_comment_only or is_log_only

        signature_keywords = ["public ", "private ", "protected ", "class ", "interface ", "extends ", "implements ", "throws "]
        has_sig_kw = any(kw in patch_clean for kw in signature_keywords)
        
        goal_lower = goal.lower()
        signature_changed = has_sig_kw or "signature" in goal_lower or "return type" in goal_lower
        
        cross_module = "cross" in goal_lower or "module" in goal_lower
        local_method_edit = not comment_only and not signature_changed and not cross_module

        metadata = PatchMetadata(
            comment_only=comment_only,
            local_method_edit=local_method_edit,
            signature_changed=signature_changed,
            cross_module=cross_module
        )
        
        return ValidationEscalator().choose(metadata)
