# implementation_plan.md — Database Layer Completion

## What exists (good foundation)
- `repositories`, `files`, `symbols` tables — fully populated (260 files, 707 symbols)
- Tree-sitter parsers (Java, Python, JS, TS) — working
- Scanner + symbol_indexer — working

## What is missing (5 things to build now)

### 1. Schema expansion
Add 5 tables:
- `symbol_relationships` — CALLS / IMPLEMENTS / EXTENDS / USES / TESTS edges
- `embeddings` — vector per symbol (384-dim MiniLM float array)
- `index_jobs` — incremental indexing audit log (what changed, when)
- `tests` — link test file → class/method under test
- `repair_patterns` — past LLM repair actions that worked (training signal)

### 2. Relationship indexer
`indexing/relationship_indexer.py`
- Reads Java AST: `implements`, `extends` → IMPLEMENTS / EXTENDS edges
- Reads import statements → USES edges (file level)
- Result: `symbol_relationships` table populated

### 3. Embedding indexer
`indexing/embedding_indexer.py`
- Embeds each symbol's signature + context using sentence-transformers MiniLM
- Stores float[] vector in `embeddings` table (as `REAL[]` or `TEXT` JSON)
- Skips already-embedded symbols (idempotent)

### 4. Incremental indexer
`indexing/incremental_indexer.py`
- On each run: compare current file hash vs stored hash
- Only re-parse + re-index files whose hash changed
- Records run in `index_jobs` table

### 5. Updated orchestrator
`index_repo.py` → runs all layers in order:
  scan → symbols → relationships → embeddings → incremental audit
