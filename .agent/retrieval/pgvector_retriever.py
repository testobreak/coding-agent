import json
import uuid
import time
import psycopg
from psycopg_pool import ConnectionPool
from typing import List, Dict, Any, Optional

class PgVectorRetriever:
    """
    Production-grade PostgreSQL + pgvector ANN retriever.
    Manages a connection pool and executes low-latency semantic chunk retrieval.
    """

    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        # Default config matching target environment
        self.config = {
            "dbname": "local_cursor",
            "user": "ashish",
            "host": "localhost",
            "port": 5432,
            "connect_timeout": 5
        }
        if db_config:
            self.config.update(db_config)

        # Connection pool initialization with psycopg3
        conninfo = f"dbname={self.config['dbname']} user={self.config['user']} host={self.config['host']} port={self.config['port']} connect_timeout={self.config['connect_timeout']}"
        print(f"[PgVectorRetriever] Initializing connection pool for {self.config['dbname']}...")
        self.pool = ConnectionPool(conninfo=conninfo, min_size=2, max_size=10)

    def close(self):
        """Close connection pool."""
        if hasattr(self, "pool"):
            self.pool.close()

    def top_k(self, query_embedding: List[float], k: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves the top-k nearest neighbor candidates from PostgreSQL.
        Target latency: < 20 ms.
        """
        start_time = time.time()
        
        # Format query embedding to a list
        if hasattr(query_embedding, "tolist"):
            emb_list = query_embedding.tolist()
        else:
            emb_list = list(query_embedding)

        query = """
        SELECT
            chunk_id,
            file_path,
            symbol,
            symbol_path,
            content,
            start_line,
            end_line,
            imports,
            1 - (embedding <=> %s::vector) AS similarity
        FROM code_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """

        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    # Execute query with timeouts
                    cur.execute("SET statement_timeout = 1000")  # 1s timeout
                    cur.execute(query, (emb_list, emb_list, k))
                    rows = cur.fetchall()
                    
                    candidates = []
                    for row in rows:
                        chunk_id, file_path, symbol, symbol_path, content, start_line, end_line, imports, similarity = row
                        
                        # Deserialize imports from JSONB / string if necessary
                        parsed_imports = []
                        if imports:
                            if isinstance(imports, list):
                                parsed_imports = imports
                            elif isinstance(imports, str):
                                try:
                                    parsed_imports = json.loads(imports)
                                except Exception:
                                    parsed_imports = []

                        candidates.append({
                            "chunk_id": str(chunk_id),
                            "file_path": file_path,
                            "symbol": symbol,
                            "symbol_path": symbol_path,
                            "content": content,
                            "start_line": start_line,
                            "end_line": end_line,
                            "imports": parsed_imports,
                            "semantic_score": float(similarity)
                        })
                    
                    elapsed = (time.time() - start_time) * 1000
                    print(f"[PgVectorRetriever] Retrieved {len(candidates)} candidates in {elapsed:.2f} ms")
                    return candidates
                    
        except Exception as e:
            print(f"[PgVectorRetriever Error] Retrieval failed: {e}")
            # Graceful degradation: return empty candidate pool
            return []

    def upsert_embeddings(self, chunks: List[Dict[str, Any]], embeddings: Any) -> None:
        """
        Bulk upserts code chunks and their embeddings into the PostgreSQL database.
        Uses deterministic uuid5 namespaces to convert string IDs to UUIDs.
        """
        if not chunks:
            return

        start_time = time.time()
        print(f"[PgVectorRetriever] Bulk upserting {len(chunks)} chunks...")

        # Prepare lists for batching
        if hasattr(embeddings, "tolist"):
            emb_list = embeddings.tolist()
        else:
            emb_list = [list(e) for e in embeddings]

        query = """
        INSERT INTO code_chunks (
            chunk_id,
            file_path,
            symbol,
            symbol_path,
            language,
            start_line,
            end_line,
            content,
            imports,
            hash,
            embedding
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
        ON CONFLICT (chunk_id) DO UPDATE SET
            file_path = EXCLUDED.file_path,
            symbol = EXCLUDED.symbol,
            symbol_path = EXCLUDED.symbol_path,
            language = EXCLUDED.language,
            start_line = EXCLUDED.start_line,
            end_line = EXCLUDED.end_line,
            content = EXCLUDED.content,
            imports = EXCLUDED.imports,
            hash = EXCLUDED.hash,
            embedding = EXCLUDED.embedding,
            updated_at = NOW();
        """

        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    for idx, chunk in enumerate(chunks):
                        raw_cid = chunk.get("chunk_id", str(idx))
                        
                        # Generate a deterministic UUID if it's not a valid UUID string
                        try:
                            cid = uuid.UUID(raw_cid)
                        except (ValueError, AttributeError):
                            # Generate a namespace UUID v5 based on the original chunk_id
                            cid = uuid.uuid5(uuid.NAMESPACE_DNS, raw_cid)

                        file_path = chunk.get("file", "")
                        symbol = chunk.get("name") or chunk.get("symbol") or ""
                        
                        # Construct a clean symbol_path (FQN style if class parent exists)
                        parent = chunk.get("parent") or ""
                        symbol_path = f"{parent}.{symbol}" if parent and symbol else (symbol or file_path)

                        # Extract language from extension
                        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
                        language = ext.upper() if ext else "UNKNOWN"

                        start_line = chunk.get("start_line") or chunk.get("line") or 1
                        end_line = chunk.get("end_line") or start_line
                        content = chunk.get("code") or chunk.get("content") or ""
                        imports = chunk.get("imports") or []
                        
                        # Generate hash of content for change detection
                        import hashlib
                        chunk_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

                        cur.execute(query, (
                            cid,
                            file_path,
                            symbol,
                            symbol_path,
                            language,
                            start_line,
                            end_line,
                            content,
                            json.dumps(imports),
                            chunk_hash,
                            emb_list[idx]
                        ))
                
                conn.commit()
                elapsed = time.time() - start_time
                print(f"[PgVectorRetriever] Bulk upserted {len(chunks)} chunks in {elapsed:.2f}s")
                
        except Exception as e:
            print(f"[PgVectorRetriever Error] Bulk upsert failed: {e}")
            raise e
