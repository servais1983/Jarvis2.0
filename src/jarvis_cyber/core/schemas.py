from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(default="default", min_length=1)
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    model: str
    used_remote_model: bool
    knowledge_hits: list["KnowledgeSearchResult"] = Field(default_factory=list)
    citations: list["KnowledgeCitation"] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    environment: str
    database_ready: bool
    voice_enabled: bool
    embeddings_enabled: bool
    auth_required: bool
    scheduler_enabled: bool
    scheduler_running: bool


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class UserLoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: str | None = Field(default=None, min_length=6, max_length=10)


UserRole = Literal["admin", "analyst"]


class UserResponse(BaseModel):
    user_id: str
    email: str
    role: UserRole
    mfa_required: bool = False
    created_at: str


class AuthTokenResponse(BaseModel):
    token: str
    user: UserResponse


class AuthSessionResponse(BaseModel):
    session_id: str
    created_at: str
    expires_at: str
    last_used_at: str | None = None
    current: bool = False


class LogoutResponse(BaseModel):
    revoked: bool


class AuditEventResponse(BaseModel):
    event_id: str
    actor_user_id: str | None = None
    event_type: str
    target_user_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class UserRoleUpdateRequest(BaseModel):
    role: UserRole


class UserCapabilitiesResponse(BaseModel):
    role: UserRole
    permissions: list[str]


ResponseStyle = Literal["concise", "balanced", "detailed"]
ApprovalPreference = Literal["ask_before_sensitive_actions", "always_ask", "suggest_only"]


class UserProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=160)
    organization: str | None = Field(default=None, max_length=160)
    environment_summary: str | None = Field(default=None, max_length=2000)
    focus_areas: str | None = Field(default=None, max_length=1200)
    preferred_language: str | None = Field(default=None, max_length=32)
    response_style: ResponseStyle | None = None
    approval_preference: ApprovalPreference | None = None
    timezone: str | None = Field(default=None, max_length=80)


class UserProfileResponse(BaseModel):
    user_id: str
    display_name: str | None = None
    job_title: str | None = None
    organization: str | None = None
    environment_summary: str | None = None
    focus_areas: str | None = None
    preferred_language: str = "fr"
    response_style: ResponseStyle = "balanced"
    approval_preference: ApprovalPreference = "ask_before_sensitive_actions"
    timezone: str | None = None
    created_at: str
    updated_at: str


class MFAFactorResponse(BaseModel):
    factor_id: str
    factor_type: Literal["totp", "webauthn"]
    label: str | None = None
    enrolled_at: str
    verified_at: str | None = None
    last_used_at: str | None = None
    disabled_at: str | None = None


class MFAStatusResponse(BaseModel):
    required: bool
    enabled: bool
    factors: list[MFAFactorResponse] = Field(default_factory=list)
    unused_recovery_codes: int = 0


class MFAEnrollRequest(BaseModel):
    label: str | None = Field(default=None, max_length=120)


class MFAEnrollmentResponse(BaseModel):
    factor_id: str
    secret: str
    otpauth_uri: str


class MFAVerifyRequest(BaseModel):
    factor_id: str
    code: str = Field(min_length=6, max_length=10)


class MFARecoveryCodesResponse(BaseModel):
    codes: list[str]


class MFAFactorDisableRequest(BaseModel):
    code: str | None = Field(default=None, min_length=6, max_length=32)
    allow_disable_last_factor: bool = False


class KnowledgeDocumentCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source: str | None = None


class KnowledgeDocument(BaseModel):
    document_id: str
    title: str
    source: str | None = None
    content: str
    content_hash: str
    created_at: str


class KnowledgeChunk(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    source: str | None = None
    content: str
    created_at: str
    embedding: list[float] | None = None


class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    source: str | None = None
    snippet: str
    score: float
    search_mode: Literal["lexical", "semantic"] = "lexical"


class KnowledgeCitation(BaseModel):
    citation_id: str
    document_id: str
    chunk_id: str
    title: str
    source: str | None = None
    snippet: str


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=3, ge=1, le=10)


class KnowledgeDeleteResponse(BaseModel):
    document_id: str
    deleted: bool


class TaskProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1200)
    output_format: str = Field(min_length=1, max_length=4000)
    review_checklist: str | None = Field(default=None, max_length=2400)


class TaskProfile(BaseModel):
    profile_id: str
    name: str
    description: str | None = None
    output_format: str
    review_checklist: str | None = None
    created_at: str
    updated_at: str


class PlaybookCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1800)
    trigger_phrases: str | None = Field(default=None, max_length=1200)
    steps: str = Field(min_length=1, max_length=6000)
    expected_outcome: str | None = Field(default=None, max_length=2000)
    task_profile_id: str | None = None


class Playbook(BaseModel):
    playbook_id: str
    title: str
    purpose: str
    trigger_phrases: str | None = None
    steps: str
    expected_outcome: str | None = None
    task_profile_id: str | None = None
    created_at: str
    updated_at: str


class PlaybookSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=3, ge=1, le=10)


class PlaybookSearchResult(BaseModel):
    playbook: Playbook
    task_profile: TaskProfile | None = None
    score: float


class InvestigationProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1200)
    trigger_phrases: str | None = Field(default=None, max_length=1200)
    default_goal: str | None = Field(default=None, max_length=1200)
    recommended_checks: str | None = Field(default=None, max_length=4000)
    include_recent_github: bool = False
    drive_query: str | None = Field(default=None, max_length=1200)
    jira_jql: str | None = Field(default=None, max_length=1200)


class InvestigationProfileTemplate(BaseModel):
    template_id: str
    name: str
    description: str | None = None
    trigger_phrases: str | None = None
    default_goal: str | None = None
    recommended_checks: str | None = None
    include_recent_github: bool = False
    drive_query: str | None = None
    jira_jql: str | None = None


class InvestigationProfile(BaseModel):
    profile_id: str
    name: str
    description: str | None = None
    trigger_phrases: str | None = None
    default_goal: str | None = None
    recommended_checks: str | None = None
    include_recent_github: bool = False
    drive_query: str | None = None
    jira_jql: str | None = None
    created_at: str
    updated_at: str


class InvestigationProfileSearchResult(BaseModel):
    profile: InvestigationProfile
    score: float


InvestigationCaseStatus = Literal["open", "monitoring", "closed"]
InvestigationChecklistStatus = Literal["todo", "done", "blocked"]
InvestigationHypothesisStatus = Literal["open", "supported", "rejected"]


class InvestigationCaseCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    raw_alert: str = Field(min_length=1)
    environment_context: str | None = None
    goal: str | None = Field(default=None, max_length=1200)
    investigation_profile_id: str | None = None


class InvestigationCaseStatusUpdateRequest(BaseModel):
    status: InvestigationCaseStatus


class InvestigationChecklistItemUpdateRequest(BaseModel):
    status: InvestigationChecklistStatus
    notes: str | None = Field(default=None, max_length=2000)


class InvestigationCaseNoteCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class InvestigationCaseEventCreateRequest(BaseModel):
    occurred_at: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)


class InvestigationCaseEvidenceCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    source: str | None = Field(default=None, max_length=400)


class InvestigationCaseHypothesisCreateRequest(BaseModel):
    statement: str = Field(min_length=1, max_length=1200)
    rationale: str | None = Field(default=None, max_length=4000)


class InvestigationCaseHypothesisUpdateRequest(BaseModel):
    status: InvestigationHypothesisStatus
    rationale: str | None = Field(default=None, max_length=4000)


class InvestigationCaseEntraEnrichmentRequest(BaseModel):
    user_principal_name: str = Field(min_length=3, max_length=320)
    sign_in_limit: int = Field(default=5, ge=1, le=20)


class InvestigationCaseDefenderEnrichmentRequest(BaseModel):
    query: str | None = Field(default=None, max_length=320)
    incident_limit: int = Field(default=5, ge=1, le=20)
    alert_limit: int = Field(default=10, ge=1, le=20)
    severity: str | None = Field(default=None, max_length=80)
    service_source: str | None = Field(default=None, max_length=120)


class InvestigationCaseSentinelEnrichmentRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    timespan: str | None = Field(default=None, max_length=80)
    evidence_title: str | None = Field(default=None, max_length=240)
    max_events: int = Field(default=5, ge=0, le=20)


InvestigationEnrichmentPriority = Literal["high", "medium", "low"]
InvestigationEnrichmentCategory = Literal[
    "account_compromise",
    "phishing",
    "malware",
    "data_exfiltration",
    "critical_vulnerability",
    "general",
]


class InvestigationEnrichmentRecommendation(BaseModel):
    recommendation_id: str
    title: str
    connector: str
    action: str
    priority: InvestigationEnrichmentPriority
    rationale: str
    required_inputs: list[str] = Field(default_factory=list)
    suggested_parameters: dict[str, str] = Field(default_factory=dict)
    sentinel_template_id: str | None = None
    already_enriched: bool = False


class InvestigationEnrichmentPlanResponse(BaseModel):
    case_id: str
    inferred_category: InvestigationEnrichmentCategory
    confidence: float
    recommendations: list[InvestigationEnrichmentRecommendation] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


IncidentViewSectionStatus = Literal["ok", "attention", "missing"]


class InvestigationIncidentViewSection(BaseModel):
    title: str
    status: IncidentViewSectionStatus
    items: list[str] = Field(default_factory=list)


class InvestigationIncidentViewResponse(BaseModel):
    case_id: str
    inferred_category: InvestigationEnrichmentCategory
    confidence: float
    headline: str
    indicators: dict[str, str] = Field(default_factory=dict)
    sections: list[InvestigationIncidentViewSection] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    analyst_note: str


SOCPriority = Literal["critical", "high", "medium", "low"]


class InvestigationSOCQueueItem(BaseModel):
    case_id: str
    title: str
    status: InvestigationCaseStatus
    inferred_category: InvestigationEnrichmentCategory
    priority: SOCPriority
    score: int
    reasons: list[str] = Field(default_factory=list)
    next_action: str
    evidence_count: int
    event_count: int
    open_hypotheses: int
    todo_checks: int
    updated_at: str


class InvestigationSOCQueueResponse(BaseModel):
    total_cases: int
    active_cases: int
    items: list[InvestigationSOCQueueItem] = Field(default_factory=list)


class SOCShiftBriefResponse(BaseModel):
    generated_at: str
    headline: str
    total_active_cases: int
    critical_cases: int
    high_cases: int
    focus_now: list[InvestigationSOCQueueItem] = Field(default_factory=list)
    blocked_or_under_evidenced: list[InvestigationSOCQueueItem] = Field(default_factory=list)
    ready_for_report: list[InvestigationSOCQueueItem] = Field(default_factory=list)
    can_wait: list[InvestigationSOCQueueItem] = Field(default_factory=list)
    operator_guidance: list[str] = Field(default_factory=list)


SOCSLAState = Literal["breached", "warning", "ok"]


class SOCSLAItem(BaseModel):
    case_id: str
    title: str
    priority: SOCPriority
    inferred_category: InvestigationEnrichmentCategory
    state: SOCSLAState
    age_minutes: int
    idle_minutes: int
    breaches: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str


class SOCSLAResponse(BaseModel):
    generated_at: str
    total_active_cases: int
    breached_count: int
    warning_count: int
    items: list[SOCSLAItem] = Field(default_factory=list)


InvestigationClosureState = Literal["ready", "needs_work", "already_closed"]
InvestigationClosureCheckStatus = Literal["passed", "missing", "attention"]


class InvestigationClosureCheck(BaseModel):
    title: str
    status: InvestigationClosureCheckStatus
    detail: str


class InvestigationClosureAssistantResponse(BaseModel):
    case_id: str
    state: InvestigationClosureState
    readiness_score: int
    headline: str
    checks: list[InvestigationClosureCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    recommended_next_action: str
    report_recommended: bool = False
    close_recommended: bool = False


class InvestigationCase(BaseModel):
    case_id: str
    title: str
    raw_alert: str
    environment_context: str | None = None
    goal: str | None = None
    investigation_profile_id: str | None = None
    status: InvestigationCaseStatus
    created_at: str
    updated_at: str


class InvestigationChecklistItem(BaseModel):
    item_id: str
    title: str
    status: InvestigationChecklistStatus
    notes: str | None = None
    position: int
    created_at: str
    updated_at: str


class InvestigationCaseNote(BaseModel):
    note_id: str
    body: str
    created_at: str


class InvestigationCaseEvent(BaseModel):
    event_id: str
    occurred_at: str
    title: str
    description: str | None = None
    created_at: str


class InvestigationCaseEvidence(BaseModel):
    evidence_id: str
    title: str
    description: str | None = None
    source: str | None = None
    created_at: str


class InvestigationCaseHypothesis(BaseModel):
    hypothesis_id: str
    statement: str
    status: InvestigationHypothesisStatus
    rationale: str | None = None
    created_at: str
    updated_at: str


class InvestigationCaseSummary(BaseModel):
    total_checks: int
    done_checks: int
    blocked_checks: int
    todo_checks: int
    completion_ratio: float
    next_open_checks: list[str] = Field(default_factory=list)
    latest_note: str | None = None
    open_hypotheses: int = 0
    supported_hypotheses: int = 0
    rejected_hypotheses: int = 0


class InvestigationCaseDetail(BaseModel):
    case: InvestigationCase
    checklist_items: list[InvestigationChecklistItem] = Field(default_factory=list)
    notes: list[InvestigationCaseNote] = Field(default_factory=list)
    events: list[InvestigationCaseEvent] = Field(default_factory=list)
    evidence: list[InvestigationCaseEvidence] = Field(default_factory=list)
    hypotheses: list[InvestigationCaseHypothesis] = Field(default_factory=list)
    summary: InvestigationCaseSummary


class InvestigationCaseEntraEnrichmentResult(BaseModel):
    sign_ins_reviewed: int
    matched_risky_users: int
    added_events: int
    added_evidence: int


class InvestigationCaseEntraEnrichmentResponse(BaseModel):
    detail: InvestigationCaseDetail
    result: InvestigationCaseEntraEnrichmentResult


class InvestigationCaseDefenderEnrichmentResult(BaseModel):
    incidents_reviewed: int
    alerts_reviewed: int
    added_events: int
    added_evidence: int


class InvestigationCaseDefenderEnrichmentResponse(BaseModel):
    detail: InvestigationCaseDetail
    result: InvestigationCaseDefenderEnrichmentResult


class InvestigationCaseSentinelEnrichmentResult(BaseModel):
    rows_reviewed: int
    added_events: int
    added_evidence: int
    columns: list[str] = Field(default_factory=list)


class InvestigationCaseSentinelEnrichmentResponse(BaseModel):
    detail: InvestigationCaseDetail
    result: InvestigationCaseSentinelEnrichmentResult


class InvestigationProgressSummaryResult(BaseModel):
    executive_summary: str
    established_facts: list[str]
    supported_hypotheses: list[str]
    rejected_hypotheses: list[str]
    next_actions: list[str]
    uncertainties: list[str]
    confidence: Confidence


class InvestigationProgressSummaryResponse(BaseModel):
    result: InvestigationProgressSummaryResult
    model: str
    used_remote_model: bool


class InvestigationCaseReportResponse(BaseModel):
    result: IncidentReportResult
    model: str
    used_remote_model: bool


class DeleteResponse(BaseModel):
    deleted: bool


class WatchlistCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    keywords: str = Field(min_length=1, max_length=1000)
    exact_match: bool = False
    kev_only: bool = False


class Watchlist(BaseModel):
    watchlist_id: str
    title: str
    keywords: str
    exact_match: bool = False
    kev_only: bool = False
    created_at: str
    updated_at: str


class DailyBriefRequest(BaseModel):
    days: int = Field(default=1, ge=1, le=30)
    per_watchlist_limit: int = Field(default=5, ge=1, le=20)


class DailyBriefWatchlistResult(BaseModel):
    watchlist: Watchlist
    records: list["CVERecord"] = Field(default_factory=list)


class DailyBriefResponse(BaseModel):
    generated_at: str
    window_start: str
    window_end: str
    items: list[DailyBriefWatchlistResult] = Field(default_factory=list)


class GitHubRepository(BaseModel):
    repository_id: int
    full_name: str
    private: bool
    html_url: str
    description: str | None = None
    updated_at: str | None = None


class DriveFile(BaseModel):
    file_id: str
    name: str
    mime_type: str | None = None
    modified_time: str | None = None
    web_view_link: str | None = None


class JiraIssue(BaseModel):
    issue_id: str
    key: str
    summary: str
    status: str | None = None
    updated_at: str | None = None
    web_url: str | None = None


class EntraSignIn(BaseModel):
    sign_in_id: str
    created_at: str | None = None
    user_display_name: str | None = None
    user_principal_name: str | None = None
    app_display_name: str | None = None
    ip_address: str | None = None
    client_app_used: str | None = None
    conditional_access_status: str | None = None
    failure_reason: str | None = None
    city: str | None = None
    country_or_region: str | None = None
    risk_level_aggregated: str | None = None


class EntraRiskyUser(BaseModel):
    user_id: str
    user_principal_name: str | None = None
    user_display_name: str | None = None
    risk_level: str | None = None
    risk_state: str | None = None
    risk_detail: str | None = None
    risk_last_updated_at: str | None = None


class EntraAuthenticationMethod(BaseModel):
    method_id: str
    method_type: str


class DefenderIncident(BaseModel):
    incident_id: str
    display_name: str | None = None
    status: str | None = None
    severity: str | None = None
    classification: str | None = None
    determination: str | None = None
    created_at: str | None = None
    last_update_at: str | None = None
    incident_web_url: str | None = None
    assigned_to: str | None = None


class DefenderAlert(BaseModel):
    alert_id: str
    provider_alert_id: str | None = None
    incident_id: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    severity: str | None = None
    classification: str | None = None
    determination: str | None = None
    service_source: str | None = None
    detection_source: str | None = None
    created_at: str | None = None
    first_activity_at: str | None = None
    last_activity_at: str | None = None
    evidence_count: int = 0


class SentinelQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    timespan: str | None = Field(default=None, max_length=80)


class SentinelQueryTemplate(BaseModel):
    template_id: str
    name: str
    category: str
    description: str
    parameters: list[str] = Field(default_factory=list)
    query_template: str
    default_timespan: str | None = None


class SentinelQueryTemplateRenderRequest(BaseModel):
    parameters: dict[str, str] = Field(default_factory=dict)
    timespan: str | None = Field(default=None, max_length=80)


class SentinelQueryTemplateRenderResponse(BaseModel):
    template_id: str
    query: str
    timespan: str | None = None


class SentinelQueryResult(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, object | None]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False


class ConnectorDigestResponse(BaseModel):
    generated_at: str
    repositories: list[GitHubRepository] = Field(default_factory=list)
    drive_files: list[DriveFile] = Field(default_factory=list)
    jira_issues: list[JiraIssue] = Field(default_factory=list)


AutomationType = Literal["daily_brief", "connector_digest"]
AutomationScheduleKind = Literal["daily"]
AutomationRunStatus = Literal["succeeded", "failed", "approval_required"]


class DailyBriefAutomationPayload(BaseModel):
    days: int = Field(default=1, ge=1, le=30)
    per_watchlist_limit: int = Field(default=5, ge=1, le=20)


class ConnectorDigestAutomationPayload(BaseModel):
    include_github: bool = True
    include_google_drive: bool = True
    include_jira: bool = True
    github_limit: int = Field(default=5, ge=1, le=20)
    drive_query: str | None = Field(default=None, max_length=1200)
    drive_limit: int = Field(default=5, ge=1, le=20)
    jira_jql: str | None = Field(default=None, max_length=1200)
    jira_limit: int = Field(default=5, ge=1, le=20)


class AutomationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    automation_type: AutomationType = "daily_brief"
    schedule_kind: AutomationScheduleKind = "daily"
    schedule_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str = Field(min_length=1, max_length=80)
    payload: DailyBriefAutomationPayload | ConnectorDigestAutomationPayload = Field(
        default_factory=DailyBriefAutomationPayload
    )
    enabled: bool = True
    requires_approval: bool = False


class Automation(BaseModel):
    automation_id: str
    name: str
    automation_type: AutomationType
    schedule_kind: AutomationScheduleKind
    schedule_time: str
    timezone: str
    payload: DailyBriefAutomationPayload | ConnectorDigestAutomationPayload
    enabled: bool
    requires_approval: bool
    next_run_at: str | None = None
    last_run_at: str | None = None
    created_at: str
    updated_at: str


class AutomationRun(BaseModel):
    run_id: str
    automation_id: str
    status: AutomationRunStatus
    started_at: str
    finished_at: str | None = None
    output: DailyBriefResponse | ConnectorDigestResponse | None = None
    error_message: str | None = None


class AutomationRunDueResponse(BaseModel):
    runs: list[AutomationRun] = Field(default_factory=list)


InboxItemType = Literal[
    "automation_succeeded",
    "automation_failed",
    "approval_required",
    "tool_approval_required",
    "tool_approval_executed",
    "tool_approval_rejected",
]


class InboxItem(BaseModel):
    item_id: str
    item_type: InboxItemType
    title: str
    body: str
    related_run_id: str | None = None
    payload: DailyBriefResponse | ConnectorDigestResponse | None = None
    read_at: str | None = None
    created_at: str


class InboxMarkReadResponse(BaseModel):
    item_id: str
    read_at: str


ToolApprovalStatus = Literal["pending", "executed", "rejected", "failed"]


class ToolApprovalRequest(BaseModel):
    approval_id: str
    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    reason: str
    source: str
    status: ToolApprovalStatus
    result: dict[str, object] | None = None
    error_message: str | None = None
    created_at: str
    resolved_at: str | None = None


ConnectorProvider = Literal[
    "github",
    "google_drive",
    "jira",
    "entra_id",
    "microsoft_defender",
    "microsoft_sentinel",
]
ConnectorCredentialSource = Literal["environment", "vault", "missing"]


class ConnectorStatus(BaseModel):
    provider: ConnectorProvider
    configured: bool
    mode: Literal["read_only_env_or_vault"] = "read_only_env_or_vault"
    credential_source: ConnectorCredentialSource


class ConnectorSecretWriteRequest(BaseModel):
    value: str = Field(min_length=1)


class ConnectorSecretStatus(BaseModel):
    provider: ConnectorProvider
    stored_in_vault: bool


class GitHubPullRequest(BaseModel):
    pull_request_id: int
    number: int
    title: str
    state: str
    html_url: str
    updated_at: str | None = None


class VoiceChatResponse(BaseModel):
    transcript: str
    session_id: str
    answer: str
    model: str
    used_remote_model: bool
    citations: list["KnowledgeCitation"] = Field(default_factory=list)


class RealtimeSidebandRequest(BaseModel):
    call_id: str = Field(min_length=1)


class RealtimeSidebandResponse(BaseModel):
    call_id: str
    connected: bool


class CVESummaryRequest(BaseModel):
    cve_id: str | None = None
    source_text: str = Field(min_length=1)


class CVEEnrichmentRequest(BaseModel):
    cve_id: str = Field(pattern=r"^CVE-\d{4}-\d{4,}$")


class AlertTriageRequest(BaseModel):
    title: str = Field(min_length=1)
    raw_alert: str = Field(min_length=1)
    environment_context: str | None = None


class IncidentReportRequest(BaseModel):
    incident_summary: str = Field(min_length=1)
    timeline: str | None = None
    impact: str | None = None
    actions_taken: str | None = None
    open_questions: str | None = None


class AlertInvestigationRequest(BaseModel):
    title: str = Field(min_length=1)
    raw_alert: str = Field(min_length=1)
    environment_context: str | None = None
    goal: str | None = Field(default=None, max_length=1200)
    investigation_profile_id: str | None = None
    include_recent_github: bool = False
    drive_query: str | None = Field(default=None, max_length=1200)
    jira_jql: str | None = Field(default=None, max_length=1200)


Severity = Literal["low", "medium", "high", "critical", "unknown"]
Confidence = Literal["low", "medium", "high"]


class CVESummaryResult(BaseModel):
    cve_id: str | None
    executive_summary: str
    affected_products: list[str]
    technical_impact: str
    urgency: Severity
    exploitation_signals: list[str]
    recommended_actions: list[str]
    uncertainties: list[str]
    confidence: Confidence


class AlertTriageResult(BaseModel):
    classification: Literal["benign", "suspicious", "malicious", "unknown"]
    observed_facts: list[str]
    hypotheses: list[str]
    priority_checks: list[str]
    severity: Severity
    decision: Literal["close", "monitor", "escalate", "investigate"]
    rationale: str
    confidence: Confidence


class WatchlistSuggestion(BaseModel):
    title: str
    keywords: str
    exact_match: bool = False
    kev_only: bool = False
    rationale: str


class AlertInvestigationResult(BaseModel):
    executive_summary: str
    triage: AlertTriageResult
    context_findings: list[str]
    matched_playbooks: list[str]
    priority_checks: list[str]
    recommended_actions: list[str]
    suggested_watchlist: WatchlistSuggestion | None = None
    uncertainties: list[str]
    confidence: Confidence


class IncidentReportResult(BaseModel):
    executive_summary: str
    timeline: list[str]
    scope_and_impact: str
    probable_cause: str
    actions_taken: list[str]
    recommended_actions: list[str]
    open_questions: list[str]
    confidence: Confidence


class CVESummaryResponse(BaseModel):
    result: CVESummaryResult
    model: str
    used_remote_model: bool


class CVEReference(BaseModel):
    url: str
    source: str | None = None
    tags: list[str] = Field(default_factory=list)


class CVERecord(BaseModel):
    cve_id: str
    status: str | None = None
    published: str | None = None
    last_modified: str | None = None
    description: str
    cvss_score: float | None = None
    cvss_severity: str | None = None
    known_exploited: bool = False
    required_action: str | None = None
    affected_criteria: list[str] = Field(default_factory=list)
    references: list[CVEReference] = Field(default_factory=list)


class CVEEnrichmentResponse(BaseModel):
    source: Literal["nvd"]
    record: CVERecord
    analysis: CVESummaryResult
    model: str
    used_remote_model: bool


class AlertTriageResponse(BaseModel):
    result: AlertTriageResult
    model: str
    used_remote_model: bool


class AlertInvestigationResponse(BaseModel):
    result: AlertInvestigationResult
    model: str
    used_remote_model: bool
    knowledge_hits: list[KnowledgeSearchResult] = Field(default_factory=list)
    playbook_hits: list[PlaybookSearchResult] = Field(default_factory=list)
    applied_profile: InvestigationProfile | None = None
    external_context: ConnectorDigestResponse | None = None
    pending_approval_id: str | None = None


class IncidentReportResponse(BaseModel):
    result: IncidentReportResult
    model: str
    used_remote_model: bool
