# Personal Coding Agent (`coding-agent`)

A local, autonomous AI coding agent and repository intelligence platform designed specifically for local Ollama models (e.g. `qwen2.5-coder:7b`). It performs deterministic code retrieval (0 LLM calls), context compaction, and single-turn model reasoning with streaming telemetry. Can be pointed at ANY external repository without modifying target code.

---

## 🏗 Architecture Overview

The system consists of three foundational layers:

```
                          ┌───────────────────────────┐
                          │     vscode-extension/     │
                          │   (TypeScript IDE Client) │
                          └─────────────┬─────────────┘
                                        │ HTTP / JSON-RPC
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                 .agent/                                     │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐ │
│  │      Retrieval       │  │ AST / Patch Engine   │  │ Validation/Repair  │ │
│  │  - BM25 + Exact Sym  │  │  - Tree-Sitter AST   │  │  - Compile Check   │ │
│  │  - Vector/FAISS      │  │  - EditSpan Calc     │  │  - Test Runner     │ │
│  │  - Cross-Encoder     │  │  - Atomic Rollback   │  │  - Self-Healing    │ │
│  └──────────────────────┘  └──────────────────────┘  └────────────────────┘ │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐ │
│  │   Inference Router   │  │    Cursor Runtime    │  │   Runtime Server   │ │
│  │  - Intent Classifier │  │  - Buffer Tracking   │  │  - /retrieve       │ │
│  │  - Speculative Dec.  │  │  - Inline Executor   │  │  - /apply_patch    │ │
│  └──────────────────────┘  └──────────────────────┘  └────────────────────┘ │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         repository_intelligence/                            │
│  ┌────────────────────────┐  ┌─────────────────────┐  ┌───────────────────┐ │
│  │   Workspace Scanner    │  │ Multi-Lang Parsers  │  │   Symbol Graph    │ │
│  │  - Monorepo Detection  │  │  - Python, Java, TS │  │  - Call Graph     │ │
│  │  - File Discovery      │  │  - Type Resolution  │  │  - SQLite Store   │ │
│  └────────────────────────┘  └─────────────────────┘  └───────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1. `.agent/` — Core Agent Runtime
* **Two-Stage Code Retrieval (`retrieval/`)**: Hybrid lexical search (BM25), exact symbol matching, dense vector embeddings (`faiss_store.py`), and cross-encoder re-ranking.
* **AST Patch Engine (`engines/`, `execution/`)**: Locates code targets via Tree-Sitter syntax trees across Java, Python, and TypeScript, computing exact `EditSpan` boundaries to apply atomic patches without corruption.
* **Cursor & Inline Runtime (`apps/cursor_runtime.py`, `execution/cursor_engine.py`)**: Manages live editor coordinates (cursor line/column, open tabs, unsaved buffer diffs) and powers Cmd+K inline modifications.
* **Self-Healing Verification Loop (`validation/`, `execution/`)**: Runs compile validators, test suites, failure routing, and rule-based repair subgraphs.

### 2. `repository_intelligence/` — Codebase Graph & Symbol Intelligence
* **Language Parsers (`parsers/`)**: Extracts classes, methods, functions, and interfaces using language-specific Tree-Sitter grammars.
* **Graph Builders (`indexer/`)**: Maps symbol relationships, call hierarchies, and dependencies into SQLite (`repository_intelligence.db`).
* **Manifest Service (`manifest/`, `symbol_locator.py`)**: Fast symbol-to-file lookup index.

### 3. `vscode-extension/` — IDE Integration
* VS Code extension (`vscode-cursor-agent`) connecting the editor interface to the agent backend daemon.
* Keybindings: `Cmd+K` (macOS) / `Ctrl+K` (Windows) for inline chat and generation.

---

## 🚀 Getting Started

### 1. Ingest & Index Repository
```bash
python .agent/index_repo.py
```

### 2. Run Background Agent Server
```bash
python -m runtime.server 8085
```

### 3. Ask Codebase Questions (Level 1 & 2 Q&A)
```bash
# Query the local agent codebase:
python ask.py "explain how the query resolver works"

# Query ANY external codebase (100% read-only, 0 changes to target code):
python ask.py --repo /path/to/any/spring-app "find the authentication implementation and explain how it works"
```

### 4. Targeted Code Modifications (Level 3 Surgical Editing)
```bash
# Propose a targeted patch with automated syntax validation and git diff approval:
python edit.py "in math.py, add a check for division by zero"

# Target an external codebase:
python edit.py --repo /path/to/my-project "in AuthService.java, add null check for token"
```

### 5. Run Verification Suites
```bash
python verify_local_agent.py
python verify_all.py
```
