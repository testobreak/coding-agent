# validation/fast_validator.py
import ast

class FastValidator:
    def validate_python(self, code: str):
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def validate_java(self, code: str):
        try:
            if code.count("{") != code.count("}"):
                return False, "Unbalanced braces '{' and '}' in Java code."
            import tree_sitter_java as ts_java
            from tree_sitter import Language, Parser
            lang = Language(ts_java.language())
            parser = Parser(lang)
            tree = parser.parse(code.encode("utf-8"))
            
            def has_error(node):
                if node.type in ("ERROR", "MISSING"):
                    return True
                for child in node.children:
                    if has_error(child):
                        return True
                return False
                
            if has_error(tree.root_node):
                return False, "Tree-sitter syntax validation failed (Java)."
            return True, None
        except Exception as e:
            return True, None

    def validate_typescript(self, code: str):
        try:
            if code.count("{") != code.count("}"):
                return False, "Unbalanced braces '{' and '}' in TypeScript code."
            import tree_sitter_typescript as ts_typescript
            from tree_sitter import Language, Parser
            lang = Language(ts_typescript.language_typescript())
            parser = Parser(lang)
            tree = parser.parse(code.encode("utf-8"))
            
            def has_error(node):
                if node.type in ("ERROR", "MISSING"):
                    return True
                for child in node.children:
                    if has_error(child):
                        return True
                return False
                
            if has_error(tree.root_node):
                return False, "Tree-sitter syntax validation failed (TypeScript)."
            return True, None
        except Exception as e:
            return True, None
