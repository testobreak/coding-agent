import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.file import File
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from retrieval.hybrid_ranker import HybridRanker


def run_tests():
    print("\n" + "=" * 60)
    print("  HybridRanker Integration Tests")
    print("=" * 60)

    from repository_intelligence.db.connection import Base, engine as db_engine
    Base.metadata.create_all(bind=db_engine)

    session = SessionLocal()
    engine = HybridRanker()

    try:
        print("\n[1] Creating mock repository, files, and symbols...")
        now = datetime.now(timezone.utc)

        # Create mock repository
        repo = Repository(
            name="MockRankingRepo",
            root_path="/mock/ranking/path"
        )
        session.add(repo)
        session.flush()

        # File A: High importance, modified today (Recency = 1.0)
        file_a = File(
            repository_id=repo.id,
            path="backend/src/main/java/com/hrms/employee/HighController.java",
            language="java",
            file_hash="hash_a",
            size_bytes=2000,
            updated_at=now
        )
        # File B: Low importance, modified 10 days ago (Recency = 0.5)
        file_b = File(
            repository_id=repo.id,
            path="backend/src/main/java/com/hrms/employee/MediumService.java",
            language="java",
            file_hash="hash_b",
            size_bytes=1200,
            updated_at=now - timedelta(days=10)
        )
        # File C: Low importance, modified 100 days ago (Recency = 0.2)
        file_c = File(
            repository_id=repo.id,
            path="backend/src/main/java/com/hrms/employee/StaleDao.java",
            language="java",
            file_hash="hash_c",
            size_bytes=800,
            updated_at=now - timedelta(days=100)
        )
        session.add(file_a)
        session.add(file_b)
        session.add(file_c)
        session.flush()

        # Add symbols to File A (High Importance)
        sym_high_1 = Symbol(
            repository_id=repo.id,
            file_id=file_a.id,
            name="HighController",
            qualified_name="com.hrms.employee.HighController",
            symbol_type="CLASS",
            start_line=1,
            end_line=50,
            signature="public class HighController",
            source_hash="sha_high_1"
        )
        sym_high_2 = Symbol(
            repository_id=repo.id,
            file_id=file_a.id,
            name="highMethod",
            qualified_name="com.hrms.employee.HighController.highMethod",
            symbol_type="METHOD",
            start_line=10,
            end_line=30,
            signature="public void highMethod()",
            source_hash="sha_high_2"
        )
        session.add(sym_high_1)
        session.add(sym_high_2)

        # Add symbol to File B (Low Importance)
        sym_med_1 = Symbol(
            repository_id=repo.id,
            file_id=file_b.id,
            name="MediumService",
            qualified_name="com.hrms.employee.MediumService",
            symbol_type="CLASS",
            start_line=1,
            end_line=30,
            signature="public class MediumService",
            source_hash="sha_med_1"
        )
        session.add(sym_med_1)

        # Add symbol to File C (Stale)
        sym_stale_1 = Symbol(
            repository_id=repo.id,
            file_id=file_c.id,
            name="StaleDao",
            qualified_name="com.hrms.employee.StaleDao",
            symbol_type="CLASS",
            start_line=1,
            end_line=20,
            signature="public class StaleDao",
            source_hash="sha_stale_1"
        )
        session.add(sym_stale_1)
        session.flush()

        # Add high symbol-level connectivity relationships to HighController
        rel_1 = SymbolRelationship(
            repository_id=repo.id,
            source_file_id=file_a.id,
            source_symbol_id=sym_high_1.id,
            target_name="com.hrms.employee.MediumService",
            target_symbol_id=sym_med_1.id,
            relationship_type="USES",
            confidence=1.0
        )
        rel_2 = SymbolRelationship(
            repository_id=repo.id,
            source_file_id=file_a.id,
            source_symbol_id=sym_high_2.id,
            target_name="com.hrms.employee.MediumService",
            target_symbol_id=sym_med_1.id,
            relationship_type="CALLS",
            confidence=1.0
        )
        session.add(rel_1)
        session.add(rel_2)
        session.flush()

        print("  [OK] Mock environment populated.")

        # 2. Formulate search candidates returned from mock vector search
        # Results contain a list of {"score": float, "chunk": dict}
        raw_results = [
            {
                "score": 0.80, # High similarity
                "chunk": {
                    "chunk_id": "stale_chunk",
                    "file": "backend/src/main/java/com/hrms/employee/StaleDao.java",
                    "name": "StaleDao",
                    "symbol": "com.hrms.employee.StaleDao",
                    "type": "CLASS"
                }
            },
            {
                "score": 0.70, # Moderate similarity
                "chunk": {
                    "chunk_id": "high_chunk",
                    "file": "backend/src/main/java/com/hrms/employee/HighController.java",
                    "name": "HighController",
                    "symbol": "com.hrms.employee.HighController",
                    "type": "CLASS"
                }
            },
            {
                "score": 0.65, # Moderate similarity
                "chunk": {
                    "chunk_id": "med_chunk",
                    "file": "backend/src/main/java/com/hrms/employee/MediumService.java",
                    "name": "MediumService",
                    "symbol": "com.hrms.employee.MediumService",
                    "type": "CLASS"
                }
            }
        ]

        # 3. Execute hybrid ranking
        print("\n[2] Executing Hybrid Ranking Engine...")
        ranked = engine.rank("HighController", raw_results, session=session)

        # 4. Display ranked results report with full sub-score details
        print("\n=== HYBRID RANKED CONTEXT RESULTS ===")
        # We can temporarily instantiate candidates again to get their scores, or we can print them directly
        # Let's inspect the sub-scores calculated by the engine by running a custom trace
        candidates_trace = []
        file_paths = set()
        symbol_qnames = set()
        for item in raw_results:
            c = item["chunk"]
            file_paths.add(c["file"])
            if c.get("symbol"):
                symbol_qnames.add(c["symbol"])

        # Fetch raw stats for debugging
        symbols_db = session.query(Symbol).filter(Symbol.qualified_name.in_(list(symbol_qnames))).all()
        sym_ids = [s.id for s in symbols_db]
        sym_id_to_qname = {s.id: s.qualified_name for s in symbols_db}

        graph_raw = {q: 0 for q in symbol_qnames}
        if sym_ids:
            inc = session.query(SymbolRelationship.target_symbol_id).filter(SymbolRelationship.target_symbol_id.in_(sym_ids)).all()
            outg = session.query(SymbolRelationship.source_symbol_id).filter(SymbolRelationship.source_symbol_id.in_(sym_ids)).all()
            for (t_id,) in inc:
                q = sym_id_to_qname.get(t_id)
                if q: graph_raw[q] = graph_raw.get(q, 0) + 1
            for (s_id,) in outg:
                q = sym_id_to_qname.get(s_id)
                if q: graph_raw[q] = graph_raw.get(q, 0) + 1

        files_db = session.query(File).filter(File.path.in_(list(file_paths))).all()
        file_raw = {}
        for f in files_db:
            sc = session.query(Symbol.id).filter(Symbol.file_id == f.id).count()
            rc = session.query(SymbolRelationship.id).filter(SymbolRelationship.source_file_id == f.id).count()
            file_raw[f.path] = {
                "updated_at": f.updated_at,
                "importance": sc + rc
            }

        print("=== DEBUG STATS ===")
        print(f"Graph Raw Connections: {graph_raw}")
        print(f"File Raw Importance: {file_raw}")
        print("===================")

        for index, item in enumerate(ranked, 1):
            score = item["score"]
            chunk = item["chunk"]
            print(f"Rank {index}: {chunk['name']} (Composite Score: {score:.4f})")
            print(f"  - File: {chunk['file']}")
            print(f"  - Original vector score: {raw_results[index-1]['score']}")

        # 5. Assertions to confirm correctness
        print("\n[3] Running assertions...")
        
        # HighController has high relationship counts, high file importance, and was updated today.
        # Even though StaleDao had a slightly higher initial raw similarity score (0.80 vs 0.70),
        # HighController should overtake it in hybrid ranking!
        top_rank = ranked[0]["chunk"]["name"]
        assert top_rank == "HighController", f"Expected HighController to rank 1st, got {top_rank}"
        print("  [OK] Success: HighController successfully overtook StaleDao in ranking.")

        # StaleDao should rank last due to old recency score and low connectivity
        last_rank = ranked[-1]["chunk"]["name"]
        assert last_rank == "StaleDao", f"Expected StaleDao to rank last, got {last_rank}"
        print("  [OK] Success: StaleDao penalized for low recency and low connectivity.")

        print("\n" + "=" * 60)
        print("  ALL HYBRID RANKING TESTS PASSED! [OK]")
        print("=" * 60 + "\n")

    except AssertionError as ae:
        print(f"\n[FAIL] ASSERTION ERROR: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("[Cleanup] Rolling back transaction to keep database clean...")
        session.rollback()
        session.close()


if __name__ == "__main__":
    run_tests()
