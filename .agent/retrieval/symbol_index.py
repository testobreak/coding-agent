# retrieval/symbol_index.py
"""Inverted symbol index for fast exact-match symbol lookups.

Provides O(1) symbol-to-chunk resolution as a complement to vector
similarity search.  The index maps lowercased symbol tokens to the
chunks that define them so that a query mentioning e.g.
``EmployeeService`` can instantly retrieve the right chunk without
embedding round-trips.

Return format mirrors ``FaissVectorStore.search`` —
``{'score': float, 'chunk': dict}`` — so consumers can merge results
from both stores transparently.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CAMEL_BOUNDARY = re.compile(
    r"""
    (?<=[a-z])(?=[A-Z])        # lowerUPPER boundary
    | (?<=[A-Z])(?=[A-Z][a-z]) # UPPERUpper boundary (e.g. HTMLParser -> HTML, Parser)
    """,
    re.VERBOSE,
)

_SYMBOL_PATTERNS = re.compile(
    r"""
    "[^"]+"                   # double-quoted strings
    | '[^']+'                 # single-quoted strings
    | [A-Za-z_]\w*            # identifiers (CamelCase, snake_case, …)
    (?:\.[A-Za-z_]\w*)*       # optional dotted tail  (com.example.Foo)
    """,
    re.VERBOSE,
)


def _split_camel(name: str) -> List[str]:
    """Split a CamelCase or PascalCase identifier into sub-components.

    >>> _split_camel('EmployeeService')
    ['Employee', 'Service']
    >>> _split_camel('HTMLParser')
    ['HTML', 'Parser']
    >>> _split_camel('simple')
    ['simple']
    """
    parts = _CAMEL_BOUNDARY.split(name)
    return [p for p in parts if p]


def _file_basename(path: str) -> Optional[str]:
    """Return the file basename without extension, or *None* for empty paths.

    >>> _file_basename('src/main/EmployeeService.java')
    'EmployeeService'
    """
    if not path:
        return None
    base = os.path.basename(path)
    stem, _ = os.path.splitext(base)
    return stem if stem else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_symbols(query: str) -> List[str]:
    """Pull symbol-like tokens out of a free-text query using SYMBOL_PATTERN."""
    SYMBOL_PATTERN = r'\b[A-Z][A-Za-z0-9_]+\b'
    raw = re.findall(SYMBOL_PATTERN, query)
    
    # Deduplicate while preserving order
    seen = set()
    return [x for x in raw if not (x in seen or seen.add(x))]


class SymbolIndex:
    """Inverted index mapping symbol names → chunks for O(1) lookups.

    Usage::

        idx = SymbolIndex()
        idx.build(chunks)
        results = idx.lookup(['EmployeeService'], k=10)
        # results == [{'score': 1.0, 'chunk': {…}}, …]
    """

    def __init__(self) -> None:
        # Lowercased symbol token  →  list of (chunk, match_tier)
        #   match_tier: 'full' | 'basename' | 'partial'
        self._index: Dict[str, List[tuple]] = defaultdict(list)
        self._built = False

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def build(self, chunks: List[Dict]) -> None:
        """Build the inverted index from a list of chunk dicts.

        Each chunk is expected to carry at least one of:

        * ``symbol`` or ``name``  – the primary symbol identifier
        * ``file``                – source file path
        * ``code`` or ``content`` – the chunk body (unused here but
          preserved in results)

        The method indexes three tiers of tokens for every chunk:

        1. **Full symbol name** (exact match → score 1.0)
        2. **File basename** without extension (→ score 0.9)
        3. **CamelCase sub-components** of the symbol (→ score 0.5)
        """
        self._index.clear()

        for chunk in chunks:
            symbol: str = chunk.get("symbol") or chunk.get("name") or ""
            file_path: str = chunk.get("file", "")

            if not symbol and not file_path:
                continue  # nothing to index

            # --- Tier 1: full symbol name ---
            if symbol:
                key = symbol.lower()
                self._index[key].append((chunk, "full"))

            # --- Tier 2: file basename ---
            basename = _file_basename(file_path)
            if basename:
                bkey = basename.lower()
                # Avoid duplicate entry when basename == symbol
                if not symbol or bkey != symbol.lower():
                    self._index[bkey].append((chunk, "basename"))

            # --- Tier 3: CamelCase sub-components ---
            if symbol:
                parts = _split_camel(symbol)
                # Only index sub-parts when there are at least 2 components;
                # a single component is already covered by the full-name tier.
                if len(parts) > 1:
                    for part in parts:
                        pkey = part.lower()
                        # Skip very short sub-parts (e.g. single letters)
                        if len(pkey) < 2:
                            continue
                        self._index[pkey].append((chunk, "partial"))

        self._built = True

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    _TIER_SCORES = {
        "full": 1.0,
        "basename": 0.9,
        "partial": 0.5,
    }

    def lookup(self, symbols: List[str], k: int = 50) -> List[Dict]:
        """Return chunks matching any of the given *symbols*.

        Parameters
        ----------
        symbols:
            Symbol strings to look up (case-insensitive).
        k:
            Maximum number of results to return.

        Returns
        -------
        list[dict]
            Each entry is ``{'score': float, 'chunk': dict}``, sorted by
            descending score.  The format is identical to
            ``FaissVectorStore.search`` so results can be merged directly.

        Deduplication
        -------------
        If the same chunk is reached through multiple symbols or tiers,
        only the highest-scoring occurrence is kept.
        """
        if not self._built:
            return []

        # chunk id(obj) → best (score, chunk)
        best: Dict[int, tuple] = {}

        for sym in symbols:
            key = sym.lower()
            entries = self._index.get(key, [])
            for chunk, tier in entries:
                score = self._TIER_SCORES[tier]
                cid = id(chunk)
                if cid not in best or score > best[cid][0]:
                    best[cid] = (score, chunk)

        # Sort descending by score, then cap at k.
        ranked = sorted(best.values(), key=lambda t: t[0], reverse=True)[:k]
        return [{"score": score, "chunk": chunk} for score, chunk in ranked]

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def query(self, query_text: str, k: int = 50) -> List[Dict]:
        """End-to-end: extract symbols from *query_text* then look them up.

        A thin wrapper combining :func:`extract_symbols` and
        :meth:`lookup` for callers that start from raw user text.

        >>> idx = SymbolIndex()
        >>> idx.build([{'symbol': 'EmployeeService', 'file': 'Emp.java', 'code': '…'}])
        >>> idx.query('Show me EmployeeService')
        [{'score': 1.0, 'chunk': {...}}]
        """
        syms = extract_symbols(query_text)
        if not syms:
            return []
        return self.lookup(syms, k=k)

    @property
    def size(self) -> int:
        """Number of distinct index keys."""
        return len(self._index)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SymbolIndex keys={self.size} built={self._built}>"
