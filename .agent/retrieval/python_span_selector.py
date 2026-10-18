# .agent/retrieval/python_span_selector.py
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Set
import sys
import ast
import re
from pathlib import Path

# Ensure repo root is in sys.path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from repository_intelligence.parsers.python_parser import PythonSymbolLocator


@dataclass
class CodeSpan:
    start_line: int
    end_line: int
    content: str
    symbol_name: Optional[str] = None
    score: float = 0.0


class PythonSpanSelector:
    def __init__(self):
        self.locator = PythonSymbolLocator()
        self._symbol_cache = {}

    def select(
        self,
        file_path: str,
        source: str,
        matched_line: int,
        max_lines: int = 50,
    ) -> Optional[CodeSpan]:
        """Maps a matched source line to the smallest enclosing function or class."""
        cache_key = (file_path, len(source))
        if cache_key not in self._symbol_cache:
            self._symbol_cache[cache_key] = self.locator.extract_symbols(
                file_path, source=source
            )
        symbols = self._symbol_cache[cache_key]
        # Find functions/classes containing the matched line.
        enclosing = [
            symbol for symbol in symbols
            if symbol["start_line"] <= matched_line <= symbol["end_line"]
        ]
        if not enclosing:
            return None
        # Prefer the smallest enclosing symbol.
        symbol = min(
            enclosing,
            key=lambda s: s["end_line"] - s["start_line"]
        )
        start = symbol["start_line"]
        end = symbol["end_line"]
        # Preserve the complete symbol if it fits.
        if end - start + 1 > max_lines:
            # Large method: preserve a region around the match.
            start = max(start, matched_line - 8)
            end = min(end, start + max_lines - 1)
        lines = source.splitlines()
        return CodeSpan(
            start_line=start,
            end_line=end,
            content="\n".join(lines[start - 1:end]),
            symbol_name=symbol["name"],
        )

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r'[A-Za-z0-9]+', text)
        res = []
        for w in words:
            parts = re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z0-9]|\b)', w)
            if parts:
                res.extend([p.lower() for p in parts if len(p) >= 2])
            else:
                if len(w) >= 2:
                    res.append(w.lower())
        return res

    def _normalize_terms(self, terms: List[str]) -> Set[str]:
        res = set()
        for t in terms:
            for sub in self._tokenize(t):
                if len(sub) >= 2:
                    res.add(sub)
                    if sub.endswith('ed') and len(sub) > 4:
                        res.add(sub[:-2])
                    elif sub.endswith('ing') and len(sub) > 5:
                        res.add(sub[:-3])
                    elif sub.endswith('s') and len(sub) > 3:
                        res.add(sub[:-1])
        return res

    def _score_ast_node(self, node: ast.AST, terms: Set[str], docstring_lines: Set[int]) -> float:
        score = 0.0
        is_return_stmt = isinstance(node, ast.Return)

        for sub in ast.walk(node):
            ln = getattr(sub, 'lineno', None)
            if ln and ln in docstring_lines:
                continue

            if isinstance(sub, ast.Call):
                func_name = ''
                if isinstance(sub.func, ast.Name):
                    func_name = sub.func.id
                elif isinstance(sub.func, ast.Attribute):
                    curr = sub.func
                    parts = []
                    while isinstance(curr, ast.Attribute):
                        parts.append(curr.attr)
                        curr = curr.value
                    if isinstance(curr, ast.Name):
                        parts.append(curr.id)
                    func_name = '.'.join(reversed(parts))

                if 'add_argument' in func_name:
                    continue

                call_weight = 4.0 if is_return_stmt else 10.0
                for token in self._tokenize(func_name):
                    if token in terms:
                        score += call_weight
                    elif token in ('generate', 'ask', 'urlopen', 'stream_callback'):
                        score += call_weight
                    elif token == 'request':
                        score += 8.0

                for kw in sub.keywords:
                    kw_weight = 2.0 if is_return_stmt else 6.0
                    if kw.arg:
                        for token in self._tokenize(kw.arg):
                            if token in terms:
                                score += kw_weight
                    if isinstance(kw.value, ast.Name):
                        for token in self._tokenize(kw.value.id):
                            if token in terms:
                                score += kw_weight

                for a in sub.args:
                    if isinstance(a, ast.Name):
                        for token in self._tokenize(a.id):
                            if token in terms:
                                score += 5.0
                            elif token in ('url', 'req', 'payload'):
                                score += 6.0
                    elif isinstance(a, ast.Constant) and isinstance(a.value, str):
                        for token in self._tokenize(a.value):
                            if token in terms:
                                score += 5.0
                        if '/api/' in a.value:
                            score += 30.0

            elif isinstance(sub, (ast.Assign, ast.AnnAssign)):
                val = getattr(sub, 'value', None)
                if isinstance(val, ast.JoinedStr):
                    for v in val.values:
                        if isinstance(v, ast.Constant) and isinstance(v.value, str):
                            for token in self._tokenize(v.value):
                                if token in terms:
                                    score += 6.0
                            if '/api/' in v.value:
                                score += 30.0
                elif isinstance(val, ast.Constant) and isinstance(val.value, str):
                    for token in self._tokenize(val.value):
                        if token in terms:
                            score += 5.0
                    if '/api/' in val.value:
                        score += 30.0

                targets = [sub.target] if isinstance(sub, ast.AnnAssign) else sub.targets
                for tgt in targets:
                    if isinstance(tgt, ast.Name) and tgt.id in ('url', 'req', 'payload'):
                        score += 8.0

            elif isinstance(sub, (ast.If, ast.While, ast.For)):
                test = getattr(sub, 'test', None)
                if test:
                    for test_sub in ast.walk(test):
                        if isinstance(test_sub, ast.Name):
                            for token in self._tokenize(test_sub.id):
                                if token in terms:
                                    score += 8.0

            elif isinstance(sub, ast.Name):
                name_weight = 0.5 if is_return_stmt else 1.0
                for token in self._tokenize(sub.id):
                    if token in terms:
                        score += name_weight

        return score

    def select_relevant(
        self,
        file_path: str,
        source: str,
        query_terms: List[str],
        max_spans: int = 3,
        max_lines_per_span: int = 25,
    ) -> List[CodeSpan]:
        """
        Parses source once, scores functions, signatures, calls, and statements across the whole file.
        Selects top-relevance symbols and bounded sections.
        Returns multiple noncontiguous spans when operations are separated, keeping original line ranges.
        Safeguards: Comments and docstrings are excluded from executable scoring.
        """
        try:
            tree = ast.parse(source)
        except Exception:
            return []

        lines = source.splitlines()
        terms = self._normalize_terms(query_terms)
        if not terms:
            return []

        class_map = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        class_map[sub] = node.name

        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node)

        docstring_lines = set()
        for fn in functions:
            if fn.body and isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) and isinstance(fn.body[0].value.value, str):
                for l in range(fn.body[0].lineno, fn.body[0].end_lineno + 1):
                    docstring_lines.add(l)

        candidate_spans: List[CodeSpan] = []

        for fn in functions:
            cls_name = class_map.get(fn, '')
            full_name = f'{cls_name}.{fn.name}' if cls_name else fn.name

            sig_score = 0.0
            for token in self._tokenize(fn.name):
                if token in terms:
                    sig_score += 6.0
                elif token in ('generate', 'ask'):
                    sig_score += 4.0

            for arg in fn.args.args + fn.args.kwonlyargs:
                for token in self._tokenize(arg.arg):
                    if token in terms:
                        sig_score += 4.0
                    elif token == 'stream_callback':
                        sig_score += 6.0

            scored_stmts = []
            for stmt in fn.body:
                if stmt.lineno in docstring_lines:
                    continue
                sc = self._score_ast_node(stmt, terms, docstring_lines)
                if sc > 0:
                    scored_stmts.append((stmt, sc))

            total_fn_score = sig_score + sum(sc for _, sc in scored_stmts)
            if total_fn_score <= 0:
                continue

            fn_len = fn.end_lineno - fn.lineno + 1
            if fn_len <= max_lines_per_span:
                candidate_spans.append(CodeSpan(
                    start_line=fn.lineno,
                    end_line=fn.end_lineno,
                    content='\n'.join(lines[fn.lineno - 1 : fn.end_lineno]),
                    symbol_name=full_name,
                    score=total_fn_score,
                ))
            else:
                # Large function: extract signature and statement clusters
                sig_end = fn.body[0].lineno - 1 if fn.body else fn.lineno
                sig_end = min(fn.end_lineno, max(fn.lineno, sig_end))
                if sig_end - fn.lineno + 1 <= max_lines_per_span:
                    candidate_spans.append(CodeSpan(
                        start_line=fn.lineno,
                        end_line=sig_end,
                        content='\n'.join(lines[fn.lineno - 1 : sig_end]),
                        symbol_name=full_name,
                        score=sig_score + 18.0,
                    ))

                # Cluster statements that are close together
                clusters = []
                cur_cluster = []
                for stmt, sc in scored_stmts:
                    if not cur_cluster:
                        cur_cluster.append((stmt, sc))
                    else:
                        prev_stmt = cur_cluster[-1][0]
                        gap = stmt.lineno - prev_stmt.end_lineno
                        total_span = stmt.end_lineno - cur_cluster[0][0].lineno + 1
                        if gap <= 3 and total_span <= max_lines_per_span:
                            cur_cluster.append((stmt, sc))
                        else:
                            clusters.append(cur_cluster)
                            cur_cluster = [(stmt, sc)]
                if cur_cluster:
                    clusters.append(cur_cluster)

                for cl in clusters:
                    cl_start = cl[0][0].lineno
                    cl_end = cl[-1][0].end_lineno
                    cl_score = sum(s[1] for s in cl)

                    # Bounded padding around statements
                    pad_start = max(fn.lineno, cl_start - 1)
                    pad_end = min(fn.end_lineno, cl_end + 1)
                    if pad_end - pad_start + 1 <= max_lines_per_span:
                        cl_start, cl_end = pad_start, pad_end
                    elif cl_end - cl_start + 1 > max_lines_per_span:
                        best_stmt = max(cl, key=lambda s: s[1])[0]
                        cl_start = max(fn.lineno, best_stmt.lineno - 2)
                        cl_end = min(fn.end_lineno, cl_start + max_lines_per_span - 1)

                    candidate_spans.append(CodeSpan(
                        start_line=cl_start,
                        end_line=cl_end,
                        content='\n'.join(lines[cl_start - 1 : cl_end]),
                        symbol_name=full_name,
                        score=cl_score,
                    ))

        # Sort candidate spans by score descending, keep top max_spans non-overlapping spans
        candidate_spans.sort(key=lambda s: s.score, reverse=True)
        selected: List[CodeSpan] = []
        for cand in candidate_spans:
            overlap = False
            for sel in selected:
                if not (cand.end_line < sel.start_line or cand.start_line > sel.end_line):
                    overlap = True
                    break
            if not overlap:
                selected.append(cand)
            if len(selected) >= max_spans:
                break

        selected.sort(key=lambda s: s.start_line)
        return selected
