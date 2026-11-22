"""The one definition of every fixed value set stored in a status-like column (H13).

Each enum below is the single source for its column: the entity builds the database CHECK constraint from it
(:func:`values_check`), the Alembic revision that adds the constraints renders it from the entity metadata, and the code that writes
the value uses the enum member instead of a string. The sets are taken from what the code writes and recognises (not from the
design document, which lists a few values no code produces). To add a value, add it here and write a revision that replaces the
constraint of that column; the schema drift test and the constraint tests fail until both exist.

Columns left open on purpose (their values come from catalogs, Azure resource types or free input, so a fixed list would be wrong):
service_type, document_category, sli_kind, data_source_kind, notification_type, decision_outcome, event_type, event_source,
evidence_category, evidence_source_kind, environment_name, record_system, tool_type, tool_name, tool_source, turn_finish and the AI usage model fields.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint


class AlertSourceTool(StrEnum):
    AZURE_MONITOR = "azure_monitor"
    ELASTIC = "elastic"
    GENERIC = "generic"
    KEIGAN_SLO = "keigan_slo"  # the internal source that carries Keigan's own SLO burn alerts


class AlertSourceStatus(StrEnum):
    WAITING_FOR_FIRST_ALERT = "waiting_for_first_alert"
    RECEIVING = "receiving"
    AUTHENTICATION_FAILURES = "authentication_failures"
    PAUSED = "paused"


class AlertEventProcessingStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED_PAUSED = "ignored_paused"


class AlertStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"


class AlertFinalDisposition(StrEnum):
    SETTLING = "settling"
    RECORDED_ONLY = "recorded_only"


class AlertPipelineStage(StrEnum):
    NORMALISE = "normalise"
    DEDUPLICATE = "deduplicate"
    SUPPRESS = "suppress"
    GROUP = "group"
    PRIORITISE = "prioritise"
    DECIDE = "decide"
    NOTIFY = "notify"
    LIFECYCLE = "lifecycle"
    SETTLE = "settle"


class AlertGroupStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    QUEUED = "queued"
    RESOLVED = "resolved"


class AlertGroupFeedbackVerdict(StrEnum):
    USEFUL = "useful"
    NOISE = "noise"


class AlertGroupingReason(StrEnum):
    """Why an alert group's alerts belong together. Derived when a group is read, never stored (no column, no CHECK); the screens translate each code."""

    SAME_SERVICE = "same_service"
    DEPENDENCY = "dependency"
    SAME_RULE = "same_rule"
    ATTACHED_TO_INCIDENT = "attached_to_incident"
    SINGLE_ALERT = "single_alert"
    NOT_RECORDED = "not_recorded"


class NoisePolicyMode(StrEnum):
    OBSERVE = "observe"
    ACTIVE = "active"


class AssignmentGroupVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class IncidentSource(StrEnum):
    SERVICENOW = "servicenow"
    ALERT = "alert"
    MANUAL = "manual"


class IncidentStatus(StrEnum):
    NEW = "new"
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Priority(StrEnum):
    """Incident and notification priority, most severe first."""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class InvestigationTrigger(StrEnum):
    INCIDENT = "incident"
    ALERT_GROUP = "alert_group"
    MANUAL = "manual"
    RERUN = "rerun"


class InvestigationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_EVIDENCE_ONLY = "completed_evidence_only"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LlmCallOutcome(StrEnum):
    """What the AI gateway writes to llm_usage_record.outcome_status. The column is open (no CHECK), so this only names the two words it writes."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class InvestigationStage(StrEnum):
    TRIAGE = "triage"
    CONTEXT = "context"
    EVIDENCE = "evidence"
    HYPOTHESES = "hypotheses"
    SYNTHESIS = "synthesis"
    COMMUNICATIONS = "communications"
    COMPLETED = "completed"


class InvestigationFeedbackVerdict(StrEnum):
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"


class AnalysisPerspective(StrEnum):
    APPLICATION = "application"
    DEPENDENCIES = "dependencies"
    INFRASTRUCTURE = "infrastructure"


class HypothesisState(StrEnum):
    """The end state of one perspective's hypothesis, after Keigan's rules (spec 27, 4.4)."""

    SUPPORTED = "supported"
    RULED_OUT = "ruled_out"
    INCONCLUSIVE = "inconclusive"


class HypothesisStateGuard(StrEnum):
    """The rule that lowered a hypothesis's proposed state; the rules only ever lower a state."""

    SUPPORT_NOT_IN_EVIDENCE = "support_not_in_evidence"
    CONFIDENCE_BELOW_SUPPORTED_MINIMUM = "confidence_below_supported_minimum"
    RULE_OUT_NOT_IN_EVIDENCE = "rule_out_not_in_evidence"
    CONFIDENCE_ABOVE_RULED_OUT_MAXIMUM = "confidence_above_ruled_out_maximum"


class InvestigationOutcome(StrEnum):
    """How far an investigation got: it found a cause, could not settle between explanations, or saw nothing that changed in the data it can read."""

    CAUSE_IDENTIFIED = "cause_identified"
    INCONCLUSIVE = "inconclusive"
    CAUSE_NOT_VISIBLE = "cause_not_visible"


class InvestigationOutcomeGuard(StrEnum):
    """The rule that lowered an investigation's proposed outcome."""

    NOTHING_CHANGED_IN_CHECKED_SOURCES = "nothing_changed_in_checked_sources"
    LEADING_HYPOTHESIS_NOT_SUPPORTED = "leading_hypothesis_not_supported"
    SYNTHESIS_UNAVAILABLE = "synthesis_unavailable"


class EvidenceCheckOutcome(StrEnum):
    """What a check of one source found: something (signal), a healthy or empty result (no signal), or it could not be read (rows stored before spec 27 only)."""

    SIGNAL = "signal"
    NO_SIGNAL = "no_signal"
    NOT_CHECKED = "not_checked"


class BaselineComparison(StrEnum):
    """Whether an evidence item was compared with the healthy window before the investigation window."""

    COMPARED = "compared"
    NO_BASELINE_FOR_SOURCE = "no_baseline_for_source"


class CoverageGapKind(StrEnum):
    """One thing an investigation meant to check and could not, or did not because of a limit."""

    SOURCE_NOT_READABLE = "source_not_readable"
    CHANGES_NOT_READABLE = "changes_not_readable"
    SERVICE_WITHOUT_TELEMETRY = "service_without_telemetry"
    SERVICES_BEYOND_LIMIT = "services_beyond_limit"
    CHECKS_BEYOND_LIMIT = "checks_beyond_limit"
    PLANNED_QUERY_REJECTED = "planned_query_rejected"
    PLANNED_QUERY_FAILED = "planned_query_failed"
    RESULTS_LEFT_OUT = "results_left_out"
    PERSPECTIVE_NOT_ANALYSED = "perspective_not_analysed"


class CoverageGapReason(StrEnum):
    """Why a check was not made: a code Keigan assigned, never text copied from an integration."""

    ACCESS_REFUSED = "access_refused"
    THROTTLED = "throttled"
    SOURCE_NOT_FOUND = "source_not_found"
    SOURCE_ERROR = "source_error"
    TIMED_OUT = "timed_out"
    NOT_APPROVED = "not_approved"
    QUERY_REJECTED = "query_rejected"
    READER_NOT_AVAILABLE = "reader_not_available"
    AI_UNAVAILABLE = "ai_unavailable"
    AI_OUTPUT_INVALID = "ai_output_invalid"
    UNKNOWN = "unknown"


class InvestigationTraceStepKind(StrEnum):
    """One row of an investigation's decision trace (spec 28)."""

    INPUTS = "inputs"
    AI_CALL = "ai_call"
    EVIDENCE = "evidence"
    DECISION = "decision"
    OUTCOME = "outcome"


class InvestigationTraceStepStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvestigationDecisionKind(StrEnum):
    """What a deterministic decision step decided."""

    SERVICES_SELECTED = "services_selected"
    PRIORITY_SET = "priority_set"
    PLANNER_REQUESTED = "planner_requested"
    EVIDENCE_ONLY_MODE = "evidence_only_mode"
    SYNTHESIS_FALLBACK = "synthesis_fallback"


class InvestigationAiCallFailure(StrEnum):
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    AI_UNAVAILABLE = "ai_unavailable"
    AI_RATE_LIMITED = "ai_rate_limited"
    AI_OUTPUT_INVALID = "ai_output_invalid"
    FAILED = "failed"


class ActionItemStatus(StrEnum):
    """A follow-up task after an incident (spec 29). ``proposed`` is an AI suggestion nobody has accepted: it is not tracked, reminded or counted."""

    PROPOSED = "proposed"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    WONT_DO = "wont_do"


class ActionItemType(StrEnum):
    PREVENT = "prevent"
    DETECT = "detect"
    MITIGATE = "mitigate"


class ActionItemPriority(StrEnum):
    """Words, not P-numbers (incident priorities are already P1 to P4). ``top`` means drop everything: the error-budget policy (spec 30) requires one."""

    TOP = "top"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ActionItemSource(StrEnum):
    """Where an item came from. Later specs (30, 31, 32) each add a value with their own revision."""

    POSTMORTEM = "postmortem"
    MANUAL = "manual"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CommunicationStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"


class PostmortemStatus(StrEnum):
    GENERATING = "generating"
    DRAFT = "draft"
    FINAL = "final"
    FAILED = "failed"


class ConversationScope(StrEnum):
    INVESTIGATION = "investigation"
    KEIGAN_AI_CHAT = "keigan_ai_chat"
    TEAMS_INCIDENT_CHAT = "teams_incident_chat"


class MessageAuthorRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TEAMS_PARTICIPANT = "teams_participant"


class ChatAnswerRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatAnswerStopReason(StrEnum):
    ANSWERED = "answered"
    TOOL_LIMIT_REACHED = "tool_limit_reached"
    TOKEN_BUDGET_REACHED = "token_budget_reached"
    CANCELLED_BY_USER = "cancelled_by_user"
    FAILED = "failed"


class ChatRunStepKind(StrEnum):
    MODEL_TURN = "model_turn"
    TOOL_CALL = "tool_call"


class ChatRunStepStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUSED = "refused"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ToolCallingMode(StrEnum):
    """How one answer run offered its tools to the model: the model's own tool calling, a JSON protocol in the prompt, or the offline planner."""

    NATIVE = "native"
    PROMPTED_JSON = "prompted_json"
    SCRIPTED_MOCK = "scripted_mock"


class ApplicationLifecycleStatus(StrEnum):
    REQUESTED = "requested"
    DRAFT = "draft"
    ONBOARDING = "onboarding"
    LIVE = "live"
    PAUSED = "paused"


class CriticalityTier(StrEnum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class ComponentType(StrEnum):
    AZURE_RESOURCE_GROUP = "azure_resource_group"
    HARDWARE = "hardware"
    MAINFRAME = "mainframe"
    SAAS_PLATFORM = "saas_platform"


class AccessVerificationStatus(StrEnum):
    NOT_CHECKED = "not_checked"
    CHECKING = "checking"
    VERIFIED = "verified"
    MISSING_ROLES = "missing_roles"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class LogToolConnectionStatus(StrEnum):
    NOT_TESTED = "not_tested"
    CONNECTED = "connected"
    FAILED = "failed"
    READER_NOT_AVAILABLE = "reader_not_available"


class ReadTestStatus(StrEnum):
    NOT_TESTED = "not_tested"
    PASSED = "passed"
    FAILED = "failed"


class IntegrationStatus(StrEnum):
    NOT_SET_UP = "not_set_up"
    CONFIGURED = "configured"
    SAVED_READER_IN_DEVELOPMENT = "saved_reader_in_development"


class DocumentDigestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class TopologyGenerationStatus(StrEnum):
    BUILDING = "building"
    READY = "ready"


class TopologyReviewStatus(StrEnum):
    AWAITING_REVIEW = "awaiting_review"
    REVIEWED = "reviewed"
    NEEDS_CORRECTION = "needs_correction"


class TopologyReviewVerdict(StrEnum):
    LOOKS_RIGHT = "looks_right"
    NEEDS_CORRECTION = "needs_correction"
    COMMENT = "comment"


class StakeholderRecipientType(StrEnum):
    PERSON = "person"
    TEAMS_CHANNEL = "teams_channel"
    DISTRIBUTION_LIST = "distribution_list"


class StakeholderRole(StrEnum):
    SRE = "sre"
    DEVELOPER = "developer"
    MANAGER = "manager"
    EXECUTIVE = "executive"
    BUSINESS_OWNER = "business_owner"
    VENDOR_CONTACT = "vendor_contact"
    LEAD = "lead"
    INFRA = "infra"
    DEVOPS = "devops"
    TESTER = "tester"


class TeamMemberStatus(StrEnum):
    """Where a team member stands, worked out from facts on the stakeholder row (never stored, so it cannot disagree with them)."""

    LISTED = "listed"  # only a notification recipient: nobody was invited
    INVITED = "invited"  # an invitation was sent and the person has not signed in yet
    ACTIVE = "active"  # the person has signed in to Keigan
    INACTIVE = "inactive"  # switched off: receives nothing


class DeliveryChannel(StrEnum):
    EMAIL = "email"
    TEAMS_INCIDENT_CHAT = "teams_incident_chat"
    TEAMS_CHANNEL = "teams_channel"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SIMULATED = "simulated"
    SKIPPED = "skipped"


class TeamsChatStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


class SignalStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    CONVERTED_TO_INCIDENT = "converted_to_incident"
    EXPIRED = "expired"


class SignalSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class BurnAlertSeverity(StrEnum):
    PAGE = "page"
    TICKET = "ticket"


class IntelligenceReportType(StrEnum):
    WEEKLY_DIGEST = "weekly_digest"
    PROACTIVE_ALERT = "proactive_alert"


class SloHealthStatus(StrEnum):
    """Where an SLO stands. Worked out from its measurements every time the dashboard is built and never stored, so no column and no CHECK constraint carry it."""

    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    NO_DATA = "no_data"


def sql_in_list(values: type[StrEnum]) -> str:
    """``'a', 'b'`` for a SQL ``IN (...)``. The members are plain identifiers, so quoting needs no escaping."""
    return ", ".join(f"'{member.value}'" for member in values)


def values_check(column_name: str, values: type[StrEnum]) -> CheckConstraint:
    """CHECK constraint named ``ck_<table>_<column>_values`` (the table comes from the project's naming convention). NULL passes, as in SQL."""
    return CheckConstraint(f"{column_name} IN ({sql_in_list(values)})", name=f"{column_name}_values")
