# memory/experience_retriever.py

import json
from typing import List, Dict, Any, Optional
from memory.experience_models import (
    SessionLocal,
    ExecutionEpisode,
    FailureRecord,
    RepairRecord,
    PlanRecord,
    StrategyRecord
)

class ExperienceRetriever:
    def __init__(self):
        pass

    def find_similar_episodes(self, goal: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Finds past episodes with similar goals or keyword tokens.
        """
        session = SessionLocal()
        try:
            words = [w.strip().lower() for w in goal.split() if len(w.strip()) > 2]
            if not words:
                episodes = session.query(ExecutionEpisode).filter(
                    ExecutionEpisode.goal.ilike(f"%{goal}%")
                ).order_by(ExecutionEpisode.created_at.desc()).limit(limit).all()
            else:
                from sqlalchemy import or_
                conditions = [ExecutionEpisode.goal.ilike(f"%{w}%") for w in words]
                episodes = session.query(ExecutionEpisode).filter(
                    or_(*conditions)
                ).order_by(ExecutionEpisode.created_at.desc()).limit(limit).all()
                
            results = []
            for ep in episodes:
                failures = [f.failure_type for f in ep.failures]
                results.append({
                    "episode_id": ep.episode_id,
                    "goal": ep.goal,
                    "outcome": ep.outcome,
                    "failures_encountered": failures,
                    "created_at": ep.created_at.isoformat()
                })
            return results
        except Exception as e:
            print(f"[ExperienceRetriever] Error finding similar episodes: {e}")
            return []
        finally:
            session.close()

    def get_successful_plans(self, goal_type: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves successful plans matching a given goal type class.
        """
        session = SessionLocal()
        try:
            plans = session.query(PlanRecord).join(
                ExecutionEpisode, PlanRecord.episode_id == ExecutionEpisode.episode_id
            ).filter(
                ExecutionEpisode.outcome == "SUCCESS",
                PlanRecord.goal_type.ilike(f"%{goal_type}%")
            ).order_by(PlanRecord.created_at.desc()).limit(limit).all()
            
            results = []
            for p in plans:
                try:
                    plan_data = json.loads(p.plan_json) if p.plan_json else {}
                except Exception:
                    plan_data = p.plan_json
                results.append({
                    "episode_id": p.episode_id,
                    "goal_type": p.goal_type,
                    "plan": plan_data,
                    "success_rate": p.success_rate
                })
            return results
        except Exception as e:
            print(f"[ExperienceRetriever] Error fetching successful plans: {e}")
            return []
        finally:
            session.close()

    def get_failure_repairs(self, failure_type: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves repair patches that successfully fixed matching failure types in the past.
        """
        session = SessionLocal()
        try:
            repairs = session.query(RepairRecord).join(
                FailureRecord, RepairRecord.failure_record_id == FailureRecord.id
            ).filter(
                FailureRecord.failure_type.ilike(f"%{failure_type}%"),
                RepairRecord.success == 1.0
            ).order_by(RepairRecord.created_at.desc()).limit(limit).all()
            
            results = []
            for r in repairs:
                results.append({
                    "episode_id": r.episode_id,
                    "repair_type": r.repair_type,
                    "target": r.target,
                    "patch": r.patch,
                    "description": r.description
                })
            return results
        except Exception as e:
            print(f"[ExperienceRetriever] Error fetching failure repairs: {e}")
            return []
        finally:
            session.close()
