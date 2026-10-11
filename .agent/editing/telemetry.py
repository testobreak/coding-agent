import logging
from typing import Optional

logger = logging.getLogger(__name__)

class EditTelemetry:
    def __init__(self):
        self.success_count = 0
        self.failure_count = 0
        self.rollback_count = 0

    def record_success(self, plan, duration_ms: float, patch_lines: int):
        self.success_count += 1
        logger.info(f"[Telemetry] Success: {plan.symbol} ({duration_ms:.1f}ms, {patch_lines} lines)")

    def record_failure(self, plan, duration_ms: float, error: str):
        self.failure_count += 1
        logger.info(f"[Telemetry] Failure: {plan.symbol} ({duration_ms:.1f}ms, error={error})")

    def record_rollback(self, plan, duration_ms: float, reason: str):
        self.rollback_count += 1
        logger.info(f"[Telemetry] Rollback: {plan.symbol} ({duration_ms:.1f}ms, reason={reason})")

_telemetry_singleton = EditTelemetry()

def get_telemetry() -> EditTelemetry:
    return _telemetry_singleton
