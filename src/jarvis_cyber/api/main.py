import logging
from contextlib import asynccontextmanager
from csv import DictWriter
from io import StringIO
from pathlib import Path
from time import perf_counter

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from jarvis_cyber.auth import (
    InvalidCredentialsError,
    LoginRateLimitedError,
    WeakPasswordError,
    auth_service,
    current_token,
    current_user,
    require_permissions,
)
from jarvis_cyber.config import settings
from jarvis_cyber.knowledge.embeddings import embedding_service
from jarvis_cyber.observability import configure_logging
from jarvis_cyber.core.schemas import (
    AlertTriageRequest,
    AlertTriageResponse,
    AlertInvestigationRequest,
    AlertInvestigationResponse,
    Automation,
    AutomationCreateRequest,
    AutomationRun,
    AutomationRunDueResponse,
    AuditEventResponse,
    AuthSessionResponse,
    AuthTokenResponse,
    DeleteResponse,
    MFAStatusResponse,
    MFAEnrollRequest,
    MFAEnrollmentResponse,
    MFAFactorDisableRequest,
    MFARecoveryCodesResponse,
    MFAVerifyRequest,
    ChatRequest,
    ChatResponse,
    CVEEnrichmentRequest,
    CVEEnrichmentResponse,
    CVESummaryRequest,
    CVESummaryResponse,
    DailyBriefRequest,
    DailyBriefResponse,
    DefenderAlert,
    DefenderIncident,
    DriveFile,
    EntraAuthenticationMethod,
    EntraRiskyUser,
    EntraSignIn,
    GitHubPullRequest,
    GitHubRepository,
    HealthResponse,
    IncidentReportRequest,
    IncidentReportResponse,
    InvestigationCase,
    InvestigationCaseCreateRequest,
    InvestigationCaseDefenderEnrichmentRequest,
    InvestigationCaseDefenderEnrichmentResponse,
    InvestigationCaseDetail,
    InvestigationCaseEntraEnrichmentRequest,
    InvestigationCaseEntraEnrichmentResponse,
    InvestigationCaseEventCreateRequest,
    InvestigationCaseEvidenceCreateRequest,
    InvestigationCaseHypothesisCreateRequest,
    InvestigationCaseHypothesisUpdateRequest,
    InvestigationCaseNoteCreateRequest,
    InvestigationCaseStatusUpdateRequest,
    InvestigationChecklistItemUpdateRequest,
    InvestigationCaseReportResponse,
    InvestigationCaseSentinelEnrichmentRequest,
    InvestigationCaseSentinelEnrichmentResponse,
    InvestigationClosureAssistantResponse,
    InvestigationEnrichmentPlanResponse,
    InvestigationIncidentViewResponse,
    InvestigationProgressSummaryResponse,
    InvestigationSOCQueueResponse,
    InvestigationProfile,
    InvestigationProfileCreateRequest,
    InvestigationProfileTemplate,
    InboxItem,
    InboxMarkReadResponse,
    KnowledgeDocument,
    KnowledgeDocumentCreateRequest,
    KnowledgeDeleteResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    JiraIssue,
    LogoutResponse,
    Playbook,
    PlaybookCreateRequest,
    PlaybookSearchRequest,
    PlaybookSearchResult,
    RealtimeSidebandRequest,
    RealtimeSidebandResponse,
    SentinelQueryRequest,
    SentinelQueryResult,
    SentinelQueryTemplate,
    SentinelQueryTemplateRenderRequest,
    SentinelQueryTemplateRenderResponse,
    SOCSLAResponse,
    SOCShiftBriefResponse,
    TaskProfile,
    TaskProfileCreateRequest,
    ToolApprovalRequest,
    UserCapabilitiesResponse,
    UserCreateRequest,
    UserLoginRequest,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserRoleUpdateRequest,
    UserResponse,
    VoiceChatResponse,
    Watchlist,
    WatchlistCreateRequest,
    ConnectorStatus,
    ConnectorSecretStatus,
    ConnectorSecretWriteRequest,
)
from jarvis_cyber.services.assistant import assistant_service
from jarvis_cyber.services.automations import automation_service
from jarvis_cyber.services.briefings import briefing_service
from jarvis_cyber.services.scheduler import automation_scheduler
from jarvis_cyber.services.realtime import (
    RealtimeServiceUnavailableError,
    realtime_service,
)
from jarvis_cyber.services.realtime_sideband import realtime_sideband_manager
from jarvis_cyber.services.voice import VoiceServiceUnavailableError, voice_service
from jarvis_cyber.services.realtime_tools import realtime_tool_service
from jarvis_cyber.services.tool_catalog import tool_catalog_service
from jarvis_cyber.services.workflows import cyber_workflow_service
from jarvis_cyber.services.mfa import (
    InvalidMFACodeError,
    LastMFAFactorError,
    MFAEncryptionUnavailableError,
    MFAFactorNotFoundError,
    RecoveryCodesUnavailableError,
    mfa_service,
)
from jarvis_cyber.knowledge.extractors import (
    EmptyKnowledgeFileError,
    UnsupportedKnowledgeFileError,
    knowledge_file_extractor,
)
from jarvis_cyber.knowledge.store import knowledge_store
from jarvis_cyber.investigation_profiles.store import investigation_profile_store
from jarvis_cyber.investigation_profiles.templates import list_investigation_profile_templates
from jarvis_cyber.investigations.store import investigation_case_store
from jarvis_cyber.playbooks.store import UnknownTaskProfileError, playbook_store
from jarvis_cyber.profile.store import profile_store
from jarvis_cyber.inbox.store import inbox_store
from jarvis_cyber.storage.database import database
from jarvis_cyber.watchlists.store import watchlist_store
from jarvis_cyber.automations.store import automation_store
from jarvis_cyber.approvals.store import tool_approval_store
from jarvis_cyber.integrations.github import github_connector
from jarvis_cyber.integrations.google_drive import google_drive_connector
from jarvis_cyber.integrations.jira import jira_connector
from jarvis_cyber.integrations.entra_id import entra_id_connector
from jarvis_cyber.integrations.microsoft_defender import microsoft_defender_connector
from jarvis_cyber.integrations.microsoft_sentinel import microsoft_sentinel_connector
from jarvis_cyber.services.connector_secrets import connector_secret_service
from jarvis_cyber.services.investigation_enrichment import investigation_enrichment_service
from jarvis_cyber.services.secret_vault import SecretVaultUnavailableError
from jarvis_cyber.sentinel_queries.templates import (
    get_sentinel_query_template,
    list_sentinel_query_templates,
    render_sentinel_query_template,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await automation_scheduler.start()
    try:
        yield
    finally:
        await automation_scheduler.stop()


app = FastAPI(
    title="Jarvis Cyber",
    version="0.1.0",
    description="Personal cybersecurity copilot API.",
    lifespan=lifespan,
)
configure_logging()
logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started_at = perf_counter()
    response = await call_next(request)
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "request_completed method=%s path=%s status=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.middleware("http")
async def apply_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data:; "
        "media-src 'self' blob:; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' https://api.openai.com wss://api.openai.com"
    )
    if settings.hsts_enabled:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.env,
        database_ready=database.ready(),
        voice_enabled=voice_service.enabled,
        embeddings_enabled=embedding_service.enabled,
        auth_required=settings.auth_required,
        scheduler_enabled=settings.scheduler_enabled,
        scheduler_running=automation_scheduler.running,
    )


@app.post("/auth/register", response_model=AuthTokenResponse)
def register(payload: UserCreateRequest, request: Request) -> AuthTokenResponse:
    try:
        return auth_service.register(
            payload.email,
            payload.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except WeakPasswordError as error:
        raise HTTPException(status_code=400, detail="Password does not meet policy.") from error
    except Exception as error:
        raise HTTPException(status_code=400, detail="Unable to register user.") from error


@app.post("/auth/login", response_model=AuthTokenResponse)
def login(payload: UserLoginRequest, request: Request) -> AuthTokenResponse:
    try:
        return auth_service.login(
            payload.email,
            payload.password,
            payload.mfa_code,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=401, detail="Invalid credentials.") from error
    except LoginRateLimitedError as error:
        raise HTTPException(status_code=429, detail="Too many login attempts.") from error


@app.get("/auth/me", response_model=UserResponse)
def me(user: UserResponse = Depends(current_user)) -> UserResponse:
    return user


@app.get("/auth/capabilities", response_model=UserCapabilitiesResponse)
def capabilities(user: UserResponse = Depends(current_user)) -> UserCapabilitiesResponse:
    return auth_service.capabilities_for(user)


@app.get("/auth/mfa/status", response_model=MFAStatusResponse)
def mfa_status(user: UserResponse = Depends(current_user)) -> MFAStatusResponse:
    return auth_service.mfa_status(user.user_id)


@app.post("/auth/mfa/totp/enroll", response_model=MFAEnrollmentResponse)
def enroll_totp(
    payload: MFAEnrollRequest,
    user: UserResponse = Depends(current_user),
) -> MFAEnrollmentResponse:
    try:
        return mfa_service.enroll_totp(user.user_id, user.email, payload.label)
    except MFAEncryptionUnavailableError as error:
        raise HTTPException(status_code=503, detail="MFA encryption key unavailable.") from error


@app.post("/auth/mfa/totp/verify", response_model=MFAStatusResponse)
def verify_totp(
    payload: MFAVerifyRequest,
    user: UserResponse = Depends(current_user),
) -> MFAStatusResponse:
    try:
        return mfa_service.verify_enrollment(user.user_id, payload.factor_id, payload.code)
    except MFAFactorNotFoundError as error:
        raise HTTPException(status_code=404, detail="MFA factor not found.") from error
    except InvalidMFACodeError as error:
        raise HTTPException(status_code=400, detail="Invalid MFA code.") from error
    except MFAEncryptionUnavailableError as error:
        raise HTTPException(status_code=503, detail="MFA encryption key unavailable.") from error


@app.post("/auth/mfa/recovery-codes", response_model=MFARecoveryCodesResponse)
def generate_recovery_codes(
    user: UserResponse = Depends(current_user),
) -> MFARecoveryCodesResponse:
    try:
        return mfa_service.generate_recovery_codes(user.user_id)
    except RecoveryCodesUnavailableError as error:
        raise HTTPException(
            status_code=400,
            detail="A verified MFA factor is required before generating recovery codes.",
        ) from error


@app.post("/auth/mfa/factors/{factor_id}/disable", response_model=MFAStatusResponse)
def disable_mfa_factor(
    factor_id: str,
    payload: MFAFactorDisableRequest,
    user: UserResponse = Depends(current_user),
) -> MFAStatusResponse:
    try:
        return mfa_service.disable_factor(
            user.user_id,
            factor_id,
            code=payload.code,
            allow_disable_last_factor=payload.allow_disable_last_factor,
        )
    except MFAFactorNotFoundError as error:
        raise HTTPException(status_code=404, detail="MFA factor not found.") from error
    except InvalidMFACodeError as error:
        raise HTTPException(status_code=400, detail="Invalid MFA code.") from error
    except LastMFAFactorError as error:
        raise HTTPException(status_code=400, detail="Cannot disable last MFA factor.") from error


@app.get("/profile/me", response_model=UserProfileResponse)
def get_profile(user: UserResponse = Depends(current_user)) -> UserProfileResponse:
    return profile_store.get(user.user_id)


@app.put("/profile/me", response_model=UserProfileResponse)
def update_profile(
    payload: UserProfileUpdateRequest,
    user: UserResponse = Depends(current_user),
) -> UserProfileResponse:
    return profile_store.update(user.user_id, payload)


@app.post("/auth/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    user: UserResponse = Depends(current_user),
    token: str | None = Depends(current_token),
) -> LogoutResponse:
    if token is None:
        return LogoutResponse(revoked=False)
    return auth_service.revoke_token(
        token,
        actor_user_id=user.user_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@app.get("/auth/sessions", response_model=list[AuthSessionResponse])
def list_sessions(
    user: UserResponse = Depends(current_user),
    token: str | None = Depends(current_token),
) -> list[AuthSessionResponse]:
    if token is None:
        return []
    return auth_service.list_sessions(user.user_id, token)


@app.delete("/auth/sessions/{session_id}", response_model=LogoutResponse)
def revoke_session(
    session_id: str,
    request: Request,
    user: UserResponse = Depends(current_user),
) -> LogoutResponse:
    return LogoutResponse(
        revoked=auth_service.revoke_session(
            user.user_id,
            session_id,
            actor_user_id=user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


@app.get("/admin/users", response_model=list[UserResponse])
def list_users(_user: UserResponse = Depends(require_permissions("admin.users.read"))) -> list[UserResponse]:
    return auth_service.list_users()


@app.patch("/admin/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: str,
    payload: UserRoleUpdateRequest,
    request: Request,
    user: UserResponse = Depends(require_permissions("admin.users.write")),
) -> UserResponse:
    updated = auth_service.update_role(
        user_id,
        payload.role,
        actor_user_id=user.user_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return updated


@app.get("/admin/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(
    limit: int = 50,
    event_type: str | None = None,
    actor_user_id: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    _user: UserResponse = Depends(require_permissions("admin.audit.read")),
) -> list[AuditEventResponse]:
    return auth_service.list_audit_events(
        limit=min(max(limit, 1), 100),
        event_type=event_type,
        actor_user_id=actor_user_id,
        created_from=created_from,
        created_to=created_to,
    )


@app.get("/admin/audit-events/export.csv")
def export_audit_events(
    limit: int = 100,
    event_type: str | None = None,
    actor_user_id: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    _user: UserResponse = Depends(require_permissions("admin.audit.export")),
) -> Response:
    events = auth_service.list_audit_events(
        limit=min(max(limit, 1), 1000),
        event_type=event_type,
        actor_user_id=actor_user_id,
        created_from=created_from,
        created_to=created_to,
    )
    buffer = StringIO()
    writer = DictWriter(
        buffer,
        fieldnames=[
            "event_id",
            "actor_user_id",
            "event_type",
            "target_user_id",
            "ip_address",
            "user_agent",
            "created_at",
            "metadata",
        ],
    )
    writer.writeheader()
    for event in events:
        writer.writerow(event.model_dump())
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="jarvis-audit-events.csv"'},
    )


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, user: UserResponse = Depends(require_permissions("chat.use"))) -> ChatResponse:
    answer, model, used_remote_model, knowledge_hits, citations = assistant_service.respond(
        user_id=user.user_id,
        session_id=payload.session_id,
        message=payload.message,
        role=user.role,
    )
    return ChatResponse(
        session_id=payload.session_id,
        answer=answer,
        model=model,
        used_remote_model=used_remote_model,
        knowledge_hits=knowledge_hits,
        citations=citations,
    )


@app.post("/workflows/cve-summary", response_model=CVESummaryResponse)
def summarize_cve(
    payload: CVESummaryRequest,
    _user: UserResponse = Depends(require_permissions("workflow.cve_summary")),
) -> CVESummaryResponse:
    result, model, used_remote_model = cyber_workflow_service.summarize_cve(payload)
    return CVESummaryResponse(result=result, model=model, used_remote_model=used_remote_model)


@app.post("/workflows/cve-enrichment", response_model=CVEEnrichmentResponse)
def enrich_cve(
    payload: CVEEnrichmentRequest,
    _user: UserResponse = Depends(require_permissions("workflow.cve_enrichment")),
) -> CVEEnrichmentResponse:
    record, analysis, model, used_remote_model = cyber_workflow_service.enrich_cve(payload)
    return CVEEnrichmentResponse(
        source="nvd",
        record=record,
        analysis=analysis,
        model=model,
        used_remote_model=used_remote_model,
    )


@app.post("/workflows/alert-triage", response_model=AlertTriageResponse)
def triage_alert(
    payload: AlertTriageRequest,
    _user: UserResponse = Depends(require_permissions("workflow.alert_triage")),
) -> AlertTriageResponse:
    result, model, used_remote_model = cyber_workflow_service.triage_alert(payload)
    return AlertTriageResponse(result=result, model=model, used_remote_model=used_remote_model)


@app.post("/workflows/alert-investigation", response_model=AlertInvestigationResponse)
def investigate_alert(
    payload: AlertInvestigationRequest,
    user: UserResponse = Depends(require_permissions("workflow.alert_investigation")),
) -> AlertInvestigationResponse:
    result, model, used_remote_model, knowledge_hits, playbook_hits, external_context, applied_profile = (
        cyber_workflow_service.investigate_alert(user.user_id, payload)
    )
    pending_approval_id = None
    if result.suggested_watchlist is not None:
        proposal = tool_catalog_service.execute(
            "create_watchlist",
            result.suggested_watchlist.model_dump(exclude={"rationale"}),
            user.user_id,
            role=user.role,
            source="workflow.alert_investigation",
        )
        pending_approval_id = proposal.get("approval_id")
    return AlertInvestigationResponse(
        result=result,
        model=model,
        used_remote_model=used_remote_model,
        knowledge_hits=knowledge_hits,
        playbook_hits=playbook_hits,
        applied_profile=applied_profile,
        external_context=external_context,
        pending_approval_id=pending_approval_id,
    )


@app.post("/workflows/incident-report", response_model=IncidentReportResponse)
def draft_incident_report(
    payload: IncidentReportRequest,
    _user: UserResponse = Depends(require_permissions("workflow.incident_report")),
) -> IncidentReportResponse:
    result, model, used_remote_model = cyber_workflow_service.draft_incident_report(payload)
    return IncidentReportResponse(result=result, model=model, used_remote_model=used_remote_model)


@app.post("/knowledge/documents", response_model=KnowledgeDocument)
def create_knowledge_document(
    payload: KnowledgeDocumentCreateRequest,
    user: UserResponse = Depends(require_permissions("knowledge.write")),
) -> KnowledgeDocument:
    return knowledge_store.add_document(
        user_id=user.user_id,
        title=payload.title,
        content=payload.content,
        source=payload.source,
    )


@app.get("/knowledge/documents", response_model=list[KnowledgeDocument])
def list_knowledge_documents(user: UserResponse = Depends(require_permissions("knowledge.read"))) -> list[KnowledgeDocument]:
    return knowledge_store.list_documents(user.user_id)


@app.delete("/knowledge/documents/{document_id}", response_model=KnowledgeDeleteResponse)
def delete_knowledge_document(
    document_id: str,
    user: UserResponse = Depends(require_permissions("knowledge.delete")),
) -> KnowledgeDeleteResponse:
    deleted = knowledge_store.delete_document(user.user_id, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return KnowledgeDeleteResponse(document_id=document_id, deleted=True)


@app.post("/knowledge/search", response_model=list[KnowledgeSearchResult])
def search_knowledge(
    payload: KnowledgeSearchRequest,
    user: UserResponse = Depends(require_permissions("knowledge.read")),
) -> list[KnowledgeSearchResult]:
    return knowledge_store.search(user.user_id, payload.query, limit=payload.limit)


@app.post("/knowledge/files", response_model=KnowledgeDocument)
async def upload_knowledge_file(
    file: UploadFile = File(...),
    user: UserResponse = Depends(require_permissions("knowledge.write")),
) -> KnowledgeDocument:
    filename = file.filename or "document.txt"
    try:
        content = knowledge_file_extractor.extract(filename, await file.read())
    except UnsupportedKnowledgeFileError as error:
        raise HTTPException(status_code=400, detail="Unsupported file type.") from error
    except EmptyKnowledgeFileError as error:
        raise HTTPException(status_code=400, detail="No extractable text found.") from error

    return knowledge_store.add_document(
        user_id=user.user_id,
        title=Path(filename).stem,
        content=content,
        source=filename,
    )


@app.post("/knowledge/files/batch", response_model=list[KnowledgeDocument])
async def upload_knowledge_files(
    files: list[UploadFile] = File(...),
    user: UserResponse = Depends(require_permissions("knowledge.write")),
) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for file in files:
        filename = file.filename or "document.txt"
        try:
            content = knowledge_file_extractor.extract(filename, await file.read())
        except UnsupportedKnowledgeFileError as error:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}") from error
        except EmptyKnowledgeFileError as error:
            raise HTTPException(status_code=400, detail=f"No extractable text found: {filename}") from error

        documents.append(
            knowledge_store.add_document(
                user_id=user.user_id,
                title=Path(filename).stem,
                content=content,
                source=filename,
            )
        )
    return documents


@app.post("/task-profiles", response_model=TaskProfile)
def create_task_profile(
    payload: TaskProfileCreateRequest,
    user: UserResponse = Depends(require_permissions("task_profiles.write")),
) -> TaskProfile:
    return playbook_store.add_task_profile(user.user_id, payload)


@app.get("/task-profiles", response_model=list[TaskProfile])
def list_task_profiles(
    user: UserResponse = Depends(require_permissions("task_profiles.read")),
) -> list[TaskProfile]:
    return playbook_store.list_task_profiles(user.user_id)


@app.delete("/task-profiles/{profile_id}", response_model=DeleteResponse)
def delete_task_profile(
    profile_id: str,
    user: UserResponse = Depends(require_permissions("task_profiles.delete")),
) -> DeleteResponse:
    deleted = playbook_store.delete_task_profile(user.user_id, profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task profile not found.")
    return DeleteResponse(deleted=True)


@app.post("/playbooks", response_model=Playbook)
def create_playbook(
    payload: PlaybookCreateRequest,
    user: UserResponse = Depends(require_permissions("playbooks.write")),
) -> Playbook:
    try:
        return playbook_store.add_playbook(user.user_id, payload)
    except UnknownTaskProfileError as error:
        raise HTTPException(status_code=400, detail="Unknown task profile.") from error


@app.get("/playbooks", response_model=list[Playbook])
def list_playbooks(
    user: UserResponse = Depends(require_permissions("playbooks.read")),
) -> list[Playbook]:
    return playbook_store.list_playbooks(user.user_id)


@app.delete("/playbooks/{playbook_id}", response_model=DeleteResponse)
def delete_playbook(
    playbook_id: str,
    user: UserResponse = Depends(require_permissions("playbooks.delete")),
) -> DeleteResponse:
    deleted = playbook_store.delete_playbook(user.user_id, playbook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Playbook not found.")
    return DeleteResponse(deleted=True)


@app.post("/playbooks/search", response_model=list[PlaybookSearchResult])
def search_playbooks(
    payload: PlaybookSearchRequest,
    user: UserResponse = Depends(require_permissions("playbooks.read")),
) -> list[PlaybookSearchResult]:
    return playbook_store.search_playbooks(user.user_id, payload.query, payload.limit)


@app.post("/investigation-profiles", response_model=InvestigationProfile)
def create_investigation_profile(
    payload: InvestigationProfileCreateRequest,
    user: UserResponse = Depends(require_permissions("investigation_profiles.write")),
) -> InvestigationProfile:
    return investigation_profile_store.add(user.user_id, payload)


@app.get("/investigation-profile-templates", response_model=list[InvestigationProfileTemplate])
def list_investigation_profile_templates_endpoint(
    user: UserResponse = Depends(require_permissions("investigation_profiles.read")),
) -> list[InvestigationProfileTemplate]:
    return list_investigation_profile_templates()


@app.get("/investigation-profiles", response_model=list[InvestigationProfile])
def list_investigation_profiles(
    user: UserResponse = Depends(require_permissions("investigation_profiles.read")),
) -> list[InvestigationProfile]:
    return investigation_profile_store.list(user.user_id)


@app.delete("/investigation-profiles/{profile_id}", response_model=DeleteResponse)
def delete_investigation_profile(
    profile_id: str,
    user: UserResponse = Depends(require_permissions("investigation_profiles.delete")),
) -> DeleteResponse:
    deleted = investigation_profile_store.delete(user.user_id, profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Investigation profile not found.")
    return DeleteResponse(deleted=True)


@app.post("/investigation-cases", response_model=InvestigationCaseDetail)
def create_investigation_case(
    payload: InvestigationCaseCreateRequest,
    user: UserResponse = Depends(require_permissions("investigations.write")),
) -> InvestigationCaseDetail:
    return investigation_case_store.create(user.user_id, payload)


@app.get("/investigation-cases", response_model=list[InvestigationCase])
def list_investigation_cases(
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> list[InvestigationCase]:
    return investigation_case_store.list(user.user_id)


@app.get("/investigation-cases/queue", response_model=InvestigationSOCQueueResponse)
def list_investigation_soc_queue(
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> InvestigationSOCQueueResponse:
    return investigation_enrichment_service.soc_queue(user.user_id)


@app.get("/investigation-cases/shift-brief", response_model=SOCShiftBriefResponse)
def get_soc_shift_brief(
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> SOCShiftBriefResponse:
    return investigation_enrichment_service.shift_brief(user.user_id)


@app.get("/investigation-cases/sla", response_model=SOCSLAResponse)
def get_soc_sla_watch(
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> SOCSLAResponse:
    return investigation_enrichment_service.sla_watch(user.user_id)


@app.get("/investigation-cases/{case_id}", response_model=InvestigationCaseDetail)
def get_investigation_case(
    case_id: str,
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> InvestigationCaseDetail:
    detail = investigation_case_store.get_detail(user.user_id, case_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return detail


@app.post(
    "/investigation-cases/{case_id}/summary",
    response_model=InvestigationProgressSummaryResponse,
)
def summarize_investigation_case(
    case_id: str,
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> InvestigationProgressSummaryResponse:
    detail = investigation_case_store.get_detail(user.user_id, case_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    result, model, used_remote_model = cyber_workflow_service.summarize_investigation_progress(detail)
    return InvestigationProgressSummaryResponse(
        result=result,
        model=model,
        used_remote_model=used_remote_model,
    )


@app.post(
    "/investigation-cases/{case_id}/report",
    response_model=InvestigationCaseReportResponse,
)
def draft_investigation_case_report(
    case_id: str,
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> InvestigationCaseReportResponse:
    detail = investigation_case_store.get_detail(user.user_id, case_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    result, model, used_remote_model = cyber_workflow_service.draft_incident_report_from_case(detail)
    return InvestigationCaseReportResponse(
        result=result,
        model=model,
        used_remote_model=used_remote_model,
    )


@app.post(
    "/investigation-cases/{case_id}/enrichment-plan",
    response_model=InvestigationEnrichmentPlanResponse,
)
def recommend_investigation_case_enrichment_plan(
    case_id: str,
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> InvestigationEnrichmentPlanResponse:
    result = investigation_enrichment_service.recommend_plan(user.user_id, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return result


@app.post(
    "/investigation-cases/{case_id}/incident-view",
    response_model=InvestigationIncidentViewResponse,
)
def render_investigation_case_incident_view(
    case_id: str,
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> InvestigationIncidentViewResponse:
    result = investigation_enrichment_service.incident_view(user.user_id, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return result


@app.post(
    "/investigation-cases/{case_id}/closure-assistant",
    response_model=InvestigationClosureAssistantResponse,
)
def assist_investigation_case_closure(
    case_id: str,
    user: UserResponse = Depends(require_permissions("investigations.read")),
) -> InvestigationClosureAssistantResponse:
    result = investigation_enrichment_service.closure_assistant(user.user_id, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return result


@app.post(
    "/investigation-cases/{case_id}/enrich/entra-id",
    response_model=InvestigationCaseEntraEnrichmentResponse,
)
def enrich_investigation_case_from_entra_id(
    case_id: str,
    payload: InvestigationCaseEntraEnrichmentRequest,
    user: UserResponse = Depends(require_permissions("investigations.write", "connectors.read")),
) -> InvestigationCaseEntraEnrichmentResponse:
    if not entra_id_connector.configured:
        raise HTTPException(status_code=503, detail="Entra ID connector is not configured.")
    result = investigation_enrichment_service.enrich_from_entra_id(user.user_id, case_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return result


@app.post(
    "/investigation-cases/{case_id}/enrich/defender",
    response_model=InvestigationCaseDefenderEnrichmentResponse,
)
def enrich_investigation_case_from_defender(
    case_id: str,
    payload: InvestigationCaseDefenderEnrichmentRequest,
    user: UserResponse = Depends(require_permissions("investigations.write", "connectors.read")),
) -> InvestigationCaseDefenderEnrichmentResponse:
    if not microsoft_defender_connector.configured:
        raise HTTPException(status_code=503, detail="Microsoft Defender connector is not configured.")
    result = investigation_enrichment_service.enrich_from_defender(user.user_id, case_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return result


@app.post(
    "/investigation-cases/{case_id}/enrich/sentinel",
    response_model=InvestigationCaseSentinelEnrichmentResponse,
)
def enrich_investigation_case_from_sentinel(
    case_id: str,
    payload: InvestigationCaseSentinelEnrichmentRequest,
    user: UserResponse = Depends(require_permissions("investigations.write", "connectors.read")),
) -> InvestigationCaseSentinelEnrichmentResponse:
    if not microsoft_sentinel_connector.configured:
        raise HTTPException(status_code=503, detail="Microsoft Sentinel connector is not configured.")
    result = investigation_enrichment_service.enrich_from_sentinel(user.user_id, case_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return result


@app.patch("/investigation-cases/{case_id}/status", response_model=InvestigationCase)
def update_investigation_case_status(
    case_id: str,
    payload: InvestigationCaseStatusUpdateRequest,
    user: UserResponse = Depends(require_permissions("investigations.write")),
) -> InvestigationCase:
    case = investigation_case_store.update_status(user.user_id, case_id, payload.status)
    if case is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return case


@app.patch(
    "/investigation-cases/{case_id}/checklist/{item_id}",
    response_model=InvestigationCaseDetail,
)
def update_investigation_case_checklist_item(
    case_id: str,
    item_id: str,
    payload: InvestigationChecklistItemUpdateRequest,
    user: UserResponse = Depends(require_permissions("investigations.write")),
) -> InvestigationCaseDetail:
    detail = investigation_case_store.update_checklist_item(user.user_id, case_id, item_id, payload)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation checklist item not found.")
    return detail


@app.post("/investigation-cases/{case_id}/notes", response_model=InvestigationCaseDetail)
def add_investigation_case_note(
    case_id: str,
    payload: InvestigationCaseNoteCreateRequest,
    user: UserResponse = Depends(require_permissions("investigations.write")),
) -> InvestigationCaseDetail:
    detail = investigation_case_store.add_note(user.user_id, case_id, payload.body)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return detail


@app.post("/investigation-cases/{case_id}/events", response_model=InvestigationCaseDetail)
def add_investigation_case_event(
    case_id: str,
    payload: InvestigationCaseEventCreateRequest,
    user: UserResponse = Depends(require_permissions("investigations.write")),
) -> InvestigationCaseDetail:
    detail = investigation_case_store.add_event(user.user_id, case_id, payload)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return detail


@app.post("/investigation-cases/{case_id}/evidence", response_model=InvestigationCaseDetail)
def add_investigation_case_evidence(
    case_id: str,
    payload: InvestigationCaseEvidenceCreateRequest,
    user: UserResponse = Depends(require_permissions("investigations.write")),
) -> InvestigationCaseDetail:
    detail = investigation_case_store.add_evidence(user.user_id, case_id, payload)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return detail


@app.post("/investigation-cases/{case_id}/hypotheses", response_model=InvestigationCaseDetail)
def add_investigation_case_hypothesis(
    case_id: str,
    payload: InvestigationCaseHypothesisCreateRequest,
    user: UserResponse = Depends(require_permissions("investigations.write")),
) -> InvestigationCaseDetail:
    detail = investigation_case_store.add_hypothesis(user.user_id, case_id, payload)
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return detail


@app.patch(
    "/investigation-cases/{case_id}/hypotheses/{hypothesis_id}",
    response_model=InvestigationCaseDetail,
)
def update_investigation_case_hypothesis(
    case_id: str,
    hypothesis_id: str,
    payload: InvestigationCaseHypothesisUpdateRequest,
    user: UserResponse = Depends(require_permissions("investigations.write")),
) -> InvestigationCaseDetail:
    detail = investigation_case_store.update_hypothesis(
        user.user_id,
        case_id,
        hypothesis_id,
        payload,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Investigation hypothesis not found.")
    return detail


@app.delete("/investigation-cases/{case_id}", response_model=DeleteResponse)
def delete_investigation_case(
    case_id: str,
    user: UserResponse = Depends(require_permissions("investigations.delete")),
) -> DeleteResponse:
    deleted = investigation_case_store.delete(user.user_id, case_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Investigation case not found.")
    return DeleteResponse(deleted=True)


@app.post("/watchlists", response_model=Watchlist)
def create_watchlist(
    payload: WatchlistCreateRequest,
    user: UserResponse = Depends(require_permissions("watchlists.write")),
) -> Watchlist:
    return watchlist_store.add(user.user_id, payload)


@app.get("/watchlists", response_model=list[Watchlist])
def list_watchlists(
    user: UserResponse = Depends(require_permissions("watchlists.read")),
) -> list[Watchlist]:
    return watchlist_store.list(user.user_id)


@app.delete("/watchlists/{watchlist_id}", response_model=DeleteResponse)
def delete_watchlist(
    watchlist_id: str,
    user: UserResponse = Depends(require_permissions("watchlists.delete")),
) -> DeleteResponse:
    deleted = watchlist_store.delete(user.user_id, watchlist_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return DeleteResponse(deleted=True)


@app.post("/briefs/daily", response_model=DailyBriefResponse)
def daily_brief(
    payload: DailyBriefRequest,
    user: UserResponse = Depends(require_permissions("briefs.daily")),
) -> DailyBriefResponse:
    return briefing_service.daily_brief(
        user.user_id,
        days=payload.days,
        per_watchlist_limit=payload.per_watchlist_limit,
    )


@app.post("/automations", response_model=Automation)
def create_automation(
    payload: AutomationCreateRequest,
    user: UserResponse = Depends(require_permissions("automations.write")),
) -> Automation:
    return automation_store.add(user.user_id, payload)


@app.get("/automations", response_model=list[Automation])
def list_automations(
    user: UserResponse = Depends(require_permissions("automations.read")),
) -> list[Automation]:
    return automation_store.list(user.user_id)


@app.delete("/automations/{automation_id}", response_model=DeleteResponse)
def delete_automation(
    automation_id: str,
    user: UserResponse = Depends(require_permissions("automations.delete")),
) -> DeleteResponse:
    deleted = automation_store.delete(user.user_id, automation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return DeleteResponse(deleted=True)


@app.post("/automations/{automation_id}/run", response_model=AutomationRun)
def run_automation(
    automation_id: str,
    user: UserResponse = Depends(require_permissions("automations.run")),
) -> AutomationRun:
    automation = automation_store.get(user.user_id, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return automation_service.run(user.user_id, automation)


@app.post("/automations/run-due", response_model=AutomationRunDueResponse)
def run_due_automations(
    user: UserResponse = Depends(require_permissions("automations.run")),
) -> AutomationRunDueResponse:
    return AutomationRunDueResponse(runs=automation_service.run_due(user.user_id))


@app.get("/automations/{automation_id}/runs", response_model=list[AutomationRun])
def list_automation_runs(
    automation_id: str,
    user: UserResponse = Depends(require_permissions("automations.read")),
) -> list[AutomationRun]:
    automation = automation_store.get(user.user_id, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return automation_store.list_runs(user.user_id, automation_id)


@app.get("/inbox", response_model=list[InboxItem])
def list_inbox_items(
    unread_only: bool = False,
    user: UserResponse = Depends(require_permissions("inbox.read")),
) -> list[InboxItem]:
    return inbox_store.list(user.user_id, unread_only=unread_only)


@app.get("/approvals", response_model=list[ToolApprovalRequest])
def list_tool_approvals(
    status: str | None = None,
    user: UserResponse = Depends(require_permissions("approvals.read")),
) -> list[ToolApprovalRequest]:
    if status not in {None, "pending", "executed", "rejected", "failed"}:
        raise HTTPException(status_code=400, detail="Unknown approval status.")
    return tool_approval_store.list(user.user_id, status=status)


@app.post("/approvals/{approval_id}/approve", response_model=ToolApprovalRequest)
def approve_tool_action(
    approval_id: str,
    user: UserResponse = Depends(require_permissions("approvals.write")),
) -> ToolApprovalRequest:
    approval = tool_approval_store.get_pending(user.user_id, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Pending approval not found.")
    try:
        result = tool_catalog_service.execute_approved(
            approval.tool_name,
            approval.arguments,
            user.user_id,
        )
    except Exception as error:
        failed = tool_approval_store.mark_failed(
            user.user_id,
            approval_id,
            error_message=str(error),
        )
        auth_service.record_audit_event(
            event_type="tool.approval_failed",
            actor_user_id=user.user_id,
            metadata={"approval_id": approval_id, "tool_name": approval.tool_name},
        )
        assert failed is not None
        return failed

    executed = tool_approval_store.mark_executed(
        user.user_id,
        approval_id,
        result=result,
    )
    assert executed is not None
    inbox_store.add(
        user.user_id,
        item_type="tool_approval_executed",
        title=f"Action approuvée : {approval.tool_name}",
        body="L'action demandée par Jarvis a été exécutée après ton accord.",
    )
    auth_service.record_audit_event(
        event_type="tool.approval_executed",
        actor_user_id=user.user_id,
        metadata={"approval_id": approval_id, "tool_name": approval.tool_name},
    )
    return executed


@app.post("/approvals/{approval_id}/reject", response_model=ToolApprovalRequest)
def reject_tool_action(
    approval_id: str,
    user: UserResponse = Depends(require_permissions("approvals.write")),
) -> ToolApprovalRequest:
    rejected = tool_approval_store.mark_rejected(user.user_id, approval_id)
    if rejected is None:
        raise HTTPException(status_code=404, detail="Pending approval not found.")
    inbox_store.add(
        user.user_id,
        item_type="tool_approval_rejected",
        title=f"Action refusée : {rejected.tool_name}",
        body="La demande d'action de Jarvis a été refusée.",
    )
    auth_service.record_audit_event(
        event_type="tool.approval_rejected",
        actor_user_id=user.user_id,
        metadata={"approval_id": approval_id, "tool_name": rejected.tool_name},
    )
    return rejected


@app.patch("/inbox/{item_id}/read", response_model=InboxMarkReadResponse)
def mark_inbox_item_read(
    item_id: str,
    user: UserResponse = Depends(require_permissions("inbox.write")),
) -> InboxMarkReadResponse:
    updated = inbox_store.mark_read(user.user_id, item_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Inbox item not found.")
    return updated


@app.get("/connectors/status", response_model=list[ConnectorStatus])
def connector_status(
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[ConnectorStatus]:
    return [
        ConnectorStatus(
            provider="github",
            configured=github_connector.configured,
            credential_source=connector_secret_service.source("github"),
        ),
        ConnectorStatus(
            provider="google_drive",
            configured=google_drive_connector.configured,
            credential_source=connector_secret_service.source("google_drive"),
        ),
        ConnectorStatus(
            provider="jira",
            configured=jira_connector.configured,
            credential_source=connector_secret_service.source("jira"),
        ),
        ConnectorStatus(
            provider="entra_id",
            configured=entra_id_connector.configured,
            credential_source=connector_secret_service.source("entra_id"),
        ),
        ConnectorStatus(
            provider="microsoft_defender",
            configured=microsoft_defender_connector.configured,
            credential_source=connector_secret_service.source("microsoft_defender"),
        ),
        ConnectorStatus(
            provider="microsoft_sentinel",
            configured=microsoft_sentinel_connector.configured,
            credential_source=connector_secret_service.source("microsoft_sentinel"),
        ),
    ]


@app.get("/admin/connector-secrets", response_model=list[ConnectorSecretStatus])
def list_connector_secret_statuses(
    _user: UserResponse = Depends(require_permissions("admin.secrets.read")),
) -> list[ConnectorSecretStatus]:
    return [
        ConnectorSecretStatus(
            provider=provider,
            stored_in_vault=connector_secret_service.stored_in_vault(provider),
        )
        for provider in (
            "github",
            "google_drive",
            "jira",
            "entra_id",
            "microsoft_defender",
            "microsoft_sentinel",
        )
    ]


@app.put("/admin/connector-secrets/{provider}", response_model=ConnectorSecretStatus)
def upsert_connector_secret(
    provider: str,
    payload: ConnectorSecretWriteRequest,
    user: UserResponse = Depends(require_permissions("admin.secrets.write")),
) -> ConnectorSecretStatus:
    if provider not in {
        "github",
        "google_drive",
        "jira",
        "entra_id",
        "microsoft_defender",
        "microsoft_sentinel",
    }:
        raise HTTPException(status_code=404, detail="Unknown connector provider.")
    try:
        connector_secret_service.set(provider, payload.value)
    except SecretVaultUnavailableError as error:
        raise HTTPException(status_code=503, detail="Secret vault unavailable.") from error
    auth_service.record_audit_event(
        event_type="admin.connector_secret_updated",
        actor_user_id=user.user_id,
        metadata={"provider": provider},
    )
    return ConnectorSecretStatus(provider=provider, stored_in_vault=True)


@app.delete("/admin/connector-secrets/{provider}", response_model=DeleteResponse)
def delete_connector_secret(
    provider: str,
    user: UserResponse = Depends(require_permissions("admin.secrets.write")),
) -> DeleteResponse:
    if provider not in {
        "github",
        "google_drive",
        "jira",
        "entra_id",
        "microsoft_defender",
        "microsoft_sentinel",
    }:
        raise HTTPException(status_code=404, detail="Unknown connector provider.")
    deleted = connector_secret_service.delete(provider)
    if deleted:
        auth_service.record_audit_event(
            event_type="admin.connector_secret_deleted",
            actor_user_id=user.user_id,
            metadata={"provider": provider},
        )
    return DeleteResponse(deleted=deleted)


@app.get("/connectors/github/repositories", response_model=list[GitHubRepository])
def list_github_repositories(
    limit: int = 10,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[GitHubRepository]:
    if not github_connector.configured:
        raise HTTPException(status_code=503, detail="GitHub connector is not configured.")
    return github_connector.list_repositories(limit=min(max(limit, 1), 50))


@app.get("/connectors/github/repos/{owner}/{repo}/pulls", response_model=list[GitHubPullRequest])
def list_github_pull_requests(
    owner: str,
    repo: str,
    limit: int = 10,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[GitHubPullRequest]:
    if not github_connector.configured:
        raise HTTPException(status_code=503, detail="GitHub connector is not configured.")
    return github_connector.list_pull_requests(owner, repo, limit=min(max(limit, 1), 50))


@app.get("/connectors/google-drive/files", response_model=list[DriveFile])
def list_google_drive_files(
    q: str | None = None,
    limit: int = 10,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[DriveFile]:
    if not google_drive_connector.configured:
        raise HTTPException(status_code=503, detail="Google Drive connector is not configured.")
    return google_drive_connector.list_files(query=q, limit=min(max(limit, 1), 50))


@app.get("/connectors/jira/issues", response_model=list[JiraIssue])
def search_jira_issues(
    jql: str,
    limit: int = 10,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[JiraIssue]:
    if not jira_connector.configured:
        raise HTTPException(status_code=503, detail="Jira connector is not configured.")
    return jira_connector.search_issues(jql=jql, limit=min(max(limit, 1), 50))


@app.get("/connectors/entra-id/sign-ins", response_model=list[EntraSignIn])
def list_entra_sign_ins(
    user_principal_name: str | None = None,
    limit: int = 10,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[EntraSignIn]:
    if not entra_id_connector.configured:
        raise HTTPException(status_code=503, detail="Entra ID connector is not configured.")
    return entra_id_connector.list_sign_ins(
        limit=min(max(limit, 1), 50),
        user_principal_name=user_principal_name,
    )


@app.get("/connectors/entra-id/risky-users", response_model=list[EntraRiskyUser])
def list_entra_risky_users(
    limit: int = 10,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[EntraRiskyUser]:
    if not entra_id_connector.configured:
        raise HTTPException(status_code=503, detail="Entra ID connector is not configured.")
    return entra_id_connector.list_risky_users(limit=min(max(limit, 1), 50))


@app.get(
    "/connectors/entra-id/users/{user_id}/authentication-methods",
    response_model=list[EntraAuthenticationMethod],
)
def list_entra_authentication_methods(
    user_id: str,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[EntraAuthenticationMethod]:
    if not entra_id_connector.configured:
        raise HTTPException(status_code=503, detail="Entra ID connector is not configured.")
    return entra_id_connector.list_authentication_methods(user_id)


@app.get("/connectors/defender/incidents", response_model=list[DefenderIncident])
def list_defender_incidents(
    limit: int = 10,
    status: str | None = None,
    severity: str | None = None,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[DefenderIncident]:
    if not microsoft_defender_connector.configured:
        raise HTTPException(status_code=503, detail="Microsoft Defender connector is not configured.")
    return microsoft_defender_connector.list_incidents(
        limit=min(max(limit, 1), 50),
        status=status,
        severity=severity,
    )


@app.get("/connectors/defender/alerts", response_model=list[DefenderAlert])
def list_defender_alerts(
    limit: int = 10,
    status: str | None = None,
    severity: str | None = None,
    service_source: str | None = None,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[DefenderAlert]:
    if not microsoft_defender_connector.configured:
        raise HTTPException(status_code=503, detail="Microsoft Defender connector is not configured.")
    return microsoft_defender_connector.list_alerts(
        limit=min(max(limit, 1), 50),
        status=status,
        severity=severity,
        service_source=service_source,
    )


@app.post("/connectors/sentinel/query", response_model=SentinelQueryResult)
def run_sentinel_query(
    payload: SentinelQueryRequest,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> SentinelQueryResult:
    if not microsoft_sentinel_connector.configured:
        raise HTTPException(status_code=503, detail="Microsoft Sentinel connector is not configured.")
    return microsoft_sentinel_connector.query(payload.query, timespan=payload.timespan, max_rows=100)


@app.get("/sentinel-query-templates", response_model=list[SentinelQueryTemplate])
def list_sentinel_query_templates_endpoint(
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> list[SentinelQueryTemplate]:
    return list_sentinel_query_templates()


@app.post(
    "/sentinel-query-templates/{template_id}/render",
    response_model=SentinelQueryTemplateRenderResponse,
)
def render_sentinel_query_template_endpoint(
    template_id: str,
    payload: SentinelQueryTemplateRenderRequest,
    _user: UserResponse = Depends(require_permissions("connectors.read")),
) -> SentinelQueryTemplateRenderResponse:
    template = get_sentinel_query_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Sentinel query template not found.")
    try:
        query = render_sentinel_query_template(template, payload.parameters)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return SentinelQueryTemplateRenderResponse(
        template_id=template.template_id,
        query=query,
        timespan=payload.timespan or template.default_timespan,
    )


@app.post("/voice/chat", response_model=VoiceChatResponse)
async def voice_chat(
    file: UploadFile = File(...),
    session_id: str = "default",
    user: UserResponse = Depends(require_permissions("voice.use")),
) -> VoiceChatResponse:
    try:
        transcript = voice_service.transcribe(file.filename or "audio.webm", await file.read())
    except VoiceServiceUnavailableError as error:
        raise HTTPException(status_code=503, detail="Voice service unavailable.") from error

    answer, model, used_remote_model, _, citations = assistant_service.respond(
        user_id=user.user_id,
        session_id=session_id,
        message=transcript,
        role=user.role,
    )
    return VoiceChatResponse(
        transcript=transcript,
        session_id=session_id,
        answer=answer,
        model=model,
        used_remote_model=used_remote_model,
        citations=citations,
    )


@app.post("/voice/speech")
def synthesize_speech(
    payload: ChatRequest,
    _user: UserResponse = Depends(require_permissions("voice.use")),
) -> Response:
    try:
        audio = voice_service.synthesize(payload.message)
    except VoiceServiceUnavailableError as error:
        raise HTTPException(status_code=503, detail="Voice service unavailable.") from error
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/realtime/token")
async def create_realtime_token(user: UserResponse = Depends(require_permissions("realtime.use"))) -> dict:
    try:
        return await realtime_service.mint_client_secret(user.user_id)
    except RealtimeServiceUnavailableError as error:
        raise HTTPException(status_code=503, detail="Realtime service unavailable.") from error


@app.post("/realtime/sideband/connect", response_model=RealtimeSidebandResponse)
async def connect_realtime_sideband(
    payload: RealtimeSidebandRequest,
    user: UserResponse = Depends(require_permissions("realtime.use")),
) -> RealtimeSidebandResponse:
    try:
        connected = await realtime_sideband_manager.connect(payload.call_id, user.user_id)
    except RealtimeServiceUnavailableError as error:
        raise HTTPException(status_code=503, detail="Realtime service unavailable.") from error
    return RealtimeSidebandResponse(call_id=payload.call_id, connected=connected)


@app.delete("/realtime/sideband/{call_id}", response_model=RealtimeSidebandResponse)
async def disconnect_realtime_sideband(
    call_id: str,
    _user: UserResponse = Depends(require_permissions("realtime.use")),
) -> RealtimeSidebandResponse:
    await realtime_sideband_manager.disconnect(call_id)
    return RealtimeSidebandResponse(call_id=call_id, connected=False)


@app.post("/realtime/tools/search-knowledge")
def realtime_search_knowledge(
    payload: KnowledgeSearchRequest,
    user: UserResponse = Depends(require_permissions("knowledge.read")),
) -> dict:
    return realtime_tool_service.search_knowledge(payload.query, payload.limit, user.user_id)


@app.post("/realtime/tools/summarize-cve")
def realtime_summarize_cve(
    payload: CVEEnrichmentRequest,
    _user: UserResponse = Depends(require_permissions("workflow.cve_enrichment")),
) -> dict:
    return realtime_tool_service.summarize_cve(payload.cve_id)


@app.post("/realtime/tools/triage-alert")
def realtime_triage_alert(
    payload: AlertTriageRequest,
    _user: UserResponse = Depends(require_permissions("workflow.alert_triage")),
) -> dict:
    return realtime_tool_service.triage_alert(
        title=payload.title,
        raw_alert=payload.raw_alert,
        environment_context=payload.environment_context,
    )
