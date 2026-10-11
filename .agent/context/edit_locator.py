# context/edit_locator.py
#
# Edit Locality Scoring Engine.
# Gathers edit candidates and computes a composite heuristic score to identify
# the exact lines/spans to modify.

import os
import re
import numpy as np
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from editing.ast_locator import ASTLocator, ASTNodeInfo

logger = logging.getLogger(__name__)

@dataclass
class EditCandidate:
    file_path: str
    start_line: int
    end_line: int
    score: float = 0.0
    source: str = ""  # "chunk", "symbol", "git_diff", "file"
    ast_node: str = ""
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class EditLocator:
    def __init__(self, embedding_engine=None, repo_root="."):
        self.embedding_engine = embedding_engine
        self.repo_root = os.path.abspath(repo_root)
        self.ast_locator = ASTLocator()
        self._lazy_embedding_engine = None
        self._dep_graph = None

    def get_embedding_engine(self):
        if self.embedding_engine:
            return self.embedding_engine
        if not self._lazy_embedding_engine:
            from retrieval.embedding_engine import EmbeddingEngine
            self._lazy_embedding_engine = EmbeddingEngine()
        return self._lazy_embedding_engine

    def get_dependency_graph(self):
        if not self._dep_graph:
            from analysis.dependency_graph import DependencyGraph
            self._dep_graph = DependencyGraph()
            self._dep_graph.build(repo_root=self.repo_root)
        return self._dep_graph

    def parse_traceback_info(self, traceback_text: str) -> List[Dict[str, Any]]:
        """Extract file name patterns and line numbers from tracebacks."""
        if not traceback_text:
            return []
        matches = []
        # Python traceback style: File "path/to/file.py", line 123
        py_pattern = r'File "([^"]+)", line (\d+)'
        for match in re.finditer(py_pattern, traceback_text):
            matches.append({
                "file": match.group(1),
                "line": int(match.group(2))
            })
        # General stack trace style: path/to/file.java:123
        gen_pattern = r'([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]+):(\d+)'
        for match in re.finditer(gen_pattern, traceback_text):
            # Avoid matching IP addresses or time stamps
            f_path = match.group(1)
            if not f_path.replace(".", "").isdigit():
                matches.append({
                    "file": f_path,
                    "line": int(match.group(2))
                })
        return matches

    def generate_candidates(
        self,
        state_chunks: List[Dict[str, Any]],
        active_symbols: List[str],
        git_diff_str: str,
        modification_targets: List[str]
    ) -> List[EditCandidate]:
        """Stage 1: Generate initial set of candidates from chunks, symbols, git diffs, and target files."""
        candidates = []
        seen = set()

        def add_candidate(file_path: str, start: int, end: int, source: str, content: str = "", meta: dict = None):
            # Canonicalize path relative to repo_root
            rel_path = os.path.relpath(os.path.abspath(os.path.join(self.repo_root, file_path)), self.repo_root)
            key = (rel_path, start, end)
            if key not in seen:
                seen.add(key)
                candidates.append(EditCandidate(
                    file_path=rel_path,
                    start_line=start,
                    end_line=end,
                    source=source,
                    content=content,
                    metadata=meta or {}
                ))

        # 1. From chunks
        for chunk in state_chunks:
            file_p = chunk.get("file_path") or chunk.get("file")
            if file_p:
                start = chunk.get("start_line", 1)
                end = chunk.get("end_line", start + len(chunk.get("content", "").splitlines()))
                add_candidate(file_p, start, end, "chunk", chunk.get("content", ""), {"chunk_id": chunk.get("id")})

        # 2. From active symbols (look up via AST locator)
        for sym_name in active_symbols:
            for target_file in modification_targets:
                try:
                    node_info = self.ast_locator.find_symbol(os.path.join(self.repo_root, target_file), sym_name)
                    if node_info:
                        add_candidate(target_file, node_info.start_line, node_info.end_line, "symbol", node_info.content, {"symbol": sym_name})
                except Exception as e:
                    logger.warning(f"Failed to find symbol {sym_name} in {target_file}: {e}")

        # 3. From git diffs
        if git_diff_str:
            # Simple diff parser to find modified lines
            current_file = None
            for line in git_diff_str.splitlines():
                if line.startswith("+++ b/"):
                    current_file = line[6:]
                elif line.startswith("@@ -") and current_file:
                    match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
                    if match:
                        start = int(match.group(1))
                        count = int(match.group(2)) if match.group(2) else 1
                        add_candidate(current_file, start, start + count - 1, "git_diff")

        # 4. From modification targets directly
        for target_file in modification_targets:
            abs_p = os.path.join(self.repo_root, target_file)
            if os.path.exists(abs_p):
                with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                lines_count = len(content.splitlines())
                add_candidate(target_file, 1, max(1, lines_count), "file", content)

        return candidates

    def compute_heuristic_scores(
        self,
        candidates: List[EditCandidate],
        query: str,
        touched_files: List[str],
        traceback_info: List[Dict[str, Any]]
    ):
        """Stage 2: Heuristic Locality Scoring (Semantic: 35%, Symbol Match: 30%, Dependency Graph: 20%, Traceback: 15%)."""
        if not candidates:
            return

        emb_engine = self.get_embedding_engine()
        query_emb = emb_engine.embed_text(query)

        # Pre-build dependency lists
        dep_graph = self.get_dependency_graph()
        all_deps = set()
        all_rev_deps = set()
        for tf in touched_files:
            try:
                all_deps.update(dep_graph.dependencies_of(tf, depth=1))
                all_rev_deps.update(dep_graph.dependents_of(tf, depth=1))
            except Exception:
                pass

        for cand in candidates:
            # 1. Semantic Similarity (35%)
            cand_text = cand.content
            if not cand_text:
                abs_path = os.path.join(self.repo_root, cand.file_path)
                if os.path.exists(abs_path):
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.read().splitlines()
                    cand_text = "\n".join(lines[cand.start_line-1:cand.end_line])
            
            if cand_text.strip():
                cand_emb = emb_engine.embed_text(cand_text)
                sim = np.dot(query_emb, cand_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(cand_emb) + 1e-8)
                semantic_score = max(0.0, float(sim))
            else:
                semantic_score = 0.0

            # 2. Symbol Match (30%)
            # Extract components from path and query
            symbol_score = 0.0
            cand_name = os.path.basename(cand.file_path)
            meta_sym = cand.metadata.get("symbol", "")
            
            query_lower = query.lower()
            if cand_name.lower() in query_lower or (meta_sym and meta_sym.lower() in query_lower):
                symbol_score = 1.0
            else:
                # Part match
                components = re.split(r'[^a-zA-Z0-9]', cand_name) + re.split(r'[^a-zA-Z0-9]', meta_sym)
                matching = [c for c in components if len(c) >= 3 and c.lower() in query_lower]
                if matching:
                    symbol_score = 0.5

            # 3. Dependency Graph Proximity (20%)
            dep_score = 0.0
            if cand.file_path in touched_files:
                dep_score = 1.0
            elif cand.file_path in all_deps or cand.file_path in all_rev_deps:
                dep_score = 0.6
            else:
                dep_score = 0.0

            # 4. Traceback Matching (15%)
            trace_score = 0.0
            for tb in traceback_info:
                tb_file = tb["file"]
                tb_line = tb["line"]
                # Match file name suffix
                if cand.file_path.endswith(tb_file) or tb_file.endswith(cand.file_path):
                    if cand.start_line <= tb_line <= cand.end_line:
                        trace_score = 1.0
                        break
                    elif abs(cand.start_line - tb_line) <= 50:
                        trace_score = 0.8
                    else:
                        trace_score = 0.4

            # Composite Heuristic Score
            composite = (
                0.35 * semantic_score +
                0.30 * symbol_score +
                0.20 * dep_score +
                0.15 * trace_score
            )
            cand.score = round(composite, 4)

    def _find_smallest_enclosing_node(self, node, start_line: int, end_line: int):
        node_start = node.start_point[0]
        node_end = node.end_point[0]
        if node_start <= start_line and node_end >= end_line:
            for child in node.children:
                res = self._find_smallest_enclosing_node(child, start_line, end_line)
                if res:
                    return res
            return node
        return None

    def get_enclosing_ast_node(self, file_path: str, start_line: int, end_line: int) -> Dict[str, Any]:
        """Stage 3: Map candidate lines to enclosing structural AST node bounds."""
        abs_path = os.path.join(self.repo_root, file_path)
        if not os.path.exists(abs_path):
            return {"start_line": start_line, "end_line": end_line, "node_type": "fallback", "content": ""}

        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()

        lang_str = self.ast_locator.get_language(file_path)
        lang = self.ast_locator.langs.get(lang_str)
        if not lang:
            # Fallback
            return {"start_line": start_line, "end_line": end_line, "node_type": "fallback", "content": ""}

        from tree_sitter import Parser
        parser = Parser(lang)
        src_bytes = source.encode("utf-8")
        tree = parser.parse(src_bytes)

        # Find smallest enclosing node
        # tree-sitter lines are 0-indexed
        smallest_node = self._find_smallest_enclosing_node(tree.root_node, start_line - 1, end_line - 1)
        
        # Walk up to find nearest structural node
        STRUCTURAL_TYPES = {
            "class_definition", "class_declaration",
            "function_definition", "function_declaration",
            "method_definition", "method_declaration",
            "constructor_declaration"
        }
        node = smallest_node
        while node:
            if node.type in STRUCTURAL_TYPES:
                break
            node = node.parent

        target_node = node or smallest_node or tree.root_node
        start_l = target_node.start_point[0] + 1
        end_l = target_node.end_point[0] + 1
        content = src_bytes[target_node.start_byte:target_node.end_byte].decode("utf-8", errors="replace")

        return {
            "node_type": target_node.type,
            "name": self.ast_locator._get_node_name(target_node, src_bytes) or "",
            "start_line": start_l,
            "end_line": end_l,
            "content": content
        }

    def predict_micro_span(self, file_path: str, node_info: Dict[str, Any], query: str) -> tuple[int, int]:
        """Stage 4: Narrow structural node down to statement-level micro-spans."""
        content = node_info["content"]
        lines = content.splitlines()
        node_start = node_info["start_line"]

        if len(lines) <= 10:
            return (node_start, node_start + len(lines) - 1)

        windows = []
        ranges = []
        for i in range(len(lines)):
            window_text = "\n".join(lines[i:i+3])
            windows.append(window_text)
            ranges.append((i, min(len(lines), i+3)))

        if not windows:
            return (node_start, node_start + len(lines) - 1)

        emb_engine = self.get_embedding_engine()
        query_emb = emb_engine.embed_text(query)
        embs = emb_engine.embed_batch(windows)

        best_score = -1.0
        best_range = (0, len(lines))

        for idx, emb in enumerate(embs):
            dot = np.dot(query_emb, emb)
            sim = dot / (np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-8)
            if sim > best_score:
                best_score = sim
                best_range = ranges[idx]

        start_idx, end_idx = best_range
        return (node_start + start_idx, node_start + end_idx - 1)

    def locate(
        self,
        query: str,
        state_chunks: List[Dict[str, Any]],
        active_symbols: List[str],
        git_diff_str: str,
        modification_targets: List[str],
        traceback: str = None
    ) -> List[Dict[str, Any]]:
        """Run the full 4-stage Edit Locality pipeline and return ranked candidates with localized spans."""
        # 1. Generate Candidates
        candidates = self.generate_candidates(state_chunks, active_symbols, git_diff_str, modification_targets)
        if not candidates:
            return []

        # 2. Score candidates
        traceback_info = self.parse_traceback_info(traceback)
        self.compute_heuristic_scores(candidates, query, modification_targets, traceback_info)

        # Sort by score descending
        candidates.sort(key=lambda x: x.score, reverse=True)

        results = []
        # Localize top candidates
        for cand in candidates[:10]:  # Top 10
            # 3. AST Localization
            ast_info = self.get_enclosing_ast_node(cand.file_path, cand.start_line, cand.end_line)
            
            # 4. Micro-span Prediction
            micro_start, micro_end = self.predict_micro_span(cand.file_path, ast_info, query)

            results.append({
                "file_path": cand.file_path,
                "score": cand.score,
                "source": cand.source,
                "heuristic_start_line": cand.start_line,
                "heuristic_end_line": cand.end_line,
                "ast_node_type": ast_info["node_type"],
                "ast_node_name": ast_info["name"],
                "ast_start_line": ast_info["start_line"],
                "ast_end_line": ast_info["end_line"],
                "localized_start_line": micro_start,
                "localized_end_line": micro_end,
                "content_snippet": ast_info["content"]
            })

        return results
