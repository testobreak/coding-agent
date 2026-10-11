# retrieval/query_intent.py
from enum import Enum


class RetrievalIntent(str, Enum):
    MODIFY_SYMBOL = "modify_symbol"
    SEARCH = "search"
    EXPLAIN = "explain"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"


def classify_intent(query: str) -> RetrievalIntent:
    q = query.lower()

    if any(x in q for x in ["add", "modify", "update", "change"]):
        return RetrievalIntent.MODIFY_SYMBOL

    if "why" in q or "explain" in q:
        return RetrievalIntent.EXPLAIN

    if "bug" in q or "error" in q:
        return RetrievalIntent.BUG_FIX

    if "refactor" in q or "rename" in q:
        return RetrievalIntent.REFACTOR

    return RetrievalIntent.SEARCH


class RetrievalIntentClassifier:
    @staticmethod
    def classify(prompt: str) -> RetrievalIntent:
        return classify_intent(prompt)


# ── Resolution Mode ──────────────────────────────────────────────────────────
#
# Determines how the QueryResolver will satisfy a developer query:
#
#   SYMBOL  — Query references a known symbol by name. Resolve directly from
#             the in-memory SymbolGraphCache. No ANN embedding needed. (~0 ms)
#
#   GRAPH   — Query asks a structural question (callers, dependencies,
#             implementations, references). Traverse the graph cache. (~1-5 ms)
#
#   SEMANTIC — Fuzzy or conceptual query. No resolvable symbol. Fall back to
#              ANN + BM25 + CandidatePipeline. (~50-200 ms)
#
# Rule: Never run ANN retrieval until structural resolution fails.

class ResolutionMode(str, Enum):
    SYMBOL   = "symbol"
    GRAPH    = "graph"
    SEMANTIC = "semantic"


# Keyword patterns that indicate a graph-structural query.
# Maps pattern → graph operation name consumed by GraphResolver.
GRAPH_OP_PATTERNS = [
    # callers
    (["who calls", "callers of", "what calls", "callers for"],         "callers"),
    # callees
    (["called by", "calls from", "callees of", "what does .* call"],   "callees"),
    # dependencies
    (["dependencies of", "depends on", "imports of", "uses of",
      "what imports", "what does .* depend"],                           "deps"),
    # implementations
    (["implementations of", "classes that implement", "implementors of",
      "who implements", "concrete implementations"],                    "impls"),
    # interfaces / supertypes
    (["inherits from", "extends", "parent of", "supertype of",
      "interfaces of", "what implements"],                              "interfaces"),
    # usages / references
    (["where is .* used", "references to", "usages of",
      "where used", "find usages"],                                     "related"),
]
