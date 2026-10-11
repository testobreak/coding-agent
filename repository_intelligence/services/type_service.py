# repository_intelligence/services/type_service.py
"""
Service wrapper around the Java ``TypeResolver`` static analyzer.
Provides a convenient API for other components (e.g., SymbolResolver) to
query variable types within a Java source file.
"""

from pathlib import Path
from typing import Optional

from repository_intelligence.parsers.java_type_resolver import TypeResolver

class TypeService:
    """Facade for accessing the Java TypeResolver.

    The service is lightweight; it lazily creates a ``TypeResolver`` instance
    and reuses it across calls, caching per‑file symbol tables.
    """

    def __init__(self) -> None:
        self._resolver = TypeResolver()

    def get_variable_type(self, variable_name: str, file_path: str, source: Optional[str] = None) -> Optional[str]:
        """Return the declared type of ``variable_name`` in ``file_path``.

        ``source`` can be provided to avoid reading the file again when the
        caller already has the file contents.
        """
        # Resolve relative to project root if necessary
        absolute_path = str(Path(file_path).resolve())
        return self._resolver.resolve_variable_type(variable_name, absolute_path, source)

# End of file
