# observability/metrics_engine.py

import json
from pathlib import Path
from typing import Dict, Any, List

class MetricsEngine:
    @staticmethod
    def calculate_metrics(log_file_path: str = None) -> Dict[str, Any]:
        if log_file_path is None:
            log_file_path = str(Path(__file__).resolve().parent.parent / "logs" / "cursor_events.jsonl")
        log_path = Path(log_file_path)
        if not log_path.exists():
            return {
                "acceptance_rate": 0.0,
                "patch_success_rate": 0.0,
                "retrieval_mrr": 0.0,
                "retrieval_hit_at_1": 0.0,
                "retrieval_hit_at_3": 0.0,
                "retrieval_hit_at_10": 0.0,
                "duplicate_candidate_ratio": 0.0,
                "p50_validation_latency": 0.0,
                "p90_validation_latency": 0.0,
                "p99_validation_latency": 0.0,
                "false_validation_rate": 0.0
            }

        events: List[Dict[str, Any]] = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line.strip()))
        except Exception:
            pass

        # Group by request_id
        req_events: Dict[str, List[Dict[str, Any]]] = {}
        for ev in events:
            req_events.setdefault(ev["request_id"], []).append(ev)

        # 1. Acceptance rate & Patch success rate
        total_proposals = 0
        accepted_proposals = 0
        successful_patches = 0
        total_patches = 0
        
        # 2. Retrieval metrics
        mrr_sum = 0.0
        retrieval_calls = 0
        hit_1 = 0
        hit_3 = 0
        hit_10 = 0
        total_duplicate_ratio = 0.0

        # 3. Validation latency & false validations
        validation_latencies = []
        total_validations = 0
        unnecessary_validations = 0

        for req_id, list_evs in req_events.items():
            for ev in list_evs:
                etype = ev["event_type"]
                payload = ev["payload"]
                
                if etype == "user_accepted":
                    total_proposals += 1
                    if payload.get("accepted", False):
                        accepted_proposals += 1
                        
                elif etype == "patch_applied":
                    total_patches += 1
                    if payload.get("success", False):
                        successful_patches += 1
                        
                elif etype == "retrieval_completed":
                    retrieval_calls += 1
                    # hit positions
                    rank = payload.get("hit_rank", 0) # 1-based index of correct file, 0 if not found
                    if rank == 1:
                        hit_1 += 1
                        hit_3 += 1
                        hit_10 += 1
                        mrr_sum += 1.0
                    elif 1 < rank <= 3:
                        hit_3 += 1
                        hit_10 += 1
                        mrr_sum += 1.0 / rank
                    elif 3 < rank <= 10:
                        hit_10 += 1
                        mrr_sum += 1.0 / rank
                        
                    total_duplicate_ratio += payload.get("duplicate_candidate_ratio", 0.0)
                    
                elif etype == "validation_finished":
                    total_validations += 1
                    lat = payload.get("latency_ms", 0.0)
                    validation_latencies.append(lat)
                    if payload.get("unnecessary", False):
                        unnecessary_validations += 1

        # Percentile helper
        def get_percentile(sorted_list, pct):
            if not sorted_list:
                return 0.0
            idx = int(len(sorted_list) * pct)
            return sorted_list[min(idx, len(sorted_list) - 1)]

        sorted_lats = sorted(validation_latencies)

        return {
            "acceptance_rate": round(accepted_proposals / total_proposals, 4) if total_proposals > 0 else 1.0,
            "patch_success_rate": round(successful_patches / total_patches, 4) if total_patches > 0 else 1.0,
            "retrieval_mrr": round(mrr_sum / retrieval_calls, 4) if retrieval_calls > 0 else 1.0,
            "retrieval_hit_at_1": round(hit_1 / retrieval_calls, 4) if retrieval_calls > 0 else 1.0,
            "retrieval_hit_at_3": round(hit_3 / retrieval_calls, 4) if retrieval_calls > 0 else 1.0,
            "retrieval_hit_at_10": round(hit_10 / retrieval_calls, 4) if retrieval_calls > 0 else 1.0,
            "duplicate_candidate_ratio": round(total_duplicate_ratio / retrieval_calls, 4) if retrieval_calls > 0 else 0.0,
            "p50_validation_latency": round(get_percentile(sorted_lats, 0.50), 2),
            "p90_validation_latency": round(get_percentile(sorted_lats, 0.90), 2),
            "p99_validation_latency": round(get_percentile(sorted_lats, 0.99), 2),
            "false_validation_rate": round(unnecessary_validations / total_validations, 4) if total_validations > 0 else 0.0
        }
