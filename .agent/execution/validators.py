# execution/validators.py

from pathlib import Path


class ExecutionValidator:

    MAX_DIFF_SIZE = 200000
    MAX_PATCH_SIZE = 500000

    ALLOWED_TOOLS = {
        # filesystem
        "query_manifest",
        "lookup_symbol",
        "search_code",
        "read_file",
        "semantic_retrieve",

        # git
        "git_status",
        "git_diff",
        "git_commit",
        "rollback_file",
        "create_checkpoint",

        # modification
        "apply_patch",
        "write_file",
        "generate_patch",
        "modify_symbol",
        "execute_edit_plan",


        # testing
        "run_backend_tests",
        "run_frontend_tests",
        "run_frontend_build",

        # planner / compiler actions
        "summarize_state",
        "plan_modifications",
        "reflect",
        "replan",
    }

    def validate_retry(
        self,
        execution
    ):
        """
        Accept:
        - ExecutableAction
        - Any object exposing to_dict()
        - Plain dict
        """

        if hasattr(
            execution,
            "to_dict"
        ):
            execution = execution.to_dict()

        elif not isinstance(
            execution,
            dict
        ):
            raise RuntimeError(
                "Execution must be dict-like"
            )

        retries = execution.get(
            "retries",
            0
        )

        max_retries = execution.get(
            "max_retries",
            3
        )

        if not isinstance(
            retries,
            int
        ):
            raise RuntimeError(
                "Retry count must be an integer"
            )

        if not isinstance(
            max_retries,
            int
        ):
            raise RuntimeError(
                "Max retries must be an integer"
            )

        if retries < 0:

            raise RuntimeError(
                "Retry count cannot be negative"
            )

        if max_retries < 0:

            raise RuntimeError(
                "Max retries cannot be negative"
            )

        if retries >= max_retries:

            raise RuntimeError(
                "Maximum retries exceeded"
            )

    def validate_execution(
        self,
        tool,
        args
    ):

        if not tool:

            raise RuntimeError(
                "Tool missing"
            )

        if tool not in self.ALLOWED_TOOLS:

            raise RuntimeError(
                f"Tool not allowed: {tool}"
            )

        if args is None:
            args = {}

        if not isinstance(
            args,
            dict
        ):
            raise RuntimeError(
                "Execution args must be a dictionary"
            )

        # =============================================
        # lookup_symbol
        # =============================================

        if tool == "lookup_symbol":
            symbol = args.get("symbol") or args.get("symbol_name")
            if not symbol:
                raise RuntimeError("lookup_symbol requires 'symbol' or 'symbol_name'")

        # =============================================
        # read_file
        # =============================================

        elif tool == "read_file":

            path = args.get(
                "path"
            )

            if not path:

                raise RuntimeError(
                    "Missing file path"
                )

            self.validate_path(
                path
            )

        # =============================================
        # rollback_file
        # =============================================

        elif tool == "rollback_file":

            path = args.get(
                "path"
            )

            if not path:

                raise RuntimeError(
                    "Rollback requires path"
                )

            self.validate_path(
                path
            )

        # =============================================
        # apply_patch
        # =============================================

        elif tool == "apply_patch":

            # Allow state fallback
            if not args:
                return

            patch = args.get(
                "patch"
            )

            if not patch:

                raise RuntimeError(
                    "Patch content missing"
                )

        # =============================================
        # write_file
        # =============================================

        elif tool == "write_file":

            path = args.get(
                "path"
            )

            if not path:

                raise RuntimeError(
                    "Missing file path"
                )

            self.validate_path(
                path
            )

            if "content" not in args:

                raise RuntimeError(
                    "Missing file content"
                )

        # =============================================
        # generate_patch
        # =============================================

        elif tool == "generate_patch":

            # Allow state-based execution fallback
            if not args:
                return

            required = [
                "path",
                "original",
                "modified",
            ]

            for key in required:

                value = args.get(key)

                if value is None or value == "":

                    raise RuntimeError(
                        f"Missing {key}"
                    )

            self.validate_path(
                args["path"]
            )

        # =============================================
        # execute_edit_plan
        # =============================================

        elif tool == "execute_edit_plan":

            required = [
                "operation",
                "symbol",
                "goal",
            ]

            for key in required:

                value = args.get(key)

                if value is None or value == "":

                    raise RuntimeError(
                        f"Missing {key}"
                    )

        # =============================================
        # modify_symbol
        # =============================================

        elif tool == "modify_symbol":

            required = [
                "symbol",
                "goal",
            ]

            for key in required:

                value = args.get(key)

                if value is None or value == "":

                    raise RuntimeError(
                        f"Missing {key}"
                    )

            if "path" in args and args["path"]:
                self.validate_path(
                    args["path"]
                )


    def validate_diff_size(
        self,
        diff
    ):

        if diff is None:
            return

        if len(diff) > self.MAX_DIFF_SIZE:

            raise RuntimeError(
                "Diff exceeds safety limit"
            )

    def validate_patch(
        self,
        patch
    ):

        if not patch:

            raise RuntimeError(
                "Empty patch"
            )

        if len(patch) > self.MAX_PATCH_SIZE:

            raise RuntimeError(
                "Patch too large"
            )

        # Validate patch structure (must be structured JSON, SEARCH/REPLACE, or unified diff)
        cleaned = patch.strip()
        is_json = False
        if "{" in cleaned or "[" in cleaned:
            try:
                import json
                import re
                match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
                if match:
                    json.loads(match.group(1))
                    is_json = True
            except Exception:
                pass

        is_search_replace = "<<<<<<< SEARCH" in patch and "=======" in patch and ">>>>>>> REPLACE" in patch
        is_diff = "@@ " in patch or "--- " in patch or "+++ " in patch

        if not (is_json or is_search_replace or is_diff):
            raise RuntimeError(
                "Invalid patch format: missing unified diff markers, SEARCH/REPLACE block, or Structured Edit JSON DSL."
            )

    def validate_path(
        self,
        path
    ):

        if not path:

            raise RuntimeError(
                "Path missing"
            )

        try:

            Path(path)

        except Exception as exc:

            raise RuntimeError(
                f"Invalid path: {path}"
            ) from exc

    # =====================================================
    # FILE SYNTAX & BALANCE VALIDATION
    # =====================================================

    def validate_file_syntax(self, path_str: str) -> None:
        """
        Validates the file's syntactic and structure correctness before staging.
        Supports AST checking for Python and JSON, and brace balance checks for C-like languages (Java, JS, TS).
        """
        path = Path(path_str)
        if not path.exists():
            return

        suffix = path.suffix.lower()

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            raise RuntimeError(f"Unable to read file '{path_str}' for syntax verification: {e}")

        # 1. PYTHON SYNTAX AST CHECK
        if suffix == ".py":
            import ast
            try:
                ast.parse(content)
            except SyntaxError as e:
                raise RuntimeError(
                    f"Syntax error in modified Python file '{path_str}' at line {e.lineno}, col {e.offset}: {e.msg}\n"
                    f"Code line: {e.text}"
                )

        # 2. JSON VALIDATION AST CHECK
        elif suffix == ".json":
            import json
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"Invalid JSON syntax in modified file '{path_str}' at line {e.lineno}, col {e.col}: {e.msg}"
                )

        # 3. BRACE & PARENTHESIS BALANCING (Java, TS, JS, CSS)
        elif suffix in {".java", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss"}:
            braces = []
            parens = []
            brackets = []
            
            # Simple line-by-line tracker to maintain accurate error locations
            for line_idx, line in enumerate(content.splitlines(), 1):
                # Strip string literals and comments to avoid comment/string brace false positives
                cleaned_line = self.re_sub_literals(line)
                
                for char_idx, char in enumerate(cleaned_line, 1):
                    if char == '{':
                        braces.append((line_idx, char_idx))
                    elif char == '}':
                        if not braces:
                            raise RuntimeError(
                                f"Unmatched closing brace '}}' in modified file '{path_str}' "
                                f"at line {line_idx}, column {char_idx}."
                            )
                        braces.pop()
                    elif char == '(':
                        parens.append((line_idx, char_idx))
                    elif char == ')':
                        if not parens:
                            raise RuntimeError(
                                f"Unmatched closing parenthesis ')' in modified file '{path_str}' "
                                f"at line {line_idx}, column {char_idx}."
                            )
                        parens.pop()
                    elif char == '[':
                        brackets.append((line_idx, char_idx))
                    elif char == ']':
                        if not brackets:
                            raise RuntimeError(
                                f"Unmatched closing bracket ']' in modified file '{path_str}' "
                                f"at line {line_idx}, column {char_idx}."
                            )
                        brackets.pop()

            if braces:
                line, col = braces[-1]
                raise RuntimeError(
                    f"Unmatched opening brace '{{' in modified file '{path_str}' "
                    f"at line {line}, column {col} (remained unclosed)."
                )
            if parens:
                line, col = parens[-1]
                raise RuntimeError(
                    f"Unmatched opening parenthesis '(' in modified file '{path_str}' "
                    f"at line {line}, column {col} (remained unclosed)."
                )
            if brackets:
                line, col = brackets[-1]
                raise RuntimeError(
                    f"Unmatched opening bracket '[' in modified file '{path_str}' "
                    f"at line {line}, column {col} (remained unclosed)."
                )

    def re_sub_literals(self, line: str) -> str:
        # Remove single-line comments
        if "//" in line:
            line = line.split("//", 1)[0]
        # Remove string literals to prevent quote brace detection
        line = self.re_replace_quotes(line, '"')
        line = self.re_replace_quotes(line, "'")
        return line

    def re_replace_quotes(self, s: str, quote_char: str) -> str:
        parts = s.split(quote_char)
        # Every odd element is inside quotes, replace it
        new_parts = []
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                new_parts.append(" ") # replace quoted content with single space
            else:
                new_parts.append(part)
        return "".join(new_parts)

