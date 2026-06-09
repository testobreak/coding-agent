# parsers/registry.py
#
# Central parser registry.
# Returns the correct parser for a given language string or file path.
#

from typing import Optional
from parsers.base import ParsedFile


class ParserRegistry:
    """
    Lazy-loads parsers on first use to avoid importing all grammars
    until they are actually needed.
    """

    def __init__(self):
        self._parsers = {}

    def _load(self, lang: str):
        if lang not in self._parsers:
            if lang == "java":
                from parsers.java_parser import JavaParser
                self._parsers[lang] = JavaParser()
            elif lang == "python":
                from parsers.python_parser import PythonParser
                self._parsers[lang] = PythonParser()
            elif lang == "javascript":
                from parsers.js_parser import JavaScriptParser
                self._parsers[lang] = JavaScriptParser()
            elif lang in ("typescript", "tsx"):
                from parsers.ts_parser import TypeScriptParser
                self._parsers[lang] = TypeScriptParser()
            else:
                return None
        return self._parsers[lang]

    def parse_file(self, path: str, language: str) -> Optional[ParsedFile]:
        """
        Parse a file using the appropriate parser.
        Returns None for unsupported languages.
        """
        parser = self._load(language)
        if parser is None:
            return None

        if language == "tsx":
            # TypeScriptParser.parse_file detects tsx from extension
            return parser.parse_file(path)

        return parser.parse_file(path)

    def supports(self, language: str) -> bool:
        return language in ("java", "python", "javascript", "typescript", "tsx")


# Singleton
registry = ParserRegistry()
