# execution/local_agent.py
"""
Local Coding Agent Orchestrator optimized for local Ollama models (e.g. Qwen2.5-Coder:7b).

Architecture:
1. Deterministic Repository Search (Symbol + Keyword + File Discovery) - 0 LLM calls
2. Context Compactor & Strict Token Budgeting (< 1,500 tokens)
3. Single Focused Ollama Call (keep_alive, streaming)
4. Telemetry Dashboard (timing, tokens/sec, retrieval accuracy)
"""

import os
import re
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable

import difflib
from inference.ollama_client import OllamaClient, OllamaResponse, OllamaTelemetry
from validation.fast_validator import FastValidator
from retrieval.python_span_selector import PythonSpanSelector
from retrieval.exact_reference_resolver import ExactReferenceResolver
from retrieval.candidate_merger import CandidateMerger, MergeResult


@dataclass
class PatchProposal:
    file_path: str
    original_content: str
    patched_content: str
    diff: str
    start_line: int
    end_line: int
    syntax_valid: bool
    syntax_error: Optional[str]
    telemetry: OllamaTelemetry


@dataclass
class RetrievedSnippet:
    file_path: str
    start_line: int
    end_line: int
    content: str
    relevance_score: float
    matched_term: str


@dataclass
class AgentResult:
    query: str
    answer: str
    snippets: List[RetrievedSnippet]
    retrieval_duration_ms: float
    telemetry: OllamaTelemetry

    def summary(self) -> str:
        snippet_files = sorted(list({s.file_path for s in self.snippets}))
        files_str = ", ".join(snippet_files) if snippet_files else "None"
        return (
            f"Query: {self.query}\n"
            f"Retrieved Files ({len(self.snippets)} snippets in {self.retrieval_duration_ms:.1f}ms): {files_str}\n"
            f"Ollama Stats: {self.telemetry.summary()}"
        )


class LocalAgent:
    EXCLUDED_DIRS = {
        ".git", "node_modules", ".cache", "__pycache__", "out", "dist",
        ".pytest_cache", ".venv", "venv", ".idea", ".vscode", "logs"
    }
    CODE_EXTENSIONS = {
        ".py", ".java", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs",
        ".cpp", ".c", ".h", ".cs", ".sql", ".json", ".yaml", ".yml"
    }

    def __init__(
        self,
        repo_root: Optional[str] = None,
        model: str = "qwen2.5-coder:7b",
        ollama_url: str = "http://localhost:11434",
        max_context_chars: int = 6000,  # ~1500 tokens
    ):
        self.repo_root = Path(repo_root or os.getcwd()).resolve()
        self.ollama = OllamaClient(base_url=ollama_url, model=model, keep_alive="30m")
        self.python_span_selector = PythonSpanSelector()
        self.max_context_chars = max_context_chars
        self._cached_source_files: Optional[List[Path]] = None

    def _get_source_files(self) -> List[Path]:
        if self._cached_source_files is not None:
            return self._cached_source_files
        source_files = []
        for root, dirs, files in os.walk(self.repo_root):
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS]
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in self.CODE_EXTENSIONS:
                    source_files.append(Path(root) / file)
        self._cached_source_files = source_files
        return self._cached_source_files

    @staticmethod
    def _implementation_score(line: str) -> float:
        """Prefer executable operations over descriptions and imports."""
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return 0.0
        score = 0.0
        if re.search(r"\b(?:self\.)?\w+\.\w+\s*\(", stripped):
            score += 4.0
        if re.search(r"\b(?:return|yield|raise|await)\b", stripped):
            score += 2.0
        if re.search(r"\b(?:for|while|if|with)\b", stripped):
            score += 1.0
        if stripped.startswith(("import ", "from ")):
            score -= 3.0
        return score

    def extract_search_terms(self, query: str) -> List[str]:
        """Extracts significant identifiers and keywords from user query."""
        stopwords = {
            "find", "the", "in", "my", "and", "or", "to", "for", "of", "a", "an",
            "is", "how", "what", "where", "explain", "show", "describe", "identify",
            "any", "all", "code", "application", "app", "project", "implement", "work",
            "works", "with", "does", "can", "you", "tell", "me", "about"
        }
        tokens = re.findall(r"[A-Za-z0-9_]+", query)
        terms = []
        for t in tokens:
            low = t.lower()
            if low not in stopwords and len(t) > 2:
                terms.append(t)
                # Light morphological stemming for natural language queries
                if low.endswith("ing") and len(low) > 5 and low[:-3] not in stopwords:
                    terms.append(t[:-3])
                elif low.endswith("ed") and len(low) > 4 and low[:-2] not in stopwords:
                    terms.append(t[:-2])
                elif low.endswith("s") and len(low) > 4 and not low.endswith("ss") and low[:-1] not in stopwords:
                    terms.append(t[:-1])

        unique_terms = []
        for t in terms:
            if t not in unique_terms:
                unique_terms.append(t)
        return unique_terms

    def deterministic_search(self, terms: List[str], max_snippets: int = 5) -> List[RetrievedSnippet]:
        """
        Fast deterministic scan across source files for matching terms.
        Prioritizes:
        - Multi-term co-occurrence in snippet window & file
        - Active implementation files (execution/, inference/, ask.py)
        - Exact class/function definitions and invocations
        - Per-file diversity (max 1 snippet per file to prevent single-file crowding)
        - Demotes tests and legacy/shadowed packages unless explicitly requested.
        Runs in < 50ms without touching an LLM.
        """
        raw_candidates: List[Dict[str, Any]] = []
        if not terms:
            return []

        is_test_query = any(t.lower() in ("test", "tests", "testing", "spec", "mock") for t in terms)
        source_files = self._get_source_files()

        # Pass 1: Fast lexical scan (0 AST parsing calls)
        for file_path in source_files:
            rel_path = str(file_path.relative_to(self.repo_root))
            path_lower = rel_path.lower()
            path_terms = [t for t in terms if t.lower() in path_lower]

            is_test_file = (
                "/tests/" in path_lower or path_lower.startswith("tests/") or
                Path(rel_path).name.startswith("test_") or Path(rel_path).name.endswith("_test.py") or
                Path(rel_path).name.startswith("verify_")
            )
            is_legacy_dir = "/llm/" in path_lower or path_lower.startswith("llm/")
            is_active_core = (
                rel_path in ("ask.py", "edit.py") or
                "/execution/" in path_lower or
                "/inference/" in path_lower or
                "/context/" in path_lower
            )

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()
            for line_idx, line in enumerate(lines):
                line_lower = line.lower()
                matched_on_line = [t for t in terms if t.lower() in line_lower]
                if not matched_on_line:
                    continue

                # Fast 25-line window
                start = max(0, line_idx - 10)
                end = min(len(lines), line_idx + 15)
                snippet_text = "\n".join(lines[start:end])
                window_lower = snippet_text.lower()
                terms_in_window = [
                    t for t in terms
                    if t.lower() in window_lower
                ]

                # Boost score if definition (def, class, function, interface)
                is_def = bool(re.search(r"\b(class|def|function|interface|public|router|async\s+def)\b", line))
                has_def_in_window = any(re.search(r"^\s*(class|def|async\s+def)\s+\w+", l) for l in lines[start:end])
                is_call = bool(re.search(r"\b(ollama|client|agent)\.(\w+)\(|\bOllamaClient\(|\bLocalAgent\(", line, re.IGNORECASE))

                score = 1.0
                if is_def:
                    score += 2.0
                elif has_def_in_window:
                    score += 1.0

                if is_call:
                    score += 2.5

                score += self._implementation_score(line)

                # Multi-term co-occurrence boost (highest relevance signal)
                if len(terms_in_window) > 1:
                    score += 3.5 * (len(terms_in_window) - 1)

                # Path matches boost
                if path_terms:
                    score += 1.5 * len(path_terms)

                # Active core orchestrator boost
                if is_active_core:
                    score += 2.0

                # Top-priority active runtime chain boost
                if rel_path in ("ask.py", "edit.py") or rel_path.endswith("local_agent.py") or rel_path.endswith("inference/ollama_client.py"):
                    score += 2.5

                # Test penalty (unless user asked about tests)
                if is_test_file and not is_test_query:
                    score -= 15.0

                # Legacy demotion (e.g. shadowed .agent/llm/ vs active .agent/inference/)
                if is_legacy_dir:
                    score -= 4.0

                raw_candidates.append({
                    "score": score,
                    "file_path": file_path,
                    "rel_path": rel_path,
                    "line_idx": line_idx,
                    "start": start,
                    "end": end,
                    "snippet_text": snippet_text,
                    "matched_term": matched_on_line[0],
                    "content": content,
                })

        # Sort candidate matches by score descending
        raw_candidates.sort(key=lambda c: c["score"], reverse=True)

        # Enforce diversity: select top candidates (max 1 per file)
        selected_candidates = []
        seen_files = set()

        for c in raw_candidates:
            if c["rel_path"] not in seen_files:
                seen_files.add(c["rel_path"])
                selected_candidates.append(c)
            if len(selected_candidates) >= max_snippets:
                break

        # If not enough diverse files found, fill remaining slots from top candidate files
        if len(selected_candidates) < max_snippets:
            seen_keys = {(c["rel_path"], c["start"] // 20) for c in selected_candidates}
            for c in raw_candidates:
                key = (c["rel_path"], c["start"] // 20)
                if key not in seen_keys:
                    seen_keys.add(key)
                    selected_candidates.append(c)
                if len(selected_candidates) >= max_snippets:
                    break

        # Pass 2: Selective AST Span Expansion ONLY on the winning candidates (max 5 calls total)
        deduped: List[RetrievedSnippet] = []
        for c in selected_candidates:
            start = c["start"]
            end = c["end"]
            snippet_text = c["snippet_text"]
            file_path = c["file_path"]

            if file_path.suffix.lower() == ".py":
                ast_spans = self.python_span_selector.select_relevant(
                    file_path=str(file_path),
                    source=c["content"],
                    query_terms=terms,
                    max_spans=3,
                    max_lines_per_span=25,
                )
                if ast_spans:
                    for ast_span in ast_spans:
                        deduped.append(RetrievedSnippet(
                            file_path=c["rel_path"],
                            start_line=ast_span.start_line,
                            end_line=ast_span.end_line,
                            content=ast_span.content,
                            relevance_score=c["score"] + (ast_span.score * 0.05),
                            matched_term=c["matched_term"],
                        ))
                    continue

            deduped.append(RetrievedSnippet(
                file_path=c["rel_path"],
                start_line=start + 1,
                end_line=end,
                content=snippet_text,
                relevance_score=c["score"],
                matched_term=c["matched_term"],
            ))

        return deduped

    def build_compact_context(self, snippets: List[RetrievedSnippet]) -> str:
        """Combines snippets into a compact, structured context within the token budget."""
        if not snippets:
            return "No relevant repository snippets found."

        sections = []
        current_chars = 0

        for s in snippets:
            header = f"--- File: {s.file_path} (Lines {s.start_line}-{s.end_line}) ---\n"
            block = f"{header}{s.content}\n\n"
            if current_chars + len(block) > self.max_context_chars:
                # Truncate if exceeding budget
                remaining = self.max_context_chars - current_chars
                if remaining > 100:
                    sections.append(block[:remaining] + "\n[Context Truncated]")
                break
            sections.append(block)
            current_chars += len(block)

        return "".join(sections)

    def retrieve_file_candidates(
        self,
        query: str,
        max_candidates: int = 12,
    ) -> MergeResult:
        """
        Resolves explicit filenames and merges them with
        lexical search results.
        No LLM calls or source-code expansion.
        """
        resolver = ExactReferenceResolver(
            repo_root=str(self.repo_root),
            source_files=self._get_source_files(),
        )
        exact_references = resolver.resolve(query)
        terms = self.extract_search_terms(query)
        lexical_snippets = self.deterministic_search(terms)
        merger = CandidateMerger()
        return merger.merge(
            exact_references=exact_references,
            lexical_snippets=lexical_snippets,
            max_candidates=max_candidates,
        )

    def ask(
        self,
        query: str,
        stream_callback: Optional[Callable[[str], None]] = None,
        num_predict: int = 256,
    ) -> AgentResult:
        """
        Executes Level 1 / Level 2 Code Q&A or Explanation:
        1. Analyzes query
        2. Retrieves relevant code snippets deterministically (<50ms)
        3. Compacts context
        4. Queries Ollama once with strict keep_alive and streaming
        5. Returns telemetry & answers
        """
        # Step 1 & 2: Deterministic search
        t0 = time.time()
        search_terms = self.extract_search_terms(query)
        snippets = self.deterministic_search(search_terms)
        retrieval_ms = (time.time() - t0) * 1000

        # Step 3: Build compact context
        context_block = self.build_compact_context(snippets)

        # Step 4: System prompt & single LLM call
        system_prompt = (
            "You are a precise, expert software engineering assistant. "
            "Analyze the provided code snippets to directly answer the user's question. "
            "Cite the specific file names and line numbers where appropriate. "
            "Be direct, concise, and technical. Keep answers focused (under 200 words). Avoid filler conversational phrases."
        )

        user_prompt = (
            f"Codebase Context:\n"
            f"```\n{context_block}\n```\n\n"
            f"User Question: {query}\n\n"
            f"Provide a concise, direct answer citing specific file paths and line numbers:"
        )

        # Step 5: Ollama execution
        res: OllamaResponse = self.ollama.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            num_ctx=4096,
            num_predict=num_predict,
            stream_callback=stream_callback,
        )

        return AgentResult(
            query=query,
            answer=res.text,
            snippets=snippets,
            retrieval_duration_ms=retrieval_ms,
            telemetry=res.telemetry,
        )

    def generate_patch(
        self,
        instruction: str,
        target_file: Optional[str] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> PatchProposal:
        """
        Level 3: Targeted surgical patch generation with validation.
        1. Identifies target file and target line span (using deterministic search or AST).
        2. Queries Ollama (single call) for the replacement block.
        3. Validates syntax using FastValidator (Python ast.parse, Java/TS checks).
        4. Produces unified git diff for human review.
        """
        # Resolve target file
        resolved_file = None
        if target_file:
            cand = self.repo_root / target_file
            if cand.exists():
                resolved_file = cand
        
        if not resolved_file:
            # Check if instruction names a file (e.g. 'in foo.py', 'bar.java')
            file_candidates = re.findall(r"[\w\./\-]+\.(?:py|java|ts|js|tsx|jsx|json|yaml|yml)", instruction)
            for fc in file_candidates:
                cand = self.repo_root / fc
                if cand.exists():
                    resolved_file = cand
                    break
                for sf in self._get_source_files():
                    if sf.name == Path(fc).name or str(sf).endswith(fc):
                        resolved_file = sf
                        break
                if resolved_file:
                    break

        if not resolved_file:
            terms = self.extract_search_terms(instruction)
            snippets = self.deterministic_search(terms, max_snippets=1)
            if snippets:
                resolved_file = self.repo_root / snippets[0].file_path

        if not resolved_file or not resolved_file.exists():
            raise FileNotFoundError(f"Could not resolve target file for instruction: '{instruction}'")

        rel_path = str(resolved_file.relative_to(self.repo_root))
        original_content = resolved_file.read_text(encoding="utf-8", errors="ignore")
        lines = original_content.splitlines()

        # Find target region (focus on matching terms or function/class definitions)
        terms = self.extract_search_terms(instruction)
        best_line = -1
        for idx, line in enumerate(lines):
            if any(t.lower() in line.lower() for t in terms):
                best_line = idx
                if re.search(r"\b(def|class|function|public)\b", line):
                    break

        if best_line == -1:
            start_line = 1
            end_line = min(len(lines), 30)
        else:
            start_line = max(1, best_line - 5)
            end_line = min(len(lines), best_line + 20)

        target_code = "\n".join(lines[start_line - 1:end_line])

        ctx_start = max(1, start_line - 15)
        ctx_end = min(len(lines), end_line + 15)
        surrounding_ctx = "\n".join(lines[ctx_start - 1:ctx_end])

        system_prompt = (
            "You are a surgical code modification engine. "
            "You will be given a target code block from a file and an instruction. "
            "Output ONLY the new replacement code for the target block. "
            "Do NOT include markdown backticks (```), file headers, or explanations. "
            "Output pure replacement code only."
        )

        user_prompt = (
            f"File: {rel_path}\n"
            f"Surrounding Context (lines {ctx_start}-{ctx_end}):\n"
            f"```\n{surrounding_ctx}\n```\n\n"
            f"TARGET BLOCK TO REPLACE (lines {start_line}-{end_line}):\n"
            f"```\n{target_code}\n```\n\n"
            f"INSTRUCTION:\n{instruction}\n\n"
            f"REPLACEMENT CODE FOR LINES {start_line}-{end_line}:"
        )

        res = self.ollama.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            num_ctx=4096,
            stream_callback=stream_callback,
        )

        replacement = res.text.strip()
        if replacement.startswith("```"):
            r_lines = replacement.splitlines()
            if r_lines:
                r_lines = r_lines[1:]
            if r_lines and r_lines[-1].startswith("```"):
                r_lines = r_lines[:-1]
            replacement = "\n".join(r_lines)

        new_lines = lines[:start_line - 1] + replacement.splitlines() + lines[end_line:]
        patched_content = "\n".join(new_lines) + ("\n" if original_content.endswith("\n") else "")

        # Fast syntax validation
        validator = FastValidator()
        ext = resolved_file.suffix.lower()
        syntax_valid = True
        syntax_error = None

        if ext == ".py":
            syntax_valid, syntax_error = validator.validate_python(patched_content)
        elif ext == ".java":
            syntax_valid, syntax_error = validator.validate_java(patched_content)
        elif ext in (".ts", ".js", ".tsx", ".jsx"):
            syntax_valid, syntax_error = validator.validate_typescript(patched_content)

        orig_split = original_content.splitlines(keepends=True)
        patched_split = patched_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_split,
            patched_split,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm=""
        ))
        diff_str = "\n".join(diff_lines)

        return PatchProposal(
            file_path=rel_path,
            original_content=original_content,
            patched_content=patched_content,
            diff=diff_str,
            start_line=start_line,
            end_line=end_line,
            syntax_valid=syntax_valid,
            syntax_error=syntax_error,
            telemetry=res.telemetry,
        )

    def apply_patch(self, proposal: PatchProposal) -> bool:
        """Applies a verified patch proposal to disk."""
        target_path = self.repo_root / proposal.file_path
        target_path.write_text(proposal.patched_content, encoding="utf-8")
        return True
