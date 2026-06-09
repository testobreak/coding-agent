# llm/llm_planner.py
#
# LLM-driven planning.
# Replaces the keyword-matching classify_task() in planner.py.
#
# The LLM receives:
#   - the goal
#   - a list of files in the repo (sampled)
#   - recent retrieved symbols (if any)
#
# It responds with a structured JSON plan:
#   {
#     "task_type": "bug_fix" | "feature" | "refactor" | "analysis",
#     "reasoning": "...",
#     "target_files": ["src/main/java/...EmployeeService.java"],
#     "diagnosis": "The salary deduction method does not null-check ...",
#     "suggested_queries": ["salary deduction method", "calculateSalary"]
#   }
#
# If the LLM call fails or returns invalid JSON,
# the system falls back to the keyword planner automatically.
#

import json
import re
from typing import Optional

from llm.ollama_client import OllamaClient


SYSTEM_PROMPT = """You are an expert software engineering assistant embedded in a local coding agent.

Your job is to analyze a user's coding goal and produce a structured plan.

You will receive:
- GOAL: what the user wants to do
- REPO FILES: a sample of files in the repository
- KNOWN SYMBOLS: code symbols already retrieved (may be empty)

Respond ONLY with a JSON object in this exact format:
{
  "task_type": "bug_fix" | "feature" | "refactor" | "analysis",
  "reasoning": "one sentence explaining your classification",
  "diagnosis": "what is most likely wrong or what needs to be built (be specific, mention file names and method names when you can)",
  "target_files": ["relative/path/to/File.java", "..."],
  "suggested_queries": ["search term 1", "search term 2", "search term 3"]
}

Rules:
- target_files: list up to 5 files most likely to need changes. Use paths from REPO FILES when possible. Empty list if unclear.
- suggested_queries: 2-4 short search terms to find the relevant code via semantic search
- diagnosis: be concrete. Don't say "the code might have issues". Say what specifically is likely wrong.
- Return ONLY the JSON. No explanation. No markdown fences.
"""


class LLMPlanner:
    """
    Uses the local Ollama LLM to classify a task and identify target files
    before the execution loop begins.
    """

    def __init__(self, llm: OllamaClient = None):
        self.llm = llm or OllamaClient()

    # =========================================================
    # MAIN
    # =========================================================

    def plan(
        self,
        goal: str,
        repo_files: list,
        known_symbols: list = None,
        context_package: dict = None,
    ) -> Optional[dict]:
        """
        Returns a plan dict or None if the LLM call fails.
        """
        prompt = self._build_prompt(
            goal, repo_files, known_symbols or [], context_package
        )

        import time
        start_time = time.time()
        try:
            response = self.llm.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ], role="planner")
            duration = time.time() - start_time
            print(f"[LLMPlanner] Completed in {duration:.2f}s")
        except Exception as e:
            duration = time.time() - start_time
            print(f"[LLMPlanner] LLM call failed after {duration:.2f}s: {e}")
            return None

        return self._parse_response(response)

    # =========================================================
    # PROMPT
    # =========================================================

    def _build_prompt(
        self,
        goal: str,
        repo_files: list,
        known_symbols: list,
        context_package: dict = None,
    ) -> str:
        """Construct the LLM prompt.

        The previous implementation aggressively truncated the file list to a
        minimum of five entries, which caused the planner to lose critical
        context in large repositories. The new logic:

        1. If the repository contains many files, we generate a concise
           hierarchical summary (top‑level directories and their immediate
           children) and include it in the prompt.
        2. We include a *sample* of up to `MAX_FILES` representative files.
           Callers can sort the list by relevance beforehand (e.g., via a
           prior semantic retrieval).
        3. The token‑budget estimation loop now only trims the sample list;
           it never drops below `MIN_FILES` (default 5) and prefers keeping
           the summary.
        """
        MAX_FILES = 30  # Upper bound for explicit file entries
        MIN_FILES = 5   # Preserve a small sample for context

        # Helper to build a two‑level repository tree summary.
        def _repo_summary(files: list) -> str:
            from collections import defaultdict
            from pathlib import PurePath
            tree = defaultdict(set)
            for f in files:
                parts = PurePath(f).parts
                if len(parts) >= 2:
                    tree[parts[0]].add(parts[1])
                elif parts:
                    tree[parts[0]]  # ensure top‑level appears
            lines = []
            for top, subs in sorted(tree.items()):
                lines.append(f"{top}/")
                for sub in sorted(subs):
                    lines.append(f"  {sub}/")
            return "\n".join(lines) if lines else "<empty repo>"

        # Decide how many files to include explicitly.
        sampled_files = list(repo_files)
        if len(sampled_files) > MAX_FILES:
            sampled_files = sampled_files[:MAX_FILES]

        # Build the repo summary if the full list is large.
        repo_summary_section = ""
        if len(repo_files) > MAX_FILES:
            repo_summary_section = f"\nREPOSITORY SUMMARY:\n{_repo_summary(repo_files)}\n"

        # Build the string representations.
        files_str = "\n".join(f"  {f}" for f in sampled_files)

        # Populate known_symbols from context_package if empty
        if not known_symbols and context_package:
            symbols_list = context_package.get("symbols") or []
            known_symbols = symbols_list

        symbols_str = "None"
        if known_symbols:
            symbols_str = "\n".join(
                f"  {s.get('name', '')} ({s.get('type', '')}) in {s.get('file', '')}"
                for s in known_symbols
            )

        # Build retrieved code section
        retrieved_context_str = ""
        if context_package:
            retrieved_chunks = context_package.get("retrieved_chunks") or []
            if retrieved_chunks:
                snippets = []
                for chunk in retrieved_chunks[:6]:
                    f_path = chunk.get("file") or chunk.get("file_path") or "unknown"
                    c_content = chunk.get("content") or chunk.get("code") or ""
                    if c_content:
                        if len(c_content) > 1200:
                            c_content = c_content[:1200] + "\n...[TRUNCATED]..."
                        snippets.append(f"File: {f_path}\nCode:\n{c_content}")
                if snippets:
                    retrieved_context_str = f"\nRELEVANT RETRIEVED CODE:\n" + "\n\n".join(snippets) + "\n"

        prompt = f"""GOAL:
{goal}

REPO FILES:{repo_summary_section}
{files_str}

KNOWN SYMBOLS:
{symbols_str}
{retrieved_context_str}"""

        # Simple token‑budget check – if we still exceed, trim the file list.
        while len(prompt.split()) * 1.3 > 3500 and len(sampled_files) > MIN_FILES:
            sampled_files.pop()
            files_str = "\n".join(f"  {f}" for f in sampled_files)
            prompt = f"""GOAL:
{goal}

REPO FILES:{repo_summary_section}
{files_str}

KNOWN SYMBOLS:
{symbols_str}
{retrieved_context_str}"""

        return prompt

    # =========================================================
    # PARSE
    # =========================================================

    def _parse_response(self, response: str) -> Optional[dict]:
        """
        Parse the LLM JSON response. Handles cases where the model
        wraps the JSON in markdown fences, has comments, trailing commas,
        or has prefix/suffix text.
        """
        if not response:
            return None

        text = response.strip()

        def repair_json_str(s: str) -> str:
            # Remove multi-line/block comments /* ... */
            s = re.sub(r"\/\*.*?\*\/", "", s, flags=re.DOTALL)
            # Remove single-line comments // ... or # ... (except http://)
            s = re.sub(r"(?<!:)\/\/.*$", "", s, flags=re.MULTILINE)
            s = re.sub(r"(?<!:)(?<!\w)#.*$", "", s, flags=re.MULTILINE)
            # Remove trailing commas in lists and dicts
            s = re.sub(r",\s*([\]}])", r"\1", s)
            return s.strip()

        data = None

        # 1. Clean markdown fences
        text_clean = re.sub(r"^```[a-z]*\n?", "", text, flags=re.IGNORECASE)
        text_clean = re.sub(r"\n?```$", "", text_clean).strip()

        # Try direct load of cleaned text
        try:
            data = json.loads(text_clean)
        except json.JSONDecodeError:
            # Try repaired cleaned text
            try:
                data = json.loads(repair_json_str(text_clean))
            except json.JSONDecodeError:
                # 2. Extract JSON object from within response using regex ({...})
                # Find the first '{' and the last '}'
                match = re.search(r"(\{.*\})", text_clean, re.DOTALL)
                if match:
                    candidate = match.group(1)
                    try:
                        data = json.loads(candidate)
                    except json.JSONDecodeError:
                        try:
                            data = json.loads(repair_json_str(candidate))
                        except json.JSONDecodeError:
                            pass

        # If still None, try to search the original response text for '{...}'
        if data is None:
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if match:
                candidate = match.group(1)
                try:
                    data = json.loads(candidate)
                except json.JSONDecodeError:
                    try:
                        data = json.loads(repair_json_str(candidate))
                    except json.JSONDecodeError:
                        pass

        if not isinstance(data, dict):
            print(f"[LLMPlanner] Could not parse JSON from response: {text[:200]}")
            return None

        # Ensure required keys are strictly present, defaulting empty values if missing
        required_defaults = {
            "task_type": "analysis",
            "diagnosis": "",
            "target_files": [],
            "suggested_queries": []
        }
        for key, default in required_defaults.items():
            if key not in data or data[key] is None:
                data[key] = default

        # Normalise task_type
        valid_types = {"bug_fix", "feature", "refactor", "analysis"}
        if data["task_type"] not in valid_types:
            data["task_type"] = "analysis"

        # Ensure lists are actually lists
        for key in ["target_files", "suggested_queries"]:
            val = data.get(key)
            if isinstance(val, str):
                data[key] = [val]
            elif isinstance(val, (list, tuple, set)):
                data[key] = list(val)
            else:
                data[key] = []

        return data
