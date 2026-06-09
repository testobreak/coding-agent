-- db/schema.sql
-- Repository Intelligence Layer — Complete PostgreSQL Schema
-- Idempotent: safe to run multiple times (CREATE IF NOT EXISTS throughout)

-- ─────────────────────────────────────────────────────────────
-- EXTENSIONS  (must come first)
-- ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ─────────────────────────────────────────────────────────────
-- LAYER 0: REPOSITORIES
-- One row per scanned root directory.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS repositories (
    id          SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL,
    root_path   TEXT        NOT NULL UNIQUE,
    language    TEXT,
    indexed_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- LAYER 1A: FILES
-- One row per source file. file_hash drives incremental indexing.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS files (
    id              SERIAL PRIMARY KEY,
    repository_id   INT         NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    path            TEXT        NOT NULL,
    relative_path   TEXT        NOT NULL,
    language        TEXT,
    file_hash       TEXT        NOT NULL,       -- sha256; changes trigger re-index
    size_bytes      BIGINT      NOT NULL,
    modified_at     TIMESTAMPTZ NOT NULL,
    indexed_at      TIMESTAMPTZ DEFAULT NOW(),
    symbols_indexed BOOL        DEFAULT FALSE,  -- true after symbol extraction
    embedded        BOOL        DEFAULT FALSE,  -- true after embedding
    UNIQUE (repository_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_files_repo         ON files(repository_id);
CREATE INDEX IF NOT EXISTS idx_files_language     ON files(language);
CREATE INDEX IF NOT EXISTS idx_files_hash         ON files(file_hash);
CREATE INDEX IF NOT EXISTS idx_files_dirty        ON files(symbols_indexed, embedded);

-- ─────────────────────────────────────────────────────────────
-- LAYER 1B: SYMBOLS
-- AST-extracted symbols: CLASS / METHOD / FUNCTION / INTERFACE / ENUM
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS symbols (
    id              SERIAL PRIMARY KEY,
    file_id         INT         NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    repository_id   INT         NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    name            TEXT        NOT NULL,
    qualified_name  TEXT,
    symbol_type     TEXT        NOT NULL,       -- CLASS | METHOD | FUNCTION | INTERFACE | ENUM
    parent_name     TEXT,
    line_start      INT,
    line_end        INT,
    signature       TEXT,
    language        TEXT        NOT NULL,
    indexed_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_symbols_name         ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_type         ON symbols(symbol_type);
CREATE INDEX IF NOT EXISTS idx_symbols_file         ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_repo         ON symbols(repository_id);
CREATE INDEX IF NOT EXISTS idx_symbols_parent       ON symbols(parent_name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified    ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_name_trgm
    ON symbols USING gin(name gin_trgm_ops);

-- ─────────────────────────────────────────────────────────────
-- LAYER 2: SYMBOL RELATIONSHIPS
-- Directed edges between symbols (or files when symbol is unknown).
--
-- rel_type values:
--   EXTENDS      — class A extends class B
--   IMPLEMENTS   — class A implements interface B
--   CALLS        — method A calls method B
--   USES         — file/symbol A imports/uses file/symbol B
--   TESTS        — test class/method A tests production class/method B
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS symbol_relationships (
    id              SERIAL PRIMARY KEY,
    repository_id   INT         NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,

    -- source (the thing doing the extending / calling / testing)
    from_symbol_id  INT         REFERENCES symbols(id) ON DELETE CASCADE,
    from_file_id    INT         REFERENCES files(id)   ON DELETE CASCADE,
    from_name       TEXT        NOT NULL,       -- human-readable, always set

    -- target (the thing being extended / called / tested)
    to_symbol_id    INT         REFERENCES symbols(id) ON DELETE SET NULL,
    to_file_id      INT         REFERENCES files(id)   ON DELETE SET NULL,
    to_name         TEXT        NOT NULL,

    rel_type        TEXT        NOT NULL,       -- EXTENDS | IMPLEMENTS | CALLS | USES | TESTS
    confidence      REAL        DEFAULT 1.0,    -- 1.0 = AST-certain, <1.0 = heuristic
    indexed_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rel_repo         ON symbol_relationships(repository_id);
CREATE INDEX IF NOT EXISTS idx_rel_from_sym     ON symbol_relationships(from_symbol_id);
CREATE INDEX IF NOT EXISTS idx_rel_to_sym       ON symbol_relationships(to_symbol_id);
CREATE INDEX IF NOT EXISTS idx_rel_from_file    ON symbol_relationships(from_file_id);
CREATE INDEX IF NOT EXISTS idx_rel_type         ON symbol_relationships(rel_type);
CREATE INDEX IF NOT EXISTS idx_rel_from_name    ON symbol_relationships(from_name);
CREATE INDEX IF NOT EXISTS idx_rel_to_name      ON symbol_relationships(to_name);

-- ─────────────────────────────────────────────────────────────
-- LAYER 3: EMBEDDINGS
-- One row per embedded symbol. Stores the vector as a float array.
-- Dimension: 384 (all-MiniLM-L6-v2)
--
-- When pgvector is available, swap REAL[] for vector(384).
-- The application layer handles both cases.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS embeddings (
    id              SERIAL PRIMARY KEY,
    symbol_id       INT         NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    repository_id   INT         NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    model           TEXT        NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    vector          REAL[]      NOT NULL,        -- 384-dim float array
    input_text      TEXT,                        -- the text that was embedded
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol_id, model)                    -- one embedding per symbol per model
);

CREATE INDEX IF NOT EXISTS idx_emb_symbol   ON embeddings(symbol_id);
CREATE INDEX IF NOT EXISTS idx_emb_repo     ON embeddings(repository_id);
CREATE INDEX IF NOT EXISTS idx_emb_model    ON embeddings(model);

-- ─────────────────────────────────────────────────────────────
-- LAYER 4: INDEX JOBS
-- Audit log for every indexing run.
-- Enables: "what changed since last run?", replay, debugging.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS index_jobs (
    id              SERIAL PRIMARY KEY,
    repository_id   INT         NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    job_type        TEXT        NOT NULL,        -- FULL | INCREMENTAL | SYMBOLS | EMBEDDINGS
    status          TEXT        NOT NULL DEFAULT 'running',  -- running | done | failed
    files_scanned   INT         DEFAULT 0,
    files_changed   INT         DEFAULT 0,
    files_skipped   INT         DEFAULT 0,
    symbols_added   INT         DEFAULT 0,
    symbols_deleted INT         DEFAULT 0,
    embeddings_added INT        DEFAULT 0,
    relationships_added INT     DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_repo    ON index_jobs(repository_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON index_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type    ON index_jobs(job_type);

-- ─────────────────────────────────────────────────────────────
-- LAYER 5: TESTS
-- Links test files/symbols to the production code they test.
-- Populated by the relationship indexer (heuristic + naming conventions).
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tests (
    id                  SERIAL PRIMARY KEY,
    repository_id       INT     NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,

    -- the test
    test_file_id        INT     REFERENCES files(id)   ON DELETE CASCADE,
    test_symbol_id      INT     REFERENCES symbols(id) ON DELETE CASCADE,
    test_name           TEXT    NOT NULL,

    -- what is being tested
    target_file_id      INT     REFERENCES files(id)   ON DELETE SET NULL,
    target_symbol_id    INT     REFERENCES symbols(id) ON DELETE SET NULL,
    target_name         TEXT,

    detection_method    TEXT    DEFAULT 'naming_convention',  -- or 'annotation' or 'import'
    indexed_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tests_repo           ON tests(repository_id);
CREATE INDEX IF NOT EXISTS idx_tests_test_file      ON tests(test_file_id);
CREATE INDEX IF NOT EXISTS idx_tests_target_file    ON tests(target_file_id);
CREATE INDEX IF NOT EXISTS idx_tests_target_symbol  ON tests(target_symbol_id);

-- ─────────────────────────────────────────────────────────────
-- LAYER 6: REPAIR PATTERNS
-- Stores successful LLM repair actions as training signal.
-- When a similar failure recurs, the agent retrieves past repairs
-- and includes them in the prompt as few-shot examples.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS repair_patterns (
    id              SERIAL PRIMARY KEY,
    repository_id   INT         REFERENCES repositories(id) ON DELETE SET NULL,

    -- failure fingerprint
    error_type      TEXT        NOT NULL,    -- NullPointerException | CompileError | TestFailure
    error_message   TEXT,                   -- short excerpt of the error
    failure_hash    TEXT,                   -- sha256(error_type + error_message) for dedup

    -- affected code
    file_path       TEXT,
    symbol_name     TEXT,
    broken_code     TEXT,                   -- the code BEFORE repair

    -- successful repair
    repaired_code   TEXT,                   -- the code AFTER repair
    patch_diff      TEXT,                   -- unified diff of the repair
    llm_model       TEXT,                   -- which LLM produced this repair

    -- outcome
    tests_passed    BOOL        DEFAULT FALSE,
    used_count      INT         DEFAULT 1,  -- how many times this pattern was reused
    last_used_at    TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_repair_error_type    ON repair_patterns(error_type);
CREATE INDEX IF NOT EXISTS idx_repair_hash          ON repair_patterns(failure_hash);
CREATE INDEX IF NOT EXISTS idx_repair_symbol        ON repair_patterns(symbol_name);
CREATE INDEX IF NOT EXISTS idx_repair_repo          ON repair_patterns(repository_id);
CREATE INDEX IF NOT EXISTS idx_repair_passed        ON repair_patterns(tests_passed);
