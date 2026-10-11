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
        unique_terms = []
        for t in terms:
            if t not in unique_terms:
                unique_terms.append(t)
        return unique_terms

    def deterministic_search(self, terms: List[str], max_snippets: int = 5) -> List[RetrievedSnippet]:
        """
        Fast deterministic scan across source files for matching terms.
        Prioritizes file paths, class/function definitions, and exact hits.
        Runs in < 50ms without touching an LLM.
        """
        snippets: List[RetrievedSnippet] = []
        if not terms:
            return snippets

        source_files = self._get_source_files()

        # Score files based on matches
        for file_path in source_files:
            rel_path = str(file_path.relative_to(self.repo_root))
            
            # Check if file path matches any term (high relevance boost)
            path_matches = sum(1 for t in terms if t.lower() in rel_path.lower())

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()
            for line_idx, line in enumerate(lines):
                line_lower = line.lower()
                for term in terms:
                    term_lower = term.lower()
                    if term_lower in line_lower:
                        # Determine window around match
                        start = max(0, line_idx - 10)
                        end = min(len(lines), line_idx + 15)
                        snippet_text = "\n".join(lines[start:end])

                        # Boost score if definition (def, class, function, interface)
                        is_def = bool(re.search(r"\b(class|def|function|interface|public|router)\b", line))
                        score = 2.0 if is_def else 1.0
                        if path_matches:
                            score += 1.5 * path_matches

                        snippets.append(RetrievedSnippet(
                            file_path=rel_path,
                            start_line=start + 1,
                            end_line=end,
                            content=snippet_text,
                            relevance_score=score,
                            matched_term=term
                        ))

        # Sort snippets by score and de-duplicate overlapping ranges
        snippets.sort(key=lambda s: s.relevance_score, reverse=True)
        deduped: List[RetrievedSnippet] = []
        seen_files = set()

        for s in snippets:
            key = (s.file_path, s.start_line // 20)
            if key not in seen_files:
                seen_files.add(key)
                deduped.append(s)
            if len(deduped) >= max_snippets:
                break

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

    def ask(
        self,
        query: str,
        stream_callback: Optional[Callable[[str], None]] = None,
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
            "Be direct, concise, and technical. Avoid filler conversational phrases."
        )

        user_prompt = (
            f"Codebase Context:\n"
            f"```\n{context_block}\n```\n\n"
            f"User Question: {query}\n\n"
            f"Answer with specific references to the files and code above:"
        )

        # Step 5: Ollama execution
        res: OllamaResponse = self.ollama.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            num_ctx=4096,
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
