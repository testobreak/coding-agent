# .agent/retrieval/tree_sitter_evidence_selector.py
"""Tree-Sitter based AST evidence extraction for Java, TypeScript, and TSX."""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Union, Iterable, Optional, Dict, Tuple
import re

from tree_sitter import Language, Parser
import tree_sitter_java as ts_java
import tree_sitter_typescript as ts_typescript

from retrieval.ast_evidence_selector import EvidenceSpan


class TreeSitterEvidenceSelector:
    """
    AST evidence selector for Java and TypeScript/TSX using Tree-Sitter.
    Extracts bounded, source-grounded spans for signatures, HTTP requests,
    and streaming callbacks.
    """

    def __init__(self):
        self.java_lang = Language(ts_java.language())
        self.ts_lang = Language(ts_typescript.language_typescript())
        self.tsx_lang = Language(ts_typescript.language_tsx())

        self.java_parser = Parser(self.java_lang)
        self.ts_parser = Parser(self.ts_lang)
        self.tsx_parser = Parser(self.tsx_lang)

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
            "put", "delete", "route", "routes", "invoke", "invoking", "network",
            "client", "server"
        }
        callback_keywords = {
            "stream", "streamed", "streaming", "callback", "callbacks", "chunk",
            "chunks", "event", "events", "listen", "listener", "yield", "generator",
            "async", "iter", "iterator", "progress"
        }

        has_endpoint = bool(query_terms & endpoint_keywords) or any(
            k in q_low for k in ["/api/", "endpoint", "http", "url", "request", "server"]
        )
        has_callback = bool(query_terms & callback_keywords) or any(
            k in q_low for k in ["stream", "callback", "progress"]
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

    def _find_symbols(self, node, src_bytes: bytes, lang: str, parent_cls: str = "") -> List[Tuple[str, any, any]]:
        symbols = []
        t = node.type
        cls_name = parent_cls

        if lang == "java":
            if t in ("class_declaration", "interface_declaration", "enum_declaration", "record_declaration"):
                n = node.child_by_field_name("name")
                if n:
                    cls_name = n.text.decode("utf-8", errors="replace").strip()
            elif t in ("method_declaration", "constructor_declaration"):
                n = node.child_by_field_name("name")
                name = n.text.decode("utf-8", errors="replace").strip() if n else "anonymous"
                full_name = f"{cls_name}.{name}" if cls_name else name
                symbols.append((full_name, node, node.child_by_field_name("body")))
        else:
            if t in ("class_declaration", "interface_declaration", "abstract_class_declaration"):
                n = node.child_by_field_name("name")
                if n:
                    cls_name = n.text.decode("utf-8", errors="replace").strip()
            elif t in ("function_declaration", "method_definition"):
                n = node.child_by_field_name("name")
                name = n.text.decode("utf-8", errors="replace").strip() if n else "anonymous"
                full_name = f"{cls_name}.{name}" if cls_name else name
                symbols.append((full_name, node, node.child_by_field_name("body")))
            elif t == "variable_declarator":
                val = node.child_by_field_name("value")
                if val and val.type in ("arrow_function", "function_expression"):
                    n = node.child_by_field_name("name")
                    name = n.text.decode("utf-8", errors="replace").strip() if n else "anonymous"
                    full_name = f"{cls_name}.{name}" if cls_name else name
                    symbols.append((full_name, val, val.child_by_field_name("body")))

        for c in node.children:
            symbols.extend(self._find_symbols(c, src_bytes, lang, cls_name))
        return symbols

    def _find_focal_ops(self, node, src_bytes: bytes, query_terms: Set[str], lang: str) -> List[Tuple[int, int, float, str, str]]:
        ops = []
        t = node.type
        s_line = node.start_point[0] + 1
        e_line = node.end_point[0] + 1

        call_target = ""
        is_call = False
        if lang == "java" and t == "method_invocation":
            is_call = True
            n = node.child_by_field_name("name")
            call_target = n.text.decode("utf-8", errors="replace").strip() if n else ""
        elif lang in ("typescript", "tsx") and t == "call_expression":
            is_call = True
            fn = node.child_by_field_name("function")
            call_target = fn.text.decode("utf-8", errors="replace").strip() if fn else ""

        if is_call:
            call_snippet = node.text.decode("utf-8", errors="replace")[:250].lower()
            weight = 0.0
            call_toks = self._split_tokens(call_target)
            matched = query_terms & call_toks
            if matched:
                weight += len(matched) * 5.0

            op_type = "call"
            if any(k in call_snippet for k in [
                "/api/", "http.request", "https.request", "fetch(", "url(",
                "http://", "https://", "agentclient.", "openconnection",
                "setrequestmethod", ".post(", ".get(", "axios"
            ]):
                weight += 6.0
                op_type = "endpoint"

            if any(k in call_snippet for k in [
                "stream", "callback", "progress", "on('data", "res.on",
                "onprogress", "cb.", "onresponse", "onerror", "subscribe"
            ]):
                weight += 5.0
                op_type = "callback"

            if weight > 0:
                ops.append((s_line, e_line, weight, op_type, call_target))

        for c in node.children:
            ops.extend(self._find_focal_ops(c, src_bytes, query_terms, lang))
        return ops

    def _select_query_aware_spans(
        self,
        candidates: List[EvidenceSpan],
        max_spans: int,
        query: Union[str, Set[str], Iterable[str]],
        query_terms: Set[str],
    ) -> List[EvidenceSpan]:
        if max_spans <= 0 or not candidates:
            return []

        requested_categories = self._identify_requested_categories(query, query_terms)

        symbols_map: Dict[str, List[EvidenceSpan]] = {}
        for c in candidates:
            symbols_map.setdefault(c.symbol_name, []).append(c)

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

        def matches_category(span: EvidenceSpan, cat: str) -> bool:
            if span.evidence_type == cat:
                return True
            if cat == "signature" and span.evidence_type == "method":
                return True
            if cat == "method" and span.evidence_type in ("signature", "method"):
                return True
            return False

        # Step 1: Cover distinct requested categories from primary relevant method(s)
        for sym in ranked_symbols:
            sym_spans = symbols_map[sym]
            for cat in requested_categories:
                if cat in covered_categories:
                    continue
                cat_spans = [s for s in sym_spans if matches_category(s, cat)]
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

        # Step 2: Cover remaining requested categories from any symbol
        if len(selected) < max_spans:
            for cat in requested_categories:
                if cat in covered_categories:
                    continue
                cat_spans = [s for s in candidates if matches_category(s, cat)]
                cat_spans.sort(key=lambda s: (-s.score, s.start_line))
                for span in cat_spans:
                    if can_add(span):
                        selected.append(span)
                        covered_categories.add(cat)
                        break
                if len(selected) >= max_spans:
                    break

        # Step 3: Fill remaining slots preferring the primary method
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

        # Step 4: Fill remaining slots from all remaining candidates
        if len(selected) < max_spans:
            all_remaining = sorted(candidates, key=lambda s: (-s.score, s.start_line))
            for span in all_remaining:
                if can_add(span):
                    selected.append(span)
                    if len(selected) >= max_spans:
                        break

        selected.sort(key=lambda s: (s.file_path, s.start_line))
        return selected

    def select(
        self,
        file_path: str,
        source: str,
        query: Union[str, Set[str], Iterable[str]],
        max_spans: int = 3,
        max_lines: int = 25,
    ) -> List[EvidenceSpan]:
        """
        Discovers, scores, and extracts source-grounded code spans using Tree-Sitter
        for Java, TypeScript, and TSX files.
        """
        ext = Path(file_path).suffix.lower()
        if ext == ".java":
            parser = self.java_parser
            lang = "java"
        elif ext in (".ts", ".js"):
            parser = self.ts_parser
            lang = "typescript"
        elif ext in (".tsx", ".jsx"):
            parser = self.tsx_parser
            lang = "tsx"
        else:
            return []

        src_bytes = source.encode("utf-8")
        try:
            tree = parser.parse(src_bytes)
        except Exception:
            return []

        lines = source.splitlines()
        query_terms = self._extract_query_terms(query)
        if not query_terms:
            return []

        symbols = self._find_symbols(tree.root_node, src_bytes, lang)
        candidates: List[EvidenceSpan] = []

        for symbol_name, node, body_node in symbols:
            start_l = node.start_point[0] + 1
            end_l = node.end_point[0] + 1

            # 1. Name score
            name_tokens = self._split_tokens(symbol_name)
            name_score = len(query_terms & name_tokens) * 5.0

            # 2. Parameters score
            param_score = 0.0
            params_node = node.child_by_field_name("parameters")
            if params_node:
                p_text = params_node.text.decode("utf-8", errors="replace")
                p_tokens = self._split_tokens(p_text)
                param_score += len(query_terms & p_tokens) * 4.0

            # 3. Call sites / operations
            focal_ops = self._find_focal_ops(node, src_bytes, query_terms, lang)
            call_score = sum(op[2] for op in focal_ops)

            # 4. Body score
            body_text = "\n".join(lines[start_l - 1:end_l])
            body_score = sum(0.5 for t in query_terms if t in body_text.lower())

            total_score = name_score + param_score + call_score + body_score
            if total_score <= 0:
                continue

            # Small function fits within max_lines
            if end_l - start_l + 1 <= max_lines:
                ev_type = "method"

                candidates.append(
                    EvidenceSpan(
                        file_path=file_path,
                        symbol_name=symbol_name,
                        start_line=start_l,
                        end_line=end_l,
                        content="\n".join(lines[start_l - 1:end_l]),
                        score=total_score,
                        evidence_type=ev_type,
                    )
                )
            else:
                # Large function: extract bounded signature and focal clusters
                sig_end = start_l
                if body_node:
                    sig_end = min(end_l, max(start_l, body_node.start_point[0] + 1))
                if sig_end - start_l + 1 <= max_lines:
                    candidates.append(
                        EvidenceSpan(
                            file_path=file_path,
                            symbol_name=symbol_name,
                            start_line=start_l,
                            end_line=sig_end,
                            content="\n".join(lines[start_l - 1:sig_end]),
                            score=name_score + param_score + 10.0,
                            evidence_type="signature",
                        )
                    )

                if focal_ops:
                    sorted_ops = sorted(focal_ops, key=lambda x: x[0])
                    clusters = []
                    cur = []
                    for op in sorted_ops:
                        if not cur:
                            cur.append(op)
                        else:
                            prev_op = cur[-1]
                            gap = op[0] - prev_op[1]
                            total_span = op[1] - cur[0][0] + 1
                            if gap <= 4 and total_span <= max_lines:
                                cur.append(op)
                            else:
                                clusters.append(cur)
                                cur = [op]
                    if cur:
                        clusters.append(cur)

                    for cluster in clusters:
                        min_l = min(op[0] for op in cluster)
                        max_l = max(op[1] for op in cluster)
                        s_l = max(start_l, min_l - 1)
                        e_l = min(end_l, max(max_l + 3, s_l + 5))
                        if e_l - s_l + 1 > max_lines:
                            e_l = min(end_l, s_l + max_lines - 1)

                        cl_score = sum(op[2] for op in cluster) + name_score
                        types = [op[3] for op in cluster]
                        if "endpoint" in types:
                            cl_type = "endpoint"
                        elif "callback" in types:
                            cl_type = "callback"
                        else:
                            cl_type = "call"

                        candidates.append(
                            EvidenceSpan(
                                file_path=file_path,
                                symbol_name=symbol_name,
                                start_line=s_l,
                                end_line=e_l,
                                content="\n".join(lines[s_l - 1:e_l]),
                                score=cl_score,
                                evidence_type=cl_type,
                            )
                        )

        return self._select_query_aware_spans(candidates, max_spans, query, query_terms)
