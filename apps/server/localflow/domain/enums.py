from enum import Enum

class DraftStatus(str, Enum):
    drafting = "DRAFTING"
    approved_locked = "APPROVED_LOCKED"
    archived = "ARCHIVED"

class ExecutionStatus(str, Enum):
    pending = "PENDING"
    running = "RUNNING"
    succeeded = "SUCCEEDED"
    failed = "FAILED"
    canceled = "CANCELED"

class RiskLevel(str, Enum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
