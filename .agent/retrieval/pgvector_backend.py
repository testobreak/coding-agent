import time
import json
import hashlib
from typing import List, Dict, Any, Optional, Protocol
import psycopg
from psycopg_pool import ConnectionPool

class ANNBackend(Protocol):
    """
    Protocol defining the interface for all Approximate Nearest Neighbor backends.
    """
    def search(
        self,
        query_vector: List[float],
        k: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        ...


class EmbeddingSearchCache:
    """
    Cache for query results mapping a query hash + filters hash to search candidates.
    Supports a TTL of 30-60 seconds.
    """
    def __init__(self, ttl_seconds: float = 30.0):
        self.ttl = ttl_seconds
        self.cache = {}  # key -> (timestamp, value)

    def get(self, query_vector: List[float], filters: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        cache_key = self._make_key(query_vector, filters)
        if cache_key in self.cache:
            ts, val = self.cache[cache_key]
            if time.time() - ts < self.ttl:
                return val
            else:
                del self.cache[cache_key]
        return None

    def set(self, query_vector: List[float], filters: Optional[Dict[str, Any]] = None, value: List[Dict[str, Any]] = None):
        cache_key = self._make_key(query_vector, filters)
        self.cache[cache_key] = (time.time(), value)

    def _make_key(self, query_vector: List[float], filters: Optional[Dict[str, Any]] = None) -> str:
        # Construct a stable key string from vector floats (rounded to 4 decimals) and filters
        rounded_vec = [round(x, 4) for x in query_vector]
        key_str = f"{rounded_vec}:{json.dumps(filters or {}, sort_keys=True)}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


class PgVectorBackend:
    """
    Production-grade pgvector HNSW ANN search backend.
    Inherits database configuration and runs migrations automatically.
    """
    def __init__(self, db_config: Optional[Dict[str, Any]] = None, cache_ttl: float = 30.0):
        self.config = {
            "dbname": "local_cursor",
            "user": "ashish",
            "host": "localhost",
            "port": 5432,
            "connect_timeout": 5
        }
        if db_config:
            self.config.update(db_config)

        conninfo = f"dbname={self.config['dbname']} user={self.config['user']} host={self.config['host']} port={self.config['port']} connect_timeout={self.config['connect_timeout']}"
        print(f"[PgVectorBackend] Connecting to database '{self.config['dbname']}'...")
        self.pool = ConnectionPool(conninfo=conninfo, min_size=2, max_size=10)
        self.cache = EmbeddingSearchCache(ttl_seconds=cache_ttl)
        self._run_migrations()

    def _run_migrations(self):
        """
        Executes required database migrations:
        - Enables the pgvector extension.
        - Adds pgvector column to embeddings table if missing.
        - Backfills the vector_embedding column from legacy JSONB vector values.
        - Creates a HNSW index on the vector_embedding column for low-latency search.
        """
        print("[PgVectorBackend] Executing database schema migrations...")
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute("ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS vector_embedding vector(384)")
                    
                    # Backfill vector_embedding from JSONB vector if it's null
                    # Cast JSONB array to a string representation and then cast to ::vector
                    cur.execute("""
                        UPDATE embeddings 
                        SET vector_embedding = vector::text::vector 
                        WHERE vector_embedding IS NULL AND vector IS NOT NULL
                    """)
                    
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx 
                        ON embeddings 
                        USING hnsw (vector_embedding vector_cosine_ops)
                    """)
                conn.commit()
                print("[PgVectorBackend] Migrations completed successfully.")
        except Exception as e:
            print(f"[PgVectorBackend Warning] Migrations warning: {e}")

    def close(self):
        """Shutdown the connection pool."""
        if hasattr(self, "pool"):
            self.pool.close()

    def search(
        self,
        query_vector: List[float],
        k: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Main query path. Checks the cache first, then executes the pgvector search.
        If strict pre-filtering returns empty results, falls back to relaxed pre-filtering.
        """
        # 1. Check warm cache
        cached_results = self.cache.get(query_vector, filters)
        if cached_results is not None:
            return cached_results

        # 2. Execute query with strict filters
        results = self._execute_search(query_vector, k, filters)

        # 3. Graceful degradation: If empty results and symbol filter was active, relax it
        if not results and filters and "symbol" in filters:
            relaxed_filters = filters.copy()
            del relaxed_filters["symbol"]
            print(f"[PgVectorBackend] Strict symbol filter '{filters['symbol']}' returned no candidates. Retrying with relaxed filters...")
            results = self._execute_search(query_vector, k, relaxed_filters)

        # 3.5 Graceful degradation: If empty results and workspace routing roots filter was active, relax it
        if not results and filters and "roots" in filters:
            relaxed_filters = filters.copy()
            del relaxed_filters["roots"]
            print(f"[PgVectorBackend] Strict roots filter '{filters['roots']}' returned no candidates. Retrying with relaxed filters...")
            results = self._execute_search(query_vector, k, relaxed_filters)

        # 4. Populate cache
        self.cache.set(query_vector, filters, results)
        return results

    def _execute_search(
        self,
        query_vector: List[float],
        k: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        start_time = time.time()
        
        # Format query embedding to a list
        if hasattr(query_vector, "tolist"):
            emb_list = query_vector.tolist()
        else:
            emb_list = list(query_vector)

        # Build SQL dynamically based on intent classifier pre-filtering
        query_sql = """
        SELECT
            e.id AS embedding_id,
            e.symbol_id,
            e.file_id,
            s.name AS symbol,
            s.qualified_name AS symbol_path,
            f.path AS file_path,
            s.start_line,
            s.end_line,
            s.signature AS content,
            1 - (e.vector_embedding <=> %s::vector) AS similarity
        FROM embeddings e
        LEFT JOIN symbols s ON s.id = e.symbol_id
        LEFT JOIN files f ON f.id = e.file_id
        """
        
        where_clauses = []
        params = [emb_list]

        if filters:
            if filters.get("language"):
                where_clauses.append("f.language = %s")
                params.append(filters["language"].lower())
            if filters.get("roots"):
                root_clauses = []
                for root in filters["roots"]:
                    root_clauses.append("f.path LIKE %s")
                    params.append(f"{root}%")
                if root_clauses:
                    where_clauses.append("(" + " OR ".join(root_clauses) + ")")
            if filters.get("domain"):
                where_clauses.append("f.path ILIKE %s")
                params.append(f"%{filters['domain']}%")
            elif filters.get("symbol"):
                # Matches exact name or qualified name
                where_clauses.append("(s.name = %s OR s.qualified_name = %s)")
                params.append(filters["symbol"])
                params.append(filters["symbol"])

        if where_clauses:
            query_sql += " WHERE " + " AND ".join(where_clauses)

        query_sql += " ORDER BY e.vector_embedding <=> %s::vector LIMIT %s"
        params.append(emb_list)
        params.append(k)

        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    # Timeout limit: 1s
                    cur.execute("SET statement_timeout = 1000")
                    cur.execute(query_sql, tuple(params))
                    rows = cur.fetchall()

                    if not rows:
                        return []

                    # Batch retrieve imports for all candidates
                    symbol_ids = [row[1] for row in rows if row[1]]
                    file_ids = [row[2] for row in rows if row[2]]

                    imports_map = {}
                    if symbol_ids or file_ids:
                        # Construct a list of UUID string conversions or objects for query parameters
                        uuid_syms = [str(sid) for sid in symbol_ids]
                        uuid_files = [str(fid) for fid in file_ids]
                        
                        import_query = """
                        SELECT source_symbol_id, source_file_id, target_name
                        FROM symbol_relationships
                        WHERE relationship_type = 'IMPORTS' AND (
                            source_symbol_id = ANY(%s) OR source_file_id = ANY(%s)
                        )
                        """
                        cur.execute(import_query, (uuid_syms, uuid_files))
                        rel_rows = cur.fetchall()
                        for rel in rel_rows:
                            source_sym, source_file, target_name = rel
                            if not target_name:
                                continue
                            key = str(source_sym) if source_sym else str(source_file)
                            if key not in imports_map:
                                imports_map[key] = []
                            imports_map[key].append(target_name)

                    # Build structured candidates
                    candidates = []
                    for row in rows:
                        emb_id, symbol_id, file_id, symbol, symbol_path, file_path, start_line, end_line, content, similarity = row
                        
                        # Fetch imports from map
                        key = str(symbol_id) if symbol_id else str(file_id)
                        imports = imports_map.get(key, [])

                        candidates.append({
                            "chunk_id": str(emb_id),
                            "file_path": file_path or "",
                            "symbol": symbol or "",
                            "symbol_path": symbol_path or "",
                            "content": content or file_path or "",
                            "start_line": start_line or 1,
                            "end_line": end_line or 1,
                            "imports": imports,
                            "semantic_score": float(similarity)
                        })

                    elapsed = (time.time() - start_time) * 1000
                    print(f"[PgVectorBackend] Query executed in {elapsed:.2f} ms (candidates={len(candidates)}, filters={filters})")
                    return candidates

        except Exception as e:
            print(f"[PgVectorBackend Error] Search failed: {e}")
            return []


def extract_filters(query: str, active_file: Optional[str] = None) -> Dict[str, Any]:
    filters = {}
    
    # Workspace routing target roots
    from retrieval.workspace_router import classify_workspace_target
    roots = classify_workspace_target(query, active_file)
    if roots:
        filters["roots"] = roots
    
    # 1. Detect language
    q_lower = query.lower()
    if "java" in q_lower:
        filters["language"] = "java"
    elif "python" in q_lower or "py" in q_lower:
        filters["language"] = "python"
    elif "typescript" in q_lower or "ts" in q_lower:
        filters["language"] = "typescript"
    elif "javascript" in q_lower or "js" in q_lower:
        filters["language"] = "javascript"
    elif active_file:
        ext = active_file.rsplit(".", 1)[-1].lower() if "." in active_file else ""
        if ext == "java":
            filters["language"] = "java"
        elif ext in ("py", "pyw"):
            filters["language"] = "python"
        elif ext in ("ts", "tsx"):
            filters["language"] = "typescript"
        elif ext in ("js", "jsx"):
            filters["language"] = "javascript"
            
    # 2. Detect target symbol name (CamelCase)
    import re
    camel_case = re.findall(r'\b[A-Z][a-z0-9]+[A-Z][a-zA-Z0-9]*\b', query)
    if camel_case:
        stop_words = {"employee", "user", "admin", "client", "server"}
        valid_cands = [c for c in camel_case if c.lower() not in stop_words]
        if valid_cands:
            filters["symbol"] = valid_cands[0]
        else:
            filters["symbol"] = camel_case[0]
            
        # Extract domain/module prefix for broader file matching (e.g. EmployeeService -> employee)
        parts = re.findall(r'[A-Z][a-z0-9]+|[A-Z]+(?=[A-Z][a-z]|\b)', filters["symbol"])
        if parts:
            filters["domain"] = parts[0].lower()
        
    return filters

