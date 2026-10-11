from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ashish@localhost:5432/local_cursor"
)

# Determine the absolute path for SQLite fallback
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
agent_dir = os.path.join(PROJECT_ROOT, ".agent")
if os.path.exists(agent_dir) and os.path.isdir(agent_dir):
    SQLITE_DB_PATH = os.path.join(agent_dir, "repository_intelligence.db")
else:
    SQLITE_DB_PATH = os.path.join(PROJECT_ROOT, "repository_intelligence.db")

# Test postgresql connection if DATABASE_URL is postgresql
if DATABASE_URL.startswith("postgresql"):
    try:
        test_engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 2})
        with test_engine.connect() as conn:
            pass
        engine = test_engine
    except Exception as e:
        print(f"[Database] PostgreSQL connection failed: {e}. Falling back to SQLite at: {SQLITE_DB_PATH}")
        engine = create_engine(f"sqlite:///{SQLITE_DB_PATH}")
else:
    engine = create_engine(DATABASE_URL)

from sqlalchemy import event
import sqlite3
import uuid

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

from sqlalchemy.types import UserDefinedType

class PGVectorType(UserDefinedType):
    def get_col_spec(self, **kw):
        return "vector(384)"
        
    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return str(value)
            return value
        return process

@compiles(PGVectorType, "sqlite")
def compile_pgvector_sqlite(element, compiler, **kw):
    return "TEXT"

Base = declarative_base()

def create_all_tables(bind_engine):
    """
    Helper to initialize standard ORM models and custom transaction/compaction tables
    on both SQLite and PostgreSQL database engines.
    """
    from sqlalchemy import text
    # Import standard models so they register on Base
    from repository_intelligence.models.repository import Repository
    from repository_intelligence.models.file import File
    from repository_intelligence.models.symbol import (
        Symbol,
        Embedding,
        IndexJob,
        RepairPattern,
        SymbolRelationship,
        Test
    )
    Base.metadata.create_all(bind=bind_engine)

    # Custom tables creation
    is_sqlite = "sqlite" in str(bind_engine.url)
    with bind_engine.begin() as conn:
        # 1. modification_checkpoints
        sql_mc = """
            CREATE TABLE IF NOT EXISTS modification_checkpoints (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                goal TEXT,
                modified_files TEXT[],
                validation_status TEXT NOT NULL,
                rollback_reason TEXT
            );
        """
        if is_sqlite:
            sql_mc = sql_mc.replace("TEXT[]", "TEXT")
        conn.execute(text(sql_mc))
        
        # 2. task_summaries
        sql_ts = """
            CREATE TABLE IF NOT EXISTS task_summaries (
                id SERIAL PRIMARY KEY,
                task_id TEXT,
                summary TEXT,
                start_step INTEGER,
                end_step INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        if is_sqlite:
            sql_ts = sql_ts.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        conn.execute(text(sql_ts))
        
        # 3. task_events
        sql_te = """
            CREATE TABLE IF NOT EXISTS task_events (
                id SERIAL PRIMARY KEY,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        if is_sqlite:
            sql_te = sql_te.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT").replace("JSONB", "JSON")
        conn.execute(text(sql_te))
        
        # 4. Indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_task_events_type ON task_events(event_type);"))

# Auto-create schema for database connections
try:
    create_all_tables(engine)
except ImportError:
    # Ignore circular imports silently during boot; calling scripts will handle setup
    pass
except Exception as e:
    print(f"[Database] Schema auto-creation warning: {e}")



