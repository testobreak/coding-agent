# core/plan_type.py
from enum import Enum

class PlanType(str, Enum):
    DIRECT = "direct"
    LINEAR = "linear"
    DAG = "dag"
