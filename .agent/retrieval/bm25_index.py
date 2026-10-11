"""
BM25 Okapi lexical search index for code retrieval.

Provides a pure-Python inverted index that scores code chunks against
free-text queries using the BM25 Okapi ranking function.  Tokenization
is tailored for source code: camelCase and snake_case identifiers are
split into sub-tokens, common language keywords are filtered as stop
words, and tokens shorter than 2 characters are discarded.

Usage
-----
>>> idx = BM25Index()
>>> idx.build([
...     {"file": "a.py", "symbol": "EmployeeService", "code": "class EmployeeService: ..."},
... ])
>>> results = idx.search("employee service", k=10)
>>> results[0]
{'score': 1.23, 'chunk': {'file': 'a.py', ...}}
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Stop words – common language keywords that carry little retrieval signal
# ---------------------------------------------------------------------------
_CODE_STOP_WORDS: frozenset[str] = frozenset(
    {
        "def",
        "class",
        "import",
        "return",
        "self",
        "this",
        "public",
        "private",
        "static",
        "void",
        "new",
        "var",
        "let",
        "const",
        "function",
    }
)

# Pre-compiled patterns used by the tokenizer
_CAMEL_BOUNDARY = re.compile(
    r"""
    (?<=[a-z])(?=[A-Z])       # aB  -> a | B
    | (?<=[A-Z])(?=[A-Z][a-z]) # ABc -> A | Bc
    """,
    re.VERBOSE,
)
_NON_ALPHA = re.compile(r"[^a-zA-Z0-9]+")


class BM25Index:
    """BM25 Okapi inverted index over code chunks.

    Parameters
    ----------
    k1 : float
        Term-frequency saturation parameter (default 1.5).
    b : float
        Length-normalisation parameter (default 0.75).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

        # Corpus state – populated by ``build``
        self._chunks: List[Dict] = []
        self._doc_freqs: Counter = Counter()          # term -> number of docs containing term
        self._doc_token_freqs: List[Counter] = []     # per-doc term frequency counters
        self._doc_lengths: List[int] = []             # number of tokens per doc
        self._avgdl: float = 0.0
        self._n_docs: int = 0

    # ------------------------------------------------------------------
    # Tokenisation
    # ------------------------------------------------------------------
    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize *text* into lower-case sub-tokens.

        The method applies three splitting strategies in sequence:

        1. **snake_case** – splits on underscores and other non-alphanumeric
           characters.
        2. **camelCase / PascalCase** – inserts a boundary before each
           upper-case letter that follows a lower-case letter, or before a
           run of upper-case letters followed by a lower-case letter
           (e.g. ``HTMLParser`` → ``HTML``, ``Parser``).
        3. **Short-token filter** – discards any resulting token with fewer
           than 2 characters.

        All tokens are lower-cased and code-specific stop words are removed.

        Parameters
        ----------
        text : str
            Raw text (source code, symbol name, file path …).

        Returns
        -------
        list[str]
            Ordered list of filtered, lower-cased tokens.
        """
        # Step 1: replace non-alphanumeric characters (including '_') with spaces
        text = _NON_ALPHA.sub(" ", text)

        tokens: List[str] = []
        for word in text.split():
            # Step 2: split camelCase / PascalCase boundaries
            parts = _CAMEL_BOUNDARY.split(word)
            for part in parts:
                tok = part.lower()
                if len(tok) >= 2 and tok not in _CODE_STOP_WORDS:
                    tokens.append(tok)

        return tokens

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------
    def build(self, chunks: List[Dict]) -> None:
        """Build the inverted index from a list of code chunks.

        Each chunk is a dictionary that **must** contain a ``'file'`` key and
        **should** contain at least one of the following pairs:

        * ``'symbol'`` or ``'name'`` – the identifier / symbol name.
        * ``'code'`` or ``'content'`` – the source-code body.

        Parameters
        ----------
        chunks : list[dict]
            The corpus of code chunks to index.
        """
        self._chunks = list(chunks)
        self._n_docs = len(self._chunks)
        self._doc_freqs = Counter()
        self._doc_token_freqs = []
        self._doc_lengths = []

        total_length = 0

        for chunk in self._chunks:
            tokens = self._extract_tokens(chunk)
            tf = Counter(tokens)
            self._doc_token_freqs.append(tf)
            self._doc_lengths.append(len(tokens))
            total_length += len(tokens)

            # Update document frequency (each unique term counts once per doc)
            for term in tf:
                self._doc_freqs[term] += 1

        self._avgdl = total_length / self._n_docs if self._n_docs else 0.0

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search(self, query: str, k: int = 50) -> List[Dict]:
        """Retrieve the top-*k* chunks most relevant to *query*.

        Parameters
        ----------
        query : str
            Free-text search query.
        k : int
            Maximum number of results to return (default 50).

        Returns
        -------
        list[dict]
            Ranked list of ``{'score': float, 'chunk': dict}`` dicts,
            ordered by descending BM25 score.  The format matches
            ``FaissVectorStore.search``.
        """
        if not self._chunks:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: List[float] = [0.0] * self._n_docs

        for term in query_tokens:
            if term not in self._doc_freqs:
                continue

            df = self._doc_freqs[term]
            # IDF with the standard BM25 smoothing (non-negative variant)
            idf = math.log(
                (self._n_docs - df + 0.5) / (df + 0.5) + 1.0
            )

            for idx in range(self._n_docs):
                tf = self._doc_token_freqs[idx].get(term, 0)
                if tf == 0:
                    continue
                dl = self._doc_lengths[idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (
                    1.0 - self.b + self.b * dl / self._avgdl
                )
                scores[idx] += idf * numerator / denominator

        # Collect non-zero scores and pick the top-k
        scored = [
            {"score": scores[i], "chunk": self._chunks[i]}
            for i in range(self._n_docs)
            if scores[i] > 0.0
        ]
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _extract_tokens(self, chunk: Dict) -> List[str]:
        """Concatenate and tokenize all textual fields of *chunk*.

        Looks for ``file``, ``symbol``/``name``, and ``code``/``content``
        keys.  Missing keys are silently skipped.
        """
        parts: List[str] = []

        file_path: Optional[str] = chunk.get("file")
        if file_path:
            parts.append(file_path)

        symbol: Optional[str] = chunk.get("symbol") or chunk.get("name")
        if symbol:
            parts.append(symbol)

        code: Optional[str] = chunk.get("code") or chunk.get("content")
        if code:
            parts.append(code)

        return self._tokenize(" ".join(parts))
