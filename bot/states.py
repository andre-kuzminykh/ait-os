"""State machine enums for process and session lifecycle."""

from enum import Enum


class ProcessStatus(str, Enum):
    """Process-level status."""
    CREATED = "created"
    INTERVIEW_IN_PROGRESS = "interview_in_progress"
    CLARIFICATION_IN_PROGRESS = "clarification_in_progress"
    ASIS_READY = "asis_ready"
    ASIS_PUBLISHED = "asis_published"
    AUTOMATION_SELECTION_IN_PROGRESS = "automation_selection_in_progress"
    READY_FOR_TOBE = "ready_for_tobe"


class SessionStatus(str, Enum):
    """Interview session status."""
    STARTED = "started"
    AWAITING_INITIAL_RESPONSE = "awaiting_initial_response"
    PROCESSING_INPUT = "processing_input"
    AWAITING_FOLLOWUP_ANSWER = "awaiting_followup_answer"
    PAUSED = "paused"
    COMPLETED = "completed"


class GapStatus(str, Enum):
    """Gap detection status."""
    PENDING = "pending"
    ANSWERED = "answered"
    SKIPPED = "skipped"


class OpportunityStatus(str, Enum):
    """Automation opportunity status."""
    PROPOSED = "proposed"
    SELECTED = "selected"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class GapFieldType(str, Enum):
    """Types of fields that can be missing in a process model."""
    ROLES = "roles"
    SYSTEMS = "systems"
    ARTIFACTS = "artifacts"
    METRICS = "metrics"
    TRIGGER = "trigger"
    OUTPUT = "output"
    SLA_TIMING = "sla_timing"
    HANDOFF = "handoff"
    DECISION_POINT = "decision_point"
    GOAL = "goal"
    INPUT = "input"
    PAIN_POINTS = "pain_points"


class OpportunityType(str, Enum):
    """Type of automation opportunity."""
    AI = "ai"
    RULE_BASED = "rule_based"
    INTEGRATION = "integration"
    ANALYTICS = "analytics"
    MONITORING = "monitoring"
