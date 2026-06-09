import ast
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2] / ".agent"

if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


@dataclass
class ExtractedSymbol:

    name: str
    qualified_name: str
    symbol_type: str
    start_line: int
    end_line: int
    signature: str | None = None
    parent_qualified_name: str | None = None
    metadata: dict = field(default_factory=dict)
    source_hash: str = ""


@dataclass
class ExtractedRelationship:

    source_qualified_name: str | None
    target_name: str
    relationship_type: str
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ExtractedTest:

    name: str
    symbol_qualified_name: str | None
    framework: str | None = None
    target_name: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:

    symbols: list[ExtractedSymbol] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    tests: list[ExtractedTest] = field(default_factory=list)


class SymbolExtractor:

    def extract(
        self,
        absolute_path: str,
        relative_path: str,
        language: str
    ) -> ExtractionResult:

        text = Path(absolute_path).read_text(
            encoding="utf-8",
            errors="ignore"
        )

        heuristic = self._extract_heuristic(
            text,
            relative_path,
            language
        )
        tree_sitter = self._extract_tree_sitter(
            absolute_path,
            relative_path,
            language,
            text
        )

        if tree_sitter.symbols:
            tree_sitter.relationships = heuristic.relationships
            tree_sitter.tests = heuristic.tests
            return tree_sitter

        return heuristic

    def _extract_heuristic(
        self,
        text: str,
        relative_path: str,
        language: str
    ) -> ExtractionResult:

        if language == "python":
            return self._extract_python(
                text,
                relative_path
            )

        if language in {
            "java",
            "javascript",
            "typescript"
        }:
            return self._extract_brace_language(
                text,
                relative_path,
                language
            )

        return ExtractionResult()

    def _extract_tree_sitter(
        self,
        absolute_path: str,
        relative_path: str,
        language: str,
        text: str
    ) -> ExtractionResult:

        try:
            from parsers.registry import registry
        except Exception:
            return ExtractionResult()

        if not registry.supports(language):
            return ExtractionResult()

        parsed = registry.parse_file(
            absolute_path,
            language
        )

        if not parsed or parsed.error:
            return ExtractionResult()

        result = ExtractionResult()
        lines = text.splitlines()
        namespace = self._path_namespace(relative_path)

        for symbol in parsed.classes:
            result.symbols.append(
                self._tree_sitter_symbol(
                    symbol,
                    namespace,
                    "CLASS",
                    lines,
                    language
                )
            )

        for symbol in parsed.interfaces:
            result.symbols.append(
                self._tree_sitter_symbol(
                    symbol,
                    namespace,
                    "INTERFACE",
                    lines,
                    language
                )
            )

        for symbol in parsed.enums:
            result.symbols.append(
                self._tree_sitter_symbol(
                    symbol,
                    namespace,
                    "ENUM",
                    lines,
                    language
                )
            )

        for symbol in parsed.methods:
            result.symbols.append(
                self._tree_sitter_symbol(
                    symbol,
                    namespace,
                    "METHOD",
                    lines,
                    language
                )
            )

        for symbol in parsed.functions:
            result.symbols.append(
                self._tree_sitter_symbol(
                    symbol,
                    namespace,
                    "FUNCTION",
                    lines,
                    language
                )
            )

        return result

    def _tree_sitter_symbol(
        self,
        symbol,
        namespace: str,
        symbol_type: str,
        lines: list[str],
        language: str
    ) -> ExtractedSymbol:

        parent = getattr(symbol, "parent", None)
        parent_qualified_name = (
            f"{namespace}.{parent}"
            if parent
            else None
        )
        qualified_name = ".".join(
            part for part in [
                parent_qualified_name or namespace,
                symbol.name
            ]
            if part
        )
        start = getattr(symbol, "line_start", 1)
        end = getattr(symbol, "line_end", start)
        source_lines = lines[start - 1:end]

        return ExtractedSymbol(
            name=symbol.name,
            qualified_name=qualified_name,
            symbol_type=symbol_type,
            start_line=start,
            end_line=end,
            signature=getattr(symbol, "signature", "") or (
                source_lines[0].strip()
                if source_lines
                else symbol.name
            ),
            parent_qualified_name=parent_qualified_name,
            metadata={
                "language": language,
                "parser": "tree-sitter"
            },
            source_hash=self._source_hash(source_lines)
        )

    def _extract_python(
        self,
        text: str,
        relative_path: str
    ) -> ExtractionResult:

        result = ExtractionResult()
        tree = ast.parse(text)
        lines = text.splitlines()

        visitor = _PythonSymbolVisitor(
            result=result,
            namespace=self._path_namespace(relative_path),
            lines=lines,
            extractor=self
        )
        visitor.visit(tree)

        return result

    def _python_symbol(
        self,
        node,
        symbol_type: str,
        relative_path: str,
        lines: list[str]
    ) -> ExtractedSymbol:

        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        parent = getattr(node, "_parent_qualified_name", None)
        qualified_name = ".".join(
            part for part in [
                self._path_namespace(relative_path),
                parent,
                node.name
            ]
            if part
        )

        signature = lines[start - 1].strip() if lines else None

        return ExtractedSymbol(
            name=node.name,
            qualified_name=qualified_name,
            symbol_type=symbol_type.upper(),
            start_line=start,
            end_line=end,
            signature=signature,
            parent_qualified_name=parent,
            metadata={"decorators": self._python_decorators(node)},
            source_hash=self._source_hash(lines[start - 1:end])
        )

    def _python_decorators(self, node) -> list[str]:

        return [
            self._python_name(decorator) or ast.dump(decorator)
            for decorator in getattr(node, "decorator_list", [])
        ]

    def _python_name(self, node) -> str | None:

        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            parent = self._python_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr

        if isinstance(node, ast.Call):
            return self._python_name(node.func)

        return None

    def _is_python_test(self, node) -> bool:

        return node.name.startswith("test_")

    def _extract_brace_language(
        self,
        text: str,
        relative_path: str,
        language: str
    ) -> ExtractionResult:

        result = ExtractionResult()
        lines = text.splitlines()
        namespace = self._path_namespace(relative_path)
        imports = self._brace_imports(lines)

        class_pattern = re.compile(
            r"\b(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"
            r"(?:\s+extends\s+([A-Za-z_][A-Za-z0-9_.$]*))?"
            r"(?:\s+implements\s+([A-Za-z_][A-Za-z0-9_.$,\s]*))?"
        )
        method_pattern = re.compile(
            r"(?:public|private|protected|static|async|final|abstract|\s)+"
            r"[A-Za-z_<>\[\].?]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{"
        )
        function_pattern = re.compile(
            r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("
        )
        arrow_function_pattern = re.compile(
            r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*="
            r"\s*(?:async\s*)?\([^)]*\)\s*=>"
        )

        current_class: ExtractedSymbol | None = None

        for index, line in enumerate(lines, start=1):
            class_match = class_pattern.search(line)
            if class_match:
                name = class_match.group(2)
                current_class = ExtractedSymbol(
                    name=name,
                    qualified_name=f"{namespace}.{name}",
                    symbol_type=class_match.group(1).upper(),
                    start_line=index,
                    end_line=self._brace_end(lines, index),
                    signature=line.strip(),
                    metadata={"language": language},
                    source_hash=self._source_hash([line])
                )
                result.symbols.append(current_class)
                self._add_uses_relationships(
                    result,
                    current_class.qualified_name,
                    imports,
                    language
                )

                if class_match.group(3):
                    result.relationships.append(
                        ExtractedRelationship(
                            source_qualified_name=current_class.qualified_name,
                            target_name=class_match.group(3),
                            relationship_type="EXTENDS",
                            confidence=0.8
                        )
                    )

                for target in self._split_targets(class_match.group(4)):
                    result.relationships.append(
                        ExtractedRelationship(
                            source_qualified_name=current_class.qualified_name,
                            target_name=target,
                            relationship_type="IMPLEMENTS",
                            confidence=0.8
                        )
                    )

            method_match = (
                method_pattern.search(line)
                or function_pattern.search(line)
                or arrow_function_pattern.search(line)
            )
            if method_match:
                name = method_match.group(1)
                parent_name = (
                    current_class.qualified_name
                    if current_class
                    and current_class.start_line <= index <= current_class.end_line
                    else None
                )
                qualified_name = ".".join(
                    part for part in [
                        parent_name or namespace,
                        name
                    ]
                    if part
                )
                symbol = ExtractedSymbol(
                    name=name,
                    qualified_name=qualified_name,
                    symbol_type="METHOD" if parent_name else "FUNCTION",
                    parent_qualified_name=parent_name,
                    start_line=index,
                    end_line=self._brace_end(lines, index),
                    signature=line.strip(),
                    metadata={"language": language},
                    source_hash=self._source_hash(
                        lines[index - 1:self._brace_end(lines, index)]
                    )
                )
                result.symbols.append(symbol)
                self._add_uses_relationships(
                    result,
                    qualified_name,
                    imports,
                    language
                )

                if self._is_test_name(name, relative_path):
                    result.tests.append(
                        ExtractedTest(
                            name=name,
                            symbol_qualified_name=qualified_name,
                            framework=self._test_framework(language),
                            target_name=self._infer_test_target(name),
                            metadata={"language": language}
                        )
                    )

                for target in self._call_targets(line):
                    if target != name:
                        result.relationships.append(
                            ExtractedRelationship(
                                source_qualified_name=qualified_name,
                                target_name=target,
                                relationship_type="CALLS",
                                confidence=0.5
                            )
                        )

                for target in self._new_targets(line):
                    result.relationships.append(
                        ExtractedRelationship(
                            source_qualified_name=qualified_name,
                            target_name=target,
                            relationship_type="USES",
                            confidence=0.6,
                            metadata={"language": language}
                        )
                    )

        return result

    def _brace_imports(
        self,
        lines: list[str]
    ) -> list[str]:

        imports = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("import "):
                imports.extend(
                    self._import_targets_from_line(stripped)
                )

        return imports

    def _import_targets_from_line(
        self,
        line: str
    ) -> list[str]:

        line = line.replace(";", "")

        if line.startswith("import type "):
            line = line.replace("import type ", "import ", 1)

        if " from " in line:
            imported, module = line[len("import "):].split(" from ", 1)
            module = module.strip("'\" ")
            names = re.findall(
                r"[A-Za-z_][A-Za-z0-9_]*",
                imported
            )
            return [
                f"{module}.{name}"
                for name in names
                if name not in {"import", "as"}
            ] or [module]

        target = line[len("import "):].strip()
        if target.endswith(".*"):
            return [target[:-2]]

        return [target]

    def _add_uses_relationships(
        self,
        result: ExtractionResult,
        source_qualified_name: str,
        imports: list[str],
        language: str
    ) -> None:

        for target in imports:
            result.relationships.append(
                ExtractedRelationship(
                    source_qualified_name=source_qualified_name,
                    target_name=target,
                    relationship_type="USES",
                    confidence=0.45,
                    metadata={"language": language, "source": "import"}
                )
            )

    def _brace_end(
        self,
        lines: list[str],
        start_line: int
    ) -> int:

        depth = 0
        seen_open = False

        for offset, line in enumerate(lines[start_line - 1:], start=start_line):
            depth += line.count("{")
            if "{" in line:
                seen_open = True
            depth -= line.count("}")

            if seen_open and depth <= 0:
                return offset

        return start_line

    def _call_targets(self, line: str) -> list[str]:

        keywords = {
            "if",
            "for",
            "while",
            "switch",
            "catch",
            "return",
            "new"
        }

        return [
            target for target in re.findall(
                r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(",
                line
            )
            if target not in keywords
        ]

    def _new_targets(self, line: str) -> list[str]:

        return re.findall(
            r"\bnew\s+([A-Za-z_][A-Za-z0-9_.$]*)\s*\(",
            line
        )

    def _split_targets(
        self,
        value: str | None
    ) -> list[str]:

        if not value:
            return []

        return [
            target.strip()
            for target in value.split(",")
            if target.strip()
        ]

    def _is_test_name(
        self,
        name: str,
        relative_path: str
    ) -> bool:

        return (
            name.startswith("test")
            or name.endswith("Test")
            or "test" in relative_path.lower()
        )

    def _test_framework(
        self,
        language: str
    ) -> str | None:

        return {
            "java": "junit",
            "javascript": "jest",
            "typescript": "jest"
        }.get(language)

    def _infer_test_target(
        self,
        test_name: str
    ) -> str | None:

        normalized = test_name

        if normalized.startswith("test_"):
            normalized = normalized[len("test_"):]
        elif normalized.startswith("test"):
            normalized = normalized[len("test"):]

        if normalized.endswith("Test"):
            normalized = normalized[:-len("Test")]

        normalized = normalized.strip("_")

        return normalized or None

    def _path_namespace(
        self,
        relative_path: str
    ) -> str:

        path = Path(relative_path)
        return ".".join(path.with_suffix("").parts)

    def _source_hash(
        self,
        lines: list[str]
    ) -> str:

        return hashlib.sha256(
            "\n".join(lines).encode("utf-8")
        ).hexdigest()


class _PythonSymbolVisitor(ast.NodeVisitor):

    def __init__(
        self,
        result: ExtractionResult,
        namespace: str,
        lines: list[str],
        extractor: SymbolExtractor
    ):

        self.result = result
        self.namespace = namespace
        self.lines = lines
        self.extractor = extractor
        self.symbol_stack: list[ExtractedSymbol] = []
        self.import_targets: list[str] = []

    def visit_Import(
        self,
        node: ast.Import
    ) -> None:

        for alias in node.names:
            self.import_targets.append(alias.name)

    def visit_ImportFrom(
        self,
        node: ast.ImportFrom
    ) -> None:

        module = node.module or ""

        for alias in node.names:
            if alias.name == "*":
                self.import_targets.append(module)
            else:
                self.import_targets.append(
                    ".".join(
                        part for part in [
                            module,
                            alias.name
                        ]
                        if part
                    )
                )

    def visit_ClassDef(
        self,
        node: ast.ClassDef
    ) -> None:

        symbol = self._symbol(
            node=node,
            symbol_type="CLASS"
        )
        self.result.symbols.append(symbol)

        for base in node.bases:
            target = self.extractor._python_name(base)
            if target:
                self.result.relationships.append(
                    ExtractedRelationship(
                        source_qualified_name=symbol.qualified_name,
                        target_name=target,
                        relationship_type="EXTENDS",
                        confidence=0.9
                    )
                )

        self.symbol_stack.append(symbol)
        self._emit_import_uses(symbol)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef
    ) -> None:

        self._visit_function(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef
    ) -> None:

        self._visit_function(node)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:

        symbol_type = (
            "METHOD"
            if self.symbol_stack
            and self.symbol_stack[-1].symbol_type == "CLASS"
            else "FUNCTION"
        )
        symbol = self._symbol(
            node=node,
            symbol_type=symbol_type
        )
        self.result.symbols.append(symbol)
        self._emit_import_uses(symbol)

        if self.extractor._is_python_test(node):
            self.result.tests.append(
                ExtractedTest(
                    name=symbol.name,
                    symbol_qualified_name=symbol.qualified_name,
                    framework="pytest",
                    target_name=self.extractor._infer_test_target(
                        symbol.name
                    ),
                    metadata={"language": "python"}
                )
            )

        self.symbol_stack.append(symbol)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_Name(
        self,
        node: ast.Name
    ) -> None:

        if self.symbol_stack and isinstance(node.ctx, ast.Load):
            self._emit_uses(
                target_name=node.id,
                confidence=0.35,
                metadata={"language": "python", "source": "name"}
            )

        self.generic_visit(node)

    def visit_Call(
        self,
        node: ast.Call
    ) -> None:

        if self.symbol_stack:
            target = self.extractor._python_name(node.func)

            if target:
                self.result.relationships.append(
                    ExtractedRelationship(
                        source_qualified_name=(
                            self.symbol_stack[-1].qualified_name
                        ),
                        target_name=target,
                        relationship_type="CALLS",
                        confidence=0.8,
                        metadata={"language": "python"}
                    )
                )

        self.generic_visit(node)

    def _emit_import_uses(
        self,
        symbol: ExtractedSymbol
    ) -> None:

        for target in self.import_targets:
            self.result.relationships.append(
                ExtractedRelationship(
                    source_qualified_name=symbol.qualified_name,
                    target_name=target,
                    relationship_type="USES",
                    confidence=0.45,
                    metadata={"language": "python", "source": "import"}
                )
            )

    def _emit_uses(
        self,
        target_name: str,
        confidence: float,
        metadata: dict
    ) -> None:

        self.result.relationships.append(
            ExtractedRelationship(
                source_qualified_name=self.symbol_stack[-1].qualified_name,
                target_name=target_name,
                relationship_type="USES",
                confidence=confidence,
                metadata=metadata
            )
        )

    def _symbol(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        symbol_type: str
    ) -> ExtractedSymbol:

        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        parent = (
            self.symbol_stack[-1].qualified_name
            if self.symbol_stack
            else None
        )
        qualified_name = ".".join(
            part for part in [
                parent or self.namespace,
                node.name
            ]
            if part
        )
        signature = (
            self.lines[start - 1].strip()
            if self.lines and start <= len(self.lines)
            else None
        )

        return ExtractedSymbol(
            name=node.name,
            qualified_name=qualified_name,
            symbol_type=symbol_type,
            start_line=start,
            end_line=end,
            signature=signature,
            parent_qualified_name=parent,
            metadata={
                "decorators": self.extractor._python_decorators(node),
                "language": "python"
            },
            source_hash=self.extractor._source_hash(
                self.lines[start - 1:end]
            )
        )
