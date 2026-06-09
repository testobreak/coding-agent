# memory/experience_store.py

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from memory.experience_models import (
    SessionLocal,
    ExecutionEpisode,
    ExecutionEvent,
    FailureRecord,
    RepairRecord,
    PlanRecord,
    StrategyRecord,
    create_experience_tables
)

class ExecutionMemory:
    def __init__(self):
        # Ensure database tables exist
        create_experience_tables()

    def start_episode(self, goal: str, plan_id: str, repository_id: str = "unknown", task_graph_id: str = None) -> str:
        """
        Starts a new execution episode. Maps one-to-one with the plan_id.
        """
        session = SessionLocal()
        try:
            # Check if episode already exists (in case of resumed execution)
            episode = session.query(ExecutionEpisode).filter(ExecutionEpisode.episode_id == plan_id).first()
            if not episode:
                episode = ExecutionEpisode(
                    episode_id=plan_id,
                    goal=goal,
                    repository_id=repository_id,
                    task_graph_id=task_graph_id or plan_id,
                    outcome="PENDING",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(episode)
                session.commit()
                
            session.close()
            
            # Log initial event
            self.log_event(plan_id, "PLAN_CREATED", {"goal": goal, "plan_id": plan_id})
            return plan_id
        except Exception as e:
            session.rollback()
            session.close()
            print(f"[ExecutionMemory] Error starting episode: {e}")
            return plan_id

    def log_event(self, episode_id: str, event_type: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Logs an execution event under the given episode.
        """
        session = SessionLocal()
        try:
            meta_str = json.dumps(metadata) if metadata else None
            event = ExecutionEvent(
                episode_id=episode_id,
                event_type=event_type,
                timestamp=datetime.utcnow(),
                metadata_json=meta_str
            )
            session.add(event)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ExecutionMemory] Error logging event {event_type}: {e}")
        finally:
            session.close()

    def log_failure(self, episode_id: str, failure_type: str, file_path: Optional[str] = None, 
                    line: Optional[int] = None, symbol: Optional[str] = None, message: Optional[str] = None) -> int:
        """
        Logs a failure diagnostic record.
        """
        session = SessionLocal()
        failure_id = -1
        try:
            failure = FailureRecord(
                episode_id=episode_id,
                failure_type=failure_type,
                file_path=file_path,
                line=line,
                symbol=symbol,
                message=message,
                created_at=datetime.utcnow()
            )
            session.add(failure)
            session.commit()
            failure_id = failure.id
            
            # Log as build or test failure event
            event_name = "TESTS_FAILED" if "test" in failure_type.lower() else "BUILD_FAILED"
            self.log_event(episode_id, event_name, {
                "failure_id": failure_id,
                "failure_type": failure_type,
                "file_path": file_path,
                "symbol": symbol,
                "message": message
            })
        except Exception as e:
            session.rollback()
            print(f"[ExecutionMemory] Error logging failure: {e}")
        finally:
            session.close()
        return failure_id

    def log_repair(self, episode_id: str, failure_id: Optional[int] = None, repair_type: str = "repair_symbol", 
                   target: Optional[str] = None, patch: Optional[str] = None, description: Optional[str] = None, 
                   success: bool = False):
        """
        Logs a repair attempt patch and status.
        """
        session = SessionLocal()
        try:
            repair = RepairRecord(
                episode_id=episode_id,
                failure_record_id=failure_id,
                repair_type=repair_type,
                target=target,
                patch=patch,
                description=description,
                success=1.0 if success else 0.0,
                created_at=datetime.utcnow()
            )
            session.add(repair)
            session.commit()
            
            # Log as event
            self.log_event(episode_id, "REPAIR_APPLIED", {
                "repair_id": repair.id,
                "failure_id": failure_id,
                "repair_type": repair_type,
                "target": target,
                "success": success,
                "description": description
            })
        except Exception as e:
            session.rollback()
            print(f"[ExecutionMemory] Error logging repair: {e}")
        finally:
            session.close()

    def log_plan(self, episode_id: str, goal_type: str, plan_dict: Dict[str, Any]):
        """
        Logs a compiled plan.
        """
        session = SessionLocal()
        try:
            plan_record = PlanRecord(
                episode_id=episode_id,
                goal_type=goal_type,
                plan_json=json.dumps(plan_dict),
                success_rate=1.0,
                created_at=datetime.utcnow()
            )
            session.add(plan_record)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ExecutionMemory] Error logging plan: {e}")
        finally:
            session.close()

    def complete_episode(self, episode_id: str, outcome: str):
        """
        Concludes the episode and updates the overall outcome status (SUCCESS / FAILED).
        Also triggers learning/strategy record updates.
        """
        session = SessionLocal()
        try:
            episode = session.query(ExecutionEpisode).filter(ExecutionEpisode.episode_id == episode_id).first()
            if episode:
                episode.outcome = outcome
                episode.updated_at = datetime.utcnow()
                session.commit()
                
                # Update StrategyRecord if a plan exists for this episode
                plan = session.query(PlanRecord).filter(PlanRecord.episode_id == episode_id).first()
                if plan:
                    self.update_strategy(plan.goal_type, outcome == "SUCCESS", session=session)
            
            session.close()
            self.log_event(episode_id, "TASK_COMPLETED", {"outcome": outcome})
        except Exception as e:
            session.rollback()
            session.close()
            print(f"[ExecutionMemory] Error completing episode: {e}")

    def update_strategy(self, goal_type: str, success: bool, session=None):
        """
        Aggregates and updates learning strategies for specific goal types.
        """
        db_sess = session or SessionLocal()
        close_session = session is None
        try:
            strategy = db_sess.query(StrategyRecord).filter(StrategyRecord.goal_type == goal_type).first()
            if not strategy:
                strategy = StrategyRecord(
                    goal_type=goal_type,
                    strategy_json=json.dumps({
                        "recommended_verifications": ["build_check", "unit_tests"],
                        "common_repairs": []
                    }),
                    success_count=0,
                    failure_count=0,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db_sess.add(strategy)
            
            if success:
                strategy.success_count += 1
            else:
                strategy.failure_count += 1
                
            strategy.updated_at = datetime.utcnow()
            db_sess.commit()
        except Exception as e:
            db_sess.rollback()
            print(f"[ExecutionMemory] Error updating strategy for {goal_type}: {e}")
        finally:
            if close_session:
                db_sess.close()
