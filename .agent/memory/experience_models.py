# memory/experience_models.py

import os
import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, ForeignKey, Text, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import sqlite3

EXPERIENCE_DATABASE_URL = os.getenv(
    "EXPERIENCE_DATABASE_URL",
    "postgresql://postgres:admin@localhost:5432/agent_experience"
)

# Determine the absolute path for SQLite fallback
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
agent_dir = os.path.join(PROJECT_ROOT, ".agent")
if os.path.exists(agent_dir) and os.path.isdir(agent_dir):
    SQLITE_DB_PATH = os.path.join(agent_dir, "experience.db")
else:
    SQLITE_DB_PATH = os.path.join(PROJECT_ROOT, "experience.db")

# Setup database engine
if EXPERIENCE_DATABASE_URL.startswith("postgresql"):
    try:
        test_engine = create_engine(EXPERIENCE_DATABASE_URL, connect_args={"connect_timeout": 2})
        with test_engine.connect() as conn:
            pass
        engine = test_engine
    except Exception:
        fallback_url = f"sqlite:///{SQLITE_DB_PATH}"
        print(f"[ExperienceDatabase] PostgreSQL connection failed. Falling back to SQLite ({fallback_url})...")
        EXPERIENCE_DATABASE_URL = fallback_url
        engine = create_engine(EXPERIENCE_DATABASE_URL)
else:
    engine = create_engine(EXPERIENCE_DATABASE_URL)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

class ExecutionEpisode(Base):
    __tablename__ = "episodes"
    
    episode_id = Column(String, primary_key=True)
    goal = Column(Text, nullable=False)
    repository_id = Column(String, nullable=False)
    task_graph_id = Column(String, nullable=True)
    outcome = Column(String, default="PENDING")  # PENDING, SUCCESS, FAILED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    events = relationship("ExecutionEvent", back_populates="episode", cascade="all, delete-orphan")
    failures = relationship("FailureRecord", back_populates="episode", cascade="all, delete-orphan")
    repairs = relationship("RepairRecord", back_populates="episode", cascade="all, delete-orphan")
    plans = relationship("PlanRecord", back_populates="episode", cascade="all, delete-orphan")

class ExecutionEvent(Base):
    __tablename__ = "events"
    
    event_id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(String, ForeignKey("episodes.episode_id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String, nullable=False)  # e.g., PLAN_CREATED, TASK_STARTED, SYMBOL_EDITED, BUILD_FAILED, REPAIR_APPLIED, BUILD_PASSED, TASK_COMPLETED
    metadata_json = Column(Text, nullable=True)  # JSON-serialized metadata

    episode = relationship("ExecutionEpisode", back_populates="events")

class FailureRecord(Base):
    __tablename__ = "failures"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(String, ForeignKey("episodes.episode_id", ondelete="CASCADE"), nullable=False)
    failure_type = Column(String, nullable=False)  # MISSING_IMPORT, UNDEFINED_SYMBOL, SYNTAX_ERROR, TEST_FAILURE, etc.
    file_path = Column(Text, nullable=True)
    line = Column(Integer, nullable=True)
    symbol = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    episode = relationship("ExecutionEpisode", back_populates="failures")
    repairs = relationship("RepairRecord", back_populates="failure")

class RepairRecord(Base):
    __tablename__ = "repairs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(String, ForeignKey("episodes.episode_id", ondelete="CASCADE"), nullable=False)
    failure_record_id = Column(Integer, ForeignKey("failures.id", ondelete="SET NULL"), nullable=True)
    repair_type = Column(String, nullable=False)  # repair_imports, repair_compilation, repair_symbol, repair_failure
    target = Column(Text, nullable=True)
    patch = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    success = Column(Float, default=0.0)  # 1.0 for success, 0.0 for failure
    created_at = Column(DateTime, default=datetime.utcnow)

    episode = relationship("ExecutionEpisode", back_populates="repairs")
    failure = relationship("FailureRecord", back_populates="repairs")

class PlanRecord(Base):
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(String, ForeignKey("episodes.episode_id", ondelete="CASCADE"), nullable=False)
    goal_type = Column(String, nullable=False)
    plan_json = Column(Text, nullable=False)  # JSON-serialized task nodes / DAG representation
    success_rate = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    episode = relationship("ExecutionEpisode", back_populates="plans")

class StrategyRecord(Base):
    __tablename__ = "strategies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_type = Column(String, nullable=False, unique=True)
    strategy_json = Column(Text, nullable=False)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def create_experience_tables():
    Base.metadata.create_all(bind=engine)
