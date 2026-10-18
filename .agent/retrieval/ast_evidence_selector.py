# .agent/retrieval/ast_evidence_selector.py
"""AST-aware method and call-site selection for retrieved code."""
from dataclasses import dataclass
from typing import List, Set, Union, Iterable, Optional
import ast
import re
from pathlib import Path


@dataclass
class EvidenceSpan:
    file_path: str
    symbol_name: str
    start_line: int
    end_line: int
    content: str
    score: float
    evidence_type: str = "implementation"


class ASTEvidenceSelector:
    """
    Discovers, scores, and extracts source-grounded code spans using AST.
    Handles long methods by producing bounded, noncontiguous spans around
    signatures, endpoint requests, and streaming call sites.
    """

    def _split_tokens(self, text: str) -> Set[str]:
        words = re.findall(r"[a-zA-Z0-9]+", text)
        tokens = set()
        for w in words:
            parts = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z0-9]|\b)", w)
            if parts:
                tokens.update(p.lower() for p in parts if len(p) >= 2)
            elif len(w) >= 2:
                tokens.add(w.lower())
        return tokens

    def _extract_query_terms(self, query: Union[str, Set[str], Iterable[str]]) -> Set[str]:
        if isinstance(query, str):
            raw_tokens = self._split_tokens(query)
        else:
            raw_tokens = set()
            for q in query:
                raw_tokens.update(self._split_tokens(str(q)))

        stopwords = {
            "how", "does", "and", "the", "what", "where", "why",
            "who", "with", "from", "into", "can", "tell", "about",
            "show", "explain", "is", "are", "was", "were", "in",
            "to", "of", "for", "a", "an", "this", "that"
        }
        terms = {t for t in raw_tokens if t not in stopwords and len(t) >= 2}
        stemmed = set(terms)
        for t in terms:
            if t.endswith("s") and len(t) > 3 and not t.endswith("ss"):
                stemmed.add(t[:-1])
            elif t.endswith("ed") and len(t) > 4:
                stemmed.add(t[:-2])
            elif t.endswith("ing") and len(t) > 5:
                stemmed.add(t[:-3])
        return stemmed

    @staticmethod
    def _spans_overlap(s1: EvidenceSpan, s2: EvidenceSpan) -> bool:
        if s1.file_path != s2.file_path:
            return False
        return not (s1.end_line < s2.start_line or s2.end_line < s1.start_line)

    def _identify_requested_categories(
        self,
        query: Union[str, Set[str], Iterable[str]],
        query_terms: Set[str],
    ) -> List[str]:
        q_text = query if isinstance(query, str) else " ".join(str(x) for x in query)
        q_low = q_text.lower()

        endpoint_keywords = {
            "call", "called", "calling", "endpoint", "endpoints", "api", "apis",
            "url", "urls", "http", "https", "request", "requests", "post", "get",
            "put", "delete", "route", "routes", "invoke", "invoking", "network", "client"
        }
        callback_keywords = {
            "stream", "streamed", "streaming", "callback", "callbacks", "chunk",
            "chunks", "event", "events", "listen", "listener", "yield", "generator",
            "async", "iter", "iterator"
        }

        has_endpoint = bool(query_terms & endpoint_keywords) or any(
            k in q_low for k in ["/api/", "endpoint", "http", "url", "request"]
        )
        has_callback = bool(query_terms & callback_keywords) or any(
            k in q_low for k in ["stream", "callback"]
        )

        requested = ["signature"]
        if has_endpoint:
            requested.append("endpoint")
        if has_callback:
            requested.append("callback")
        if not has_endpoint and not has_callback:
            requested.extend(["call", "method"])
        elif len(requested) < 3:
            requested.extend(["call", "method"])
        return requested

    def _select_query_aware_spans(
        self,
        candidates: List[EvidenceSpan],
        max_spans: int,
        query: Union[str, Set[str], Iterable[str]],
        query_terms: Set[str],
    ) -> List[EvidenceSpan]:
        """
        Query-aware evidence coverage selection:
        1. Rank executable call sites and symbols.
        2. Identify evidence categories relevant to the query.
        3. Prefer spans belonging to the same relevant method.
        4. Cover distinct requested operations before filling remaining slots.
        5. Deduplicate overlapping source ranges.
        """
        if max_spans <= 0 or not candidates:
            return []

        requested_categories = self._identify_requested_categories(query, query_terms)

        # 1. Rank symbols and group spans by symbol
        symbols_map: dict = {}
        for c in candidates:
            symbols_map.setdefault(c.symbol_name, []).append(c)

        # Rank symbols: prefer the primary method with the strongest relevant evidence
        ranked_symbols = sorted(
            symbols_map.keys(),
            key=lambda sym: (
                max(s.score for s in symbols_map[sym]),
                sum(s.score for s in symbols_map[sym]),
            ),
            reverse=True,
        )

        selected: List[EvidenceSpan] = []

        def can_add(span: EvidenceSpan) -> bool:
            for existing in selected:
                if self._spans_overlap(span, existing):
                    return False
            return True

        covered_categories: Set[str] = set()

        # Step 1: Cover distinct requested categories from the primary relevant method(s) (Rules 2, 3, 4, 5)
        for sym in ranked_symbols:
            sym_spans = symbols_map[sym]
            for cat in requested_categories:
                if cat in covered_categories:
                    continue
                cat_spans = [s for s in sym_spans if s.evidence_type == cat]
                cat_spans.sort(key=lambda s: (-s.score, s.start_line))
                for span in cat_spans:
                    if can_add(span):
                        selected.append(span)
                        covered_categories.add(cat)
                        break
                if len(selected) >= max_spans:
                    break
            if len(selected) >= max_spans:
                break

        # Step 2: If any requested categories are not yet covered, cover from any candidate
        if len(selected) < max_spans:
            for cat in requested_categories:
                if cat in covered_categories:
                    continue
                cat_spans = [s for s in candidates if s.evidence_type == cat]
                cat_spans.sort(key=lambda s: (-s.score, s.start_line))
                for span in cat_spans:
                    if can_add(span):
                        selected.append(span)
                        covered_categories.add(cat)
                        break
                if len(selected) >= max_spans:
                    break

        # Step 3: Fill remaining slots preferring the primary method first
        if len(selected) < max_spans:
            for sym in ranked_symbols:
                sym_spans = sorted(symbols_map[sym], key=lambda s: (-s.score, s.start_line))
                for span in sym_spans:
                    if can_add(span):
                        selected.append(span)
                        if len(selected) >= max_spans:
                            break
                if len(selected) >= max_spans:
                    break

        # Step 4: Fill any remaining slots from remaining candidates
        if len(selected) < max_spans:
            all_remaining = sorted(candidates, key=lambda s: (-s.score, s.start_line))
            for span in all_remaining:
                if can_add(span):
                    selected.append(span)
                    if len(selected) >= max_spans:
                        break

        # Return sorted by line order within the file
        selected.sort(key=lambda s: (s.file_path, s.start_line))
        return selected

    def _select_diverse_spans(
        self,
        candidates: List[EvidenceSpan],
        max_spans: int,
    ) -> List[EvidenceSpan]:
        """Legacy diversity selection fallback."""
        return self._select_query_aware_spans(
            candidates=candidates,
            max_spans=max_spans,
            query="",
            query_terms=set(),
        )

    def select_python(
        self,
        file_path: str,
        source: str,
        query: Union[str, Set[str], Iterable[str]],
        max_spans: int = 3,
        max_lines: int = 25,
    ) -> List[EvidenceSpan]:
        try:
            tree = ast.parse(source)
        except Exception:
            return []

        lines = source.splitlines()
        query_terms = self._extract_query_terms(query)
        if not query_terms:
            return []

        class_map = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        class_map[sub] = node.name

        candidates: List[EvidenceSpan] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            start = node.lineno
            end = node.end_lineno
            cls_name = class_map.get(node, "")
            symbol_name = f"{cls_name}.{node.name}" if cls_name else node.name

            # 1. Rank symbol name
            name_tokens = set(
                re.findall(
                    r"[a-z]+",
                    re.sub(r"([a-z])([A-Z])", r"\1 \2", symbol_name).lower(),
                )
            )
            name_score = len(query_terms & name_tokens) * 5.0

            # 2. Parameters
            param_score = 0.0
            for arg in node.args.args + node.args.kwonlyargs:
                if query_terms & self._split_tokens(arg.arg):
                    param_score += 4.0

            # 3. Call expressions and executable statements
            call_names = []
            focal_operations = []

            for child in ast.walk(node):
                c_start = getattr(child, "lineno", start)
                c_end = getattr(child, "end_lineno", c_start)

                if isinstance(child, ast.Call):
                    try:
                        func_str = ast.unparse(child.func).lower()
                        call_names.append(func_str)
                    except Exception:
                        func_str = ""

                    c_weight = 0.0
                    call_toks = self._split_tokens(func_str)
                    if query_terms & call_toks:
                        c_weight += 5.0

                    for kw in child.keywords:
                        if kw.arg and (query_terms & self._split_tokens(kw.arg)):
                            c_weight += 4.0
                        if isinstance(kw.value, ast.Name) and (query_terms & self._split_tokens(kw.value.id)):
                            c_weight += 4.0

                    for a in child.args:
                        if isinstance(a, ast.Constant) and isinstance(a.value, str):
                            a_lower = a.value.lower()
                            if query_terms & self._split_tokens(a_lower):
                                c_weight += 4.0
                            if "/api/" in a_lower:
                                c_weight += 6.0

                    if c_weight > 0:
                        focal_operations.append((c_start, c_end, c_weight, func_str))

                elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                    val = getattr(child, "value", None)
                    v_str = ""
                    if isinstance(val, ast.JoinedStr):
                        try:
                            v_str = ast.unparse(val).lower()
                        except Exception:
                            pass
                    elif isinstance(val, ast.Constant) and isinstance(val.value, str):
                        v_str = val.value.lower()
                    if v_str and ("/api/" in v_str or (query_terms & self._split_tokens(v_str))):
                        focal_operations.append((c_start, c_end, 6.0, v_str))

                elif isinstance(child, (ast.If, ast.While, ast.For)):
                    test = getattr(child, "test", None)
                    if test:
                        for test_sub in ast.walk(test):
                            if isinstance(test_sub, ast.Name) and (query_terms & self._split_tokens(test_sub.id)):
                                focal_operations.append((c_start, c_end, 4.0, test_sub.id))

            call_tokens = self._split_tokens(" ".join(call_names))
            call_score = (
                3.0 * len(query_terms & call_tokens)
                + sum(op[2] for op in focal_operations)
            )

            body = "\n".join(lines[start - 1 : end])
            body_score = sum(
                0.5 for term in query_terms
                if term in body.lower()
            )

            total_score = name_score + param_score + call_score + body_score
            if total_score <= 0:
                continue

            # Check if function fits within max_lines
            if end - start + 1 <= max_lines:
                candidates.append(
                    EvidenceSpan(
                        file_path=file_path,
                        symbol_name=symbol_name,
                        start_line=start,
                        end_line=end,
                        content="\n".join(lines[start - 1 : end]),
                        score=total_score,
                        evidence_type="method",
                    )
                )
            else:
                # Large function: extract bounded noncontiguous source spans!
                # Span A: Enclosing method signature and parameters
                sig_end = node.body[0].lineno - 1 if node.body else start
                sig_end = min(end, max(start, sig_end))
                sig_lines = sig_end - start + 1
                if sig_lines <= max_lines:
                    candidates.append(
                        EvidenceSpan(
                            file_path=file_path,
                            symbol_name=symbol_name,
                            start_line=start,
                            end_line=sig_end,
                            content="\n".join(lines[start - 1 : sig_end]),
                            score=name_score + param_score + 10.0,
                            evidence_type="signature",
                        )
                    )

                # Cluster focal operations
                if focal_operations:
                    sorted_ops = sorted(focal_operations, key=lambda x: x[0])
                    clusters = []
                    cur = []
                    for op in sorted_ops:
                        if not cur:
                            cur.append(op)
                        else:
                            prev_op = cur[-1]
                            gap = op[0] - prev_op[1]
                            total_span = op[1] - cur[0][0] + 1
                            if gap <= 3 and total_span <= max_lines:
                                cur.append(op)
                            else:
                                clusters.append(cur)
                                cur = [op]
                    if cur:
                        clusters.append(cur)

                    for cluster in clusters:
                        min_l = min(op[0] for op in cluster)
                        max_l = max(op[1] for op in cluster)

                        s_line = max(start, min_l - 1)
                        e_line = min(end, max(max_l + 4, s_line + 6))
                        if e_line - s_line + 1 > max_lines:
                            e_line = min(end, s_line + max_lines - 1)

                        cl_score = sum(op[2] for op in cluster) + name_score

                        cluster_text = " ".join(
                            str(op[3]).lower()
                            for op in cluster
                        )
                        if "/api/" in cluster_text:
                            evidence_type = "endpoint"
                        elif "stream" in cluster_text or "callback" in cluster_text:
                            evidence_type = "callback"
                        else:
                            evidence_type = "call"

                        candidates.append(
                            EvidenceSpan(
                                file_path=file_path,
                                symbol_name=symbol_name,
                                start_line=s_line,
                                end_line=e_line,
                                content="\n".join(lines[s_line - 1 : e_line]),
                                score=cl_score,
                                evidence_type=evidence_type,
                            )
                        )

        return self._select_query_aware_spans(
            candidates=candidates,
            max_spans=max_spans,
            query=query,
            query_terms=query_terms,
        )

    def select_spans(
        self,
        file_path: str,
        source: str,
        query_terms: Union[Set[str], Iterable[str], str],
        max_spans: int = 3,
        max_lines: int = 25,
    ) -> List[EvidenceSpan]:
        """Alias for select_python."""
        return self.select_python(
            file_path=file_path,
            source=source,
            query=query_terms,
            max_spans=max_spans,
            max_lines=max_lines,
        )

    def select_evidence(
        self,
        file_path: str,
        source: str,
        query_terms: Union[Set[str], Iterable[str], str],
        max_spans: int = 3,
        max_lines: int = 25,
    ) -> List[EvidenceSpan]:
        """Alias for select_python."""
        return self.select_python(
            file_path=file_path,
            source=source,
            query=query_terms,
            max_spans=max_spans,
            max_lines=max_lines,
        )


# Backward compatibility alias
AstEvidenceSelector = ASTEvidenceSelector
