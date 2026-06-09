CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE repositories (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    name TEXT NOT NULL,

    root_path TEXT NOT NULL,

    created_at TIMESTAMPTZ
        DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        DEFAULT NOW()
);

CREATE TABLE files (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    repository_id UUID NOT NULL
        REFERENCES repositories(id)
        ON DELETE CASCADE,

    path TEXT NOT NULL,

    language TEXT NOT NULL,

    file_hash TEXT NOT NULL,

    size_bytes BIGINT NOT NULL,

    updated_at TIMESTAMPTZ
        DEFAULT NOW(),

    UNIQUE(repository_id, path)
);

CREATE TABLE symbols (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    repository_id UUID NOT NULL
        REFERENCES repositories(id)
        ON DELETE CASCADE,

    file_id UUID NOT NULL
        REFERENCES files(id)
        ON DELETE CASCADE,

    name TEXT NOT NULL,

    qualified_name TEXT NOT NULL,

    symbol_type TEXT NOT NULL,

    parent_symbol_id UUID
        REFERENCES symbols(id)
        ON DELETE CASCADE,

    start_line INTEGER NOT NULL,

    end_line INTEGER NOT NULL,

    signature TEXT,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    source_hash TEXT NOT NULL,

    updated_at TIMESTAMPTZ
        DEFAULT NOW(),

    UNIQUE(repository_id, qualified_name, symbol_type)
);

CREATE INDEX idx_symbols_file_id
    ON symbols(file_id);

CREATE INDEX idx_symbols_repository_name
    ON symbols(repository_id, name);

CREATE TABLE symbol_relationships (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    repository_id UUID NOT NULL
        REFERENCES repositories(id)
        ON DELETE CASCADE,

    source_symbol_id UUID
        REFERENCES symbols(id)
        ON DELETE CASCADE,

    target_symbol_id UUID
        REFERENCES symbols(id)
        ON DELETE CASCADE,

    source_file_id UUID
        REFERENCES files(id)
        ON DELETE CASCADE,

    target_name TEXT,

    relationship_type TEXT NOT NULL,

    confidence NUMERIC(4,3) NOT NULL
        DEFAULT 1.000,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ
        DEFAULT NOW()
);

CREATE INDEX idx_symbol_relationships_source
    ON symbol_relationships(source_symbol_id);

CREATE INDEX idx_symbol_relationships_target
    ON symbol_relationships(target_symbol_id);

CREATE INDEX idx_symbol_relationships_type
    ON symbol_relationships(repository_id, relationship_type);

CREATE TABLE embeddings (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    repository_id UUID NOT NULL
        REFERENCES repositories(id)
        ON DELETE CASCADE,

    file_id UUID
        REFERENCES files(id)
        ON DELETE CASCADE,

    symbol_id UUID
        REFERENCES symbols(id)
        ON DELETE CASCADE,

    scope TEXT NOT NULL,

    content_hash TEXT NOT NULL,

    embedding_model TEXT NOT NULL,

    dimensions INTEGER NOT NULL,

    vector JSONB NOT NULL,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ
        DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        DEFAULT NOW(),

    CHECK (
        (file_id IS NOT NULL) OR
        (symbol_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX idx_embeddings_file_scope_model
    ON embeddings(file_id, scope, embedding_model)
    WHERE symbol_id IS NULL;

CREATE UNIQUE INDEX idx_embeddings_symbol_scope_model
    ON embeddings(symbol_id, scope, embedding_model)
    WHERE symbol_id IS NOT NULL;

CREATE TABLE index_jobs (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    repository_id UUID NOT NULL
        REFERENCES repositories(id)
        ON DELETE CASCADE,

    status TEXT NOT NULL,

    reason TEXT NOT NULL,

    started_at TIMESTAMPTZ
        DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    scanned_files INTEGER NOT NULL
        DEFAULT 0,

    changed_files INTEGER NOT NULL
        DEFAULT 0,

    changed_symbols INTEGER NOT NULL
        DEFAULT 0,

    error TEXT,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb
);

CREATE INDEX idx_index_jobs_repository_started
    ON index_jobs(repository_id, started_at DESC);

CREATE TABLE tests (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    repository_id UUID NOT NULL
        REFERENCES repositories(id)
        ON DELETE CASCADE,

    file_id UUID NOT NULL
        REFERENCES files(id)
        ON DELETE CASCADE,

    symbol_id UUID
        REFERENCES symbols(id)
        ON DELETE SET NULL,

    name TEXT NOT NULL,

    framework TEXT,

    target_symbol_id UUID
        REFERENCES symbols(id)
        ON DELETE SET NULL,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    updated_at TIMESTAMPTZ
        DEFAULT NOW(),

    UNIQUE(repository_id, file_id, name)
);

CREATE INDEX idx_tests_target_symbol
    ON tests(target_symbol_id);

CREATE TABLE repair_patterns (

    id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    repository_id UUID
        REFERENCES repositories(id)
        ON DELETE CASCADE,

    name TEXT NOT NULL,

    language TEXT,

    problem_signature TEXT NOT NULL,

    repair_strategy TEXT NOT NULL,

    confidence NUMERIC(4,3) NOT NULL
        DEFAULT 0.500,

    examples JSONB NOT NULL
        DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ
        DEFAULT NOW(),

    updated_at TIMESTAMPTZ
        DEFAULT NOW()
);

CREATE INDEX idx_repair_patterns_signature
    ON repair_patterns(language, problem_signature);
