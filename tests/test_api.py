from fastapi.testclient import TestClient
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from pydantic import SecretStr

from jarvis_cyber.api.main import app
from jarvis_cyber.core.schemas import (
    AutomationRun,
    DailyBriefResponse,
    DefenderAlert,
    DefenderIncident,
    EntraRiskyUser,
    EntraSignIn,
    InboxMarkReadResponse,
    SentinelQueryResult,
)
from jarvis_cyber.knowledge.store import SQLiteKnowledgeStore
from jarvis_cyber.services.mfa import mfa_service
from jarvis_cyber.approvals.store import SQLiteToolApprovalStore
from jarvis_cyber.inbox.store import SQLiteInboxStore
from jarvis_cyber.storage.database import Database


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["auth_required"] is False
    assert response.json()["scheduler_enabled"] is True
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_index() -> None:
    response = client.get("/")
    assert response.status_code == 200
    # Page title changed to JARVIS in the Iron Man HUD redesign
    assert "JARVIS" in response.text


def test_chat() -> None:
    response = client.post("/chat", json={"session_id": "test", "message": "Analyse cette alerte."})
    assert response.status_code == 200
    body = response.json()
    assert body["model"]
    assert body["session_id"] == "test"
    assert body["used_remote_model"] is False
    assert "Jarvis Cyber est prêt en mode local" in body["answer"]
    assert body["citations"] == []


def test_auth_register_and_me(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)

    register_response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    assert register_response.status_code == 200
    token = register_response.json()["token"]
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "alice@example.com"
    assert me_response.json()["role"] == "admin"



def test_registration_rejects_weak_password(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)

    response = client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "password123"},
    )

    assert response.status_code == 400


def test_mfa_status_is_ready_but_disabled(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)

    register_response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    token = register_response.json()["token"]
    response = client.get("/auth/mfa/status", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "required": False,
        "enabled": False,
        "factors": [],
        "unused_recovery_codes": 0,
    }


def test_mfa_totp_enrollment_requires_key(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.database", auth_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.settings.mfa_encryption_key", None)

    register_response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    token = register_response.json()["token"]
    response = client.post(
        "/auth/mfa/totp/enroll",
        headers={"Authorization": f"Bearer {token}"},
        json={"label": "Téléphone"},
    )

    assert response.status_code == 503


def test_mfa_recovery_codes_and_factor_disable_endpoints(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.database", auth_database)
    monkeypatch.setattr(
        "jarvis_cyber.services.mfa.settings.mfa_encryption_key",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )

    register_response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    token = register_response.json()["token"]
    enroll_response = client.post(
        "/auth/mfa/totp/enroll",
        headers={"Authorization": f"Bearer {token}"},
        json={"label": "Téléphone"},
    )
    enrollment = enroll_response.json()
    verification_code = mfa_service._totp(enrollment["secret"], int(datetime.now(UTC).timestamp() // 30))
    verify_response = client.post(
        "/auth/mfa/totp/verify",
        headers={"Authorization": f"Bearer {token}"},
        json={"factor_id": enrollment["factor_id"], "code": verification_code},
    )
    recovery_response = client.post(
        "/auth/mfa/recovery-codes",
        headers={"Authorization": f"Bearer {token}"},
    )
    next_code = mfa_service._totp(enrollment["secret"], int(datetime.now(UTC).timestamp() // 30) + 1)
    rejected_disable_response = client.post(
        f"/auth/mfa/factors/{enrollment['factor_id']}/disable",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": next_code, "allow_disable_last_factor": False},
    )
    disable_response = client.post(
        f"/auth/mfa/factors/{enrollment['factor_id']}/disable",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "code": recovery_response.json()["codes"][0],
            "allow_disable_last_factor": True,
        },
    )

    assert verify_response.status_code == 200
    assert recovery_response.status_code == 200
    assert len(recovery_response.json()["codes"]) == 10
    assert rejected_disable_response.status_code == 400
    assert disable_response.status_code == 200
    assert disable_response.json()["required"] is False
    assert disable_response.json()["unused_recovery_codes"] == 0


def test_profile_round_trip() -> None:
    initial_response = client.get("/profile/me")
    update_response = client.put(
        "/profile/me",
        json={
            "display_name": "Stephane",
            "job_title": "Analyste SOC",
            "organization": "Blue Team",
            "environment_summary": "Microsoft 365 et Sentinel.",
            "focus_areas": "phishing, vulnérabilités critiques",
            "preferred_language": "fr",
            "response_style": "concise",
            "approval_preference": "always_ask",
            "timezone": "Europe/Brussels",
        },
    )

    assert initial_response.status_code == 200
    assert initial_response.json()["user_id"] == "local-dev"
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Stephane"
    assert update_response.json()["response_style"] == "concise"
    assert update_response.json()["approval_preference"] == "always_ask"


def test_task_profiles_and_playbooks_round_trip() -> None:
    profile_response = client.post(
        "/task-profiles",
        json={
            "name": "Brief SOC",
            "description": "Synthèse rapide de quart.",
            "output_format": "Résumé ; faits ; risque ; prochaines actions",
            "review_checklist": "Séparer faits et hypothèses.",
        },
    )
    profile_id = profile_response.json()["profile_id"]
    playbook_response = client.post(
        "/playbooks",
        json={
            "title": "Triage phishing",
            "purpose": "Qualifier un email suspect.",
            "trigger_phrases": "phishing, email suspect",
            "steps": "Vérifier l'expéditeur puis les URLs.",
            "expected_outcome": "Décision de triage.",
            "task_profile_id": profile_id,
        },
    )
    search_response = client.post("/playbooks/search", json={"query": "phishing email", "limit": 3})

    assert profile_response.status_code == 200
    assert playbook_response.status_code == 200
    assert search_response.status_code == 200
    assert search_response.json()[0]["playbook"]["title"] == "Triage phishing"
    assert search_response.json()[0]["task_profile"]["name"] == "Brief SOC"


def test_investigation_profiles_round_trip() -> None:
    create_response = client.post(
        "/investigation-profiles",
        json={
            "name": "Compromission de compte",
            "description": "Investigation identité.",
            "trigger_phrases": "impossible travel connexion suspecte",
            "default_goal": "Confirmer si le compte est compromis.",
            "recommended_checks": "Vérifier les connexions impossibles.",
            "include_recent_github": True,
            "drive_query": "name contains 'identity'",
            "jira_jql": "project = SEC AND labels = identity",
        },
    )
    profile_id = create_response.json()["profile_id"]
    list_response = client.get("/investigation-profiles")
    delete_response = client.delete(f"/investigation-profiles/{profile_id}")

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert any(item["name"] == "Compromission de compte" for item in list_response.json())
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


def test_investigation_profile_templates_are_available() -> None:
    response = client.get("/investigation-profile-templates")

    assert response.status_code == 200
    template_ids = {item["template_id"] for item in response.json()}
    assert {
        "account-compromise",
        "phishing",
        "malware-execution",
        "critical-vulnerability",
        "data-exfiltration",
    } <= template_ids
    assert next(item for item in response.json() if item["template_id"] == "phishing")[
        "recommended_checks"
    ]


def test_investigation_cases_round_trip() -> None:
    profile_response = client.post(
        "/investigation-profiles",
        json={
            "name": "Compromission de compte",
            "recommended_checks": "Vérifier les connexions.\nContrôler MFA.",
        },
    )
    case_response = client.post(
        "/investigation-cases",
        json={
            "title": "Impossible travel",
            "raw_alert": "Connexion Bruxelles puis Tokyo.",
            "investigation_profile_id": profile_response.json()["profile_id"],
        },
    )
    case_id = case_response.json()["case"]["case_id"]
    item_id = case_response.json()["checklist_items"][0]["item_id"]
    update_response = client.patch(
        f"/investigation-cases/{case_id}/checklist/{item_id}",
        json={"status": "done", "notes": "Connexion confirmée."},
    )
    note_response = client.post(
        f"/investigation-cases/{case_id}/notes",
        json={"body": "Escalade vers IAM."},
    )
    event_response = client.post(
        f"/investigation-cases/{case_id}/events",
        json={"occurred_at": "2026-05-18T08:00:00Z", "title": "Connexion Bruxelles"},
    )
    evidence_response = client.post(
        f"/investigation-cases/{case_id}/evidence",
        json={"title": "Journal Entra ID", "source": "entra"},
    )
    hypothesis_response = client.post(
        f"/investigation-cases/{case_id}/hypotheses",
        json={"statement": "Compte compromis", "rationale": "Connexion impossible."},
    )
    hypothesis_id = hypothesis_response.json()["hypotheses"][0]["hypothesis_id"]
    hypothesis_update_response = client.patch(
        f"/investigation-cases/{case_id}/hypotheses/{hypothesis_id}",
        json={"status": "supported", "rationale": "MFA modifié."},
    )
    summary_response = client.post(f"/investigation-cases/{case_id}/summary")
    report_response = client.post(f"/investigation-cases/{case_id}/report")
    list_response = client.get("/investigation-cases")
    detail_response = client.get(f"/investigation-cases/{case_id}")
    delete_response = client.delete(f"/investigation-cases/{case_id}")

    assert case_response.status_code == 200
    assert len(case_response.json()["checklist_items"]) == 2
    assert update_response.json()["summary"]["done_checks"] == 1
    assert note_response.json()["summary"]["latest_note"] == "Escalade vers IAM."
    assert event_response.json()["events"][0]["title"] == "Connexion Bruxelles"
    assert evidence_response.json()["evidence"][0]["source"] == "entra"
    assert hypothesis_update_response.json()["summary"]["supported_hypotheses"] == 1
    assert summary_response.json()["used_remote_model"] is False
    assert summary_response.json()["result"]["supported_hypotheses"] == ["Compte compromis"]
    assert report_response.json()["used_remote_model"] is False
    assert report_response.json()["result"]["timeline"][0].startswith("2026-05-18T08:00:00Z")
    assert any(item["case_id"] == case_id for item in list_response.json())
    assert detail_response.json()["case"]["title"] == "Impossible travel"
    assert delete_response.json()["deleted"] is True


def test_watchlists_round_trip() -> None:
    create_response = client.post(
        "/watchlists",
        json={
            "title": "Microsoft 365",
            "keywords": "Microsoft Outlook",
            "exact_match": True,
            "kev_only": False,
        },
    )
    list_response = client.get("/watchlists")
    delete_response = client.delete(f"/watchlists/{create_response.json()['watchlist_id']}")

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert any(item["title"] == "Microsoft 365" for item in list_response.json())
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


def test_daily_brief_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.api.main.briefing_service.daily_brief",
        lambda user_id, days, per_watchlist_limit: DailyBriefResponse(
            generated_at="2026-05-16T00:00:00+00:00",
            window_start="2026-05-15T00:00:00+00:00",
            window_end="2026-05-16T00:00:00+00:00",
            items=[],
        ),
    )

    response = client.post("/briefs/daily", json={"days": 1, "per_watchlist_limit": 5})

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_automations_round_trip(monkeypatch) -> None:
    create_response = client.post(
        "/automations",
        json={
            "name": "Brief du matin",
            "automation_type": "daily_brief",
            "schedule_kind": "daily",
            "schedule_time": "08:00",
            "timezone": "Europe/Brussels",
            "payload": {"days": 1, "per_watchlist_limit": 5},
            "enabled": True,
            "requires_approval": False,
        },
    )
    automation_id = create_response.json()["automation_id"]
    list_response = client.get("/automations")
    monkeypatch.setattr(
        "jarvis_cyber.api.main.automation_service.run",
        lambda user_id, automation: AutomationRun(
            run_id="run-1",
            automation_id=automation.automation_id,
            status="succeeded",
            started_at="2026-05-16T00:00:00+00:00",
            finished_at="2026-05-16T00:00:01+00:00",
            output=None,
            error_message=None,
        ),
    )
    run_response = client.post(f"/automations/{automation_id}/run")
    delete_response = client.delete(f"/automations/{automation_id}")

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "succeeded"
    assert delete_response.status_code == 200


def test_inbox_endpoints(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.api.main.inbox_store.list",
        lambda user_id, unread_only=False: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.api.main.inbox_store.mark_read",
        lambda user_id, item_id: InboxMarkReadResponse(
            item_id=item_id,
            read_at="2026-05-16T00:00:00+00:00",
        ),
    )

    list_response = client.get("/inbox")
    mark_response = client.patch("/inbox/item-1/read")

    assert list_response.status_code == 200
    assert list_response.json() == []
    assert mark_response.status_code == 200
    assert mark_response.json()["item_id"] == "item-1"


def test_tool_approval_endpoints_execute_watchlist(monkeypatch, tmp_path) -> None:
    approval_database = Database(tmp_path / "approvals.db")
    monkeypatch.setattr("jarvis_cyber.approvals.store.database", approval_database)
    monkeypatch.setattr("jarvis_cyber.watchlists.store.database", approval_database)
    monkeypatch.setattr("jarvis_cyber.inbox.store.database", approval_database)
    monkeypatch.setattr("jarvis_cyber.api.main.tool_approval_store", SQLiteToolApprovalStore())
    monkeypatch.setattr("jarvis_cyber.api.main.inbox_store", SQLiteInboxStore())
    monkeypatch.setattr(
        "jarvis_cyber.api.main.auth_service.record_audit_event",
        lambda **kwargs: None,
    )
    approval = SQLiteToolApprovalStore().create(
        "local-dev",
        tool_name="create_watchlist",
        arguments={"title": "Microsoft 365", "keywords": "Microsoft Outlook"},
        reason="sensitive_tool",
        source="text_chat",
    )

    list_response = client.get("/approvals?status=pending")
    approve_response = client.post(f"/approvals/{approval.approval_id}/approve")
    watchlists_response = client.get("/watchlists")

    assert list_response.status_code == 200
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "executed"
    assert watchlists_response.json()[0]["title"] == "Microsoft 365"


def test_connector_status_and_unconfigured_endpoints(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.api.main.github_connector.token", None)
    monkeypatch.setattr("jarvis_cyber.api.main.google_drive_connector.access_token", None)
    monkeypatch.setattr("jarvis_cyber.api.main.jira_connector.api_token", None)
    monkeypatch.setattr("jarvis_cyber.api.main.entra_id_connector.access_token", None)
    monkeypatch.setattr("jarvis_cyber.api.main.microsoft_defender_connector.access_token", None)
    monkeypatch.setattr("jarvis_cyber.api.main.microsoft_sentinel_connector.access_token", None)
    monkeypatch.setattr("jarvis_cyber.api.main.microsoft_sentinel_connector.workspace_id", None)
    monkeypatch.setattr(
        "jarvis_cyber.api.main.connector_secret_service.source",
        lambda provider: "missing",
    )

    status_response = client.get("/connectors/status")
    github_response = client.get("/connectors/github/repositories")
    drive_response = client.get("/connectors/google-drive/files")
    jira_response = client.get("/connectors/jira/issues", params={"jql": "project = SEC"})
    entra_signins_response = client.get("/connectors/entra-id/sign-ins")
    entra_risky_response = client.get("/connectors/entra-id/risky-users")
    entra_methods_response = client.get("/connectors/entra-id/users/u1/authentication-methods")
    defender_incidents_response = client.get("/connectors/defender/incidents")
    defender_alerts_response = client.get("/connectors/defender/alerts")
    sentinel_response = client.post("/connectors/sentinel/query", json={"query": "SigninLogs | take 1"})

    assert status_response.status_code == 200
    assert all(item["configured"] is False for item in status_response.json())
    assert github_response.status_code == 503
    assert drive_response.status_code == 503
    assert jira_response.status_code == 503
    assert entra_signins_response.status_code == 503
    assert entra_risky_response.status_code == 503
    assert entra_methods_response.status_code == 503
    assert defender_incidents_response.status_code == 503
    assert defender_alerts_response.status_code == 503
    assert sentinel_response.status_code == 503


def test_investigation_case_entra_enrichment_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.api.main.entra_id_connector.access_token", "token")
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.entra_id_connector.list_sign_ins",
        lambda **kwargs: [
            EntraSignIn(
                sign_in_id="s1",
                created_at="2026-05-18T08:00:00Z",
                user_principal_name="analyst@example.com",
                app_display_name="Microsoft Teams",
            )
        ],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.entra_id_connector.list_risky_users",
        lambda limit: [
            EntraRiskyUser(
                user_id="u1",
                user_principal_name="analyst@example.com",
                risk_level="high",
                risk_state="atRisk",
            )
        ],
    )
    case_response = client.post(
        "/investigation-cases",
        json={"title": "Impossible travel", "raw_alert": "Suspicious login"},
    )
    case_id = case_response.json()["case"]["case_id"]

    response = client.post(
        f"/investigation-cases/{case_id}/enrich/entra-id",
        json={"user_principal_name": "analyst@example.com", "sign_in_limit": 5},
    )

    assert response.status_code == 200
    assert response.json()["result"] == {
        "sign_ins_reviewed": 1,
        "matched_risky_users": 1,
        "added_events": 1,
        "added_evidence": 2,
    }


def test_investigation_case_defender_enrichment_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.api.main.microsoft_defender_connector.access_token", "token")
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.microsoft_defender_connector.list_incidents",
        lambda **kwargs: [
            DefenderIncident(
                incident_id="29",
                display_name="Account compromise",
                status="active",
                severity="high",
            )
        ],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.microsoft_defender_connector.list_alerts",
        lambda **kwargs: [
            DefenderAlert(
                alert_id="a1",
                incident_id="29",
                title="Suspicious sign-in",
                status="new",
                severity="high",
                service_source="microsoftDefenderForEndpoint",
                first_activity_at="2026-05-18T08:00:00Z",
                evidence_count=2,
            )
        ],
    )
    case_response = client.post(
        "/investigation-cases",
        json={"title": "Impossible travel", "raw_alert": "Suspicious login"},
    )
    case_id = case_response.json()["case"]["case_id"]

    response = client.post(
        f"/investigation-cases/{case_id}/enrich/defender",
        json={"query": "sign-in", "incident_limit": 5, "alert_limit": 5},
    )

    assert response.status_code == 200
    assert response.json()["result"] == {
        "incidents_reviewed": 0,
        "alerts_reviewed": 1,
        "added_events": 1,
        "added_evidence": 1,
    }


def test_investigation_case_sentinel_enrichment_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.api.main.microsoft_sentinel_connector.access_token", "token")
    monkeypatch.setattr("jarvis_cyber.api.main.microsoft_sentinel_connector.workspace_id", "workspace-1")
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.microsoft_sentinel_connector.query",
        lambda query, **kwargs: SentinelQueryResult(
            columns=["TimeGenerated", "UserPrincipalName", "IPAddress"],
            rows=[
                {
                    "TimeGenerated": "2026-05-18T08:00:00Z",
                    "UserPrincipalName": "analyst@example.com",
                    "IPAddress": "203.0.113.10",
                }
            ],
            row_count=1,
        ),
    )
    case_response = client.post(
        "/investigation-cases",
        json={"title": "Impossible travel", "raw_alert": "Suspicious login"},
    )
    case_id = case_response.json()["case"]["case_id"]

    response = client.post(
        f"/investigation-cases/{case_id}/enrich/sentinel",
        json={"query": "SigninLogs | take 1", "timespan": "PT24H"},
    )

    assert response.status_code == 200
    assert response.json()["result"] == {
        "rows_reviewed": 1,
        "added_events": 1,
        "added_evidence": 1,
        "columns": ["TimeGenerated", "UserPrincipalName", "IPAddress"],
    }


def test_sentinel_query_templates_can_be_listed_and_rendered() -> None:
    list_response = client.get("/sentinel-query-templates")
    template_id = list_response.json()[0]["template_id"]

    render_response = client.post(
        f"/sentinel-query-templates/{template_id}/render",
        json={"parameters": {"user_principal_name": "analyst@example.com"}},
    )

    assert list_response.status_code == 200
    assert render_response.status_code == 200
    assert "analyst@example.com" in render_response.json()["query"]
    assert render_response.json()["timespan"] is not None


def test_sentinel_query_template_render_requires_parameters() -> None:
    response = client.post(
        "/sentinel-query-templates/account-signin-overview/render",
        json={"parameters": {}},
    )

    assert response.status_code == 400


def test_admin_connector_secret_status(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)
    monkeypatch.setattr(
        "jarvis_cyber.api.main.connector_secret_service.stored_in_vault",
        lambda provider: provider == "github",
    )

    admin_response = client.post(
        "/auth/register",
        json={"email": "admin@example.com", "password": "StrongPassword!123"},
    )
    token = admin_response.json()["token"]
    response = client.get(
        "/admin/connector-secrets",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()[0] == {"provider": "github", "stored_in_vault": True}


def test_admin_can_manage_user_roles(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)

    admin_response = client.post(
        "/auth/register",
        json={"email": "admin@example.com", "password": "StrongPassword!123"},
    )
    analyst_response = client.post(
        "/auth/register",
        json={"email": "analyst@example.com", "password": "StrongPassword!123"},
    )
    admin_token = admin_response.json()["token"]
    analyst_token = analyst_response.json()["token"]
    analyst_user_id = analyst_response.json()["user"]["user_id"]

    list_response = client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    denied_response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    capabilities_response = client.get(
        "/auth/capabilities",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    update_response = client.patch(
        f"/admin/users/{analyst_user_id}/role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "admin"},
    )

    assert admin_response.json()["user"]["role"] == "admin"
    assert analyst_response.json()["user"]["role"] == "analyst"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 2
    assert denied_response.status_code == 403
    assert capabilities_response.status_code == 200
    assert "admin.users.write" not in capabilities_response.json()["permissions"]
    assert update_response.status_code == 200
    assert update_response.json()["role"] == "admin"


def test_chat_requires_authentication_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.auth.settings.auth_required", True)

    response = client.post("/chat", json={"session_id": "test", "message": "Analyse cette alerte."})

    assert response.status_code == 401


def test_auth_sessions_logout_and_expiry(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)

    first_login = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    second_login = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    first_token = first_login.json()["token"]
    second_token = second_login.json()["token"]

    sessions_response = client.get(
        "/auth/sessions",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    sessions = sessions_response.json()
    other_session_id = next(session["session_id"] for session in sessions if not session["current"])
    revoke_response = client.delete(
        f"/auth/sessions/{other_session_id}",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    revoked_me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    logout_response = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    logged_out_me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {second_token}"},
    )

    third_login = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    third_token = third_login.json()["token"]
    with auth_database.connect() as connection:
        connection.execute(
            """
            UPDATE auth_tokens
            SET expires_at = ?
            """,
            ((datetime.now(UTC) - timedelta(minutes=1)).isoformat(),),
        )
    expired_me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {third_token}"},
    )

    assert sessions_response.status_code == 200
    assert len(sessions) == 2
    assert revoke_response.json()["revoked"] is True
    assert revoked_me_response.status_code == 401
    assert logout_response.json()["revoked"] is True
    assert logged_out_me_response.status_code == 401
    assert expired_me_response.status_code == 401


def test_login_rate_limiting_and_audit(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)
    monkeypatch.setattr("jarvis_cyber.auth.settings.auth_login_max_failures", 2)

    register_response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    token = register_response.json()["token"]
    first_failure = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    second_failure = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    blocked_response = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    audit_response = client.get(
        "/admin/audit-events",
        headers={"Authorization": f"Bearer {token}"},
    )
    event_types = [event["event_type"] for event in audit_response.json()]

    assert first_failure.status_code == 401
    assert second_failure.status_code == 401
    assert blocked_response.status_code == 429
    assert audit_response.status_code == 200
    assert "auth.login_failed" in event_types
    assert "auth.login_blocked" in event_types



def test_audit_filter_and_export(monkeypatch, tmp_path) -> None:
    auth_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", auth_database)

    register_response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "StrongPassword!123"},
    )
    token = register_response.json()["token"]
    client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )

    filtered_response = client.get(
        "/admin/audit-events?event_type=auth.login_failed",
        headers={"Authorization": f"Bearer {token}"},
    )
    export_response = client.get(
        "/admin/audit-events/export.csv?event_type=auth.login_failed",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert filtered_response.status_code == 200
    assert all(event["event_type"] == "auth.login_failed" for event in filtered_response.json())
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")
    assert "auth.login_failed" in export_response.text


def test_knowledge_endpoints(monkeypatch, tmp_path) -> None:
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))
    monkeypatch.setattr("jarvis_cyber.api.main.knowledge_store", store)

    create_response = client.post(
        "/knowledge/documents",
        json={"title": "Playbook", "content": "Toujours vÃ©rifier les URLs.", "source": "playbook.md"},
    )
    search_response = client.post("/knowledge/search", json={"query": "urls", "limit": 3})
    list_response = client.get("/knowledge/documents")

    assert create_response.status_code == 200
    assert search_response.status_code == 200
    assert list_response.status_code == 200
    assert len(search_response.json()) == 1
    assert len(list_response.json()) == 1

    document_id = create_response.json()["document_id"]
    delete_response = client.delete(f"/knowledge/documents/{document_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


def test_knowledge_file_upload(monkeypatch, tmp_path) -> None:
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))
    monkeypatch.setattr("jarvis_cyber.api.main.knowledge_store", store)

    response = client.post(
        "/knowledge/files",
        files={"file": ("playbook.md", b"Verifier les URLs.", "text/markdown")},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "playbook.md"


def test_knowledge_file_batch_upload(monkeypatch, tmp_path) -> None:
    store = SQLiteKnowledgeStore(tmp_path, db=Database(tmp_path / "knowledge.db"))
    monkeypatch.setattr("jarvis_cyber.api.main.knowledge_store", store)

    response = client.post(
        "/knowledge/files/batch",
        files=[
            ("files", ("playbook.md", b"Verifier les URLs.", "text/markdown")),
            ("files", ("notes.txt", b"Escalader les alertes critiques.", "text/plain")),
        ],
    )

    assert response.status_code == 200
    assert len(response.json()) == 2



def test_investigation_case_enrichment_plan_endpoint() -> None:
    case_response = client.post(
        "/investigation-cases",
        json={
            "title": "CVE-2026-12345 critique exposée",
            "raw_alert": "Vulnérabilité critique avec exploitation probable.",
        },
    )
    case_id = case_response.json()["case"]["case_id"]

    response = client.post(f"/investigation-cases/{case_id}/enrichment-plan")

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == case_id
    assert body["inferred_category"] == "critical_vulnerability"
    assert any(
        item["sentinel_template_id"] == "critical-cve-device-exposure"
        for item in body["recommendations"]
    )
    assert body["recommendations"][0]["suggested_parameters"]["cve_id"] == "CVE-2026-12345"


def test_investigation_case_incident_view_endpoint() -> None:
    case_response = client.post(
        "/investigation-cases",
        json={
            "title": "Phishing reçu par victim@example.com",
            "raw_alert": "Email suspect avec URL https://evil.example/login",
        },
    )
    case_id = case_response.json()["case"]["case_id"]

    response = client.post(f"/investigation-cases/{case_id}/incident-view")

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == case_id
    assert body["inferred_category"] == "phishing"
    assert body["indicators"]["recipient"] == "victim@example.com"
    assert any(section["title"] == "Indicateurs email / URL" for section in body["sections"])


def test_investigation_case_soc_queue_endpoint() -> None:
    cve_response = client.post(
        "/investigation-cases",
        json={
            "title": "CVE-2026-99999 critique exposée",
            "raw_alert": "Vulnérabilité critique sans preuve.",
        },
    )
    case_id = cve_response.json()["case"]["case_id"]

    response = client.get("/investigation-cases/queue")

    assert response.status_code == 200
    body = response.json()
    assert body["active_cases"] >= 1
    item = next(item for item in body["items"] if item["case_id"] == case_id)
    assert item["inferred_category"] == "critical_vulnerability"
    assert item["score"] >= 55
    assert item["reasons"]


def test_investigation_case_shift_brief_endpoint() -> None:
    cve_response = client.post(
        "/investigation-cases",
        json={
            "title": "CVE-2026-88888 critique exposée",
            "raw_alert": "Vulnérabilité critique sans preuve.",
        },
    )
    case_id = cve_response.json()["case"]["case_id"]

    response = client.get("/investigation-cases/shift-brief")

    assert response.status_code == 200
    body = response.json()
    assert body["total_active_cases"] >= 1
    assert body["critical_cases"] >= 1
    assert body["operator_guidance"]
    assert body["headline"]
    assert case_id


def test_investigation_case_sla_endpoint() -> None:
    client.post(
        "/investigation-cases",
        json={
            "title": "CVE-2026-77777 critique exposée",
            "raw_alert": "Vulnérabilité critique sans preuve.",
        },
    )

    response = client.get("/investigation-cases/sla")

    assert response.status_code == 200
    body = response.json()
    assert body["total_active_cases"] >= 1
    assert "breached_count" in body
    assert "warning_count" in body
    assert isinstance(body["items"], list)


def test_investigation_case_closure_assistant_endpoint() -> None:
    case_response = client.post(
        "/investigation-cases",
        json={"title": "Investigation à clôturer", "raw_alert": "Alerte qualifiée."},
    )
    case_id = case_response.json()["case"]["case_id"]

    response = client.post(f"/investigation-cases/{case_id}/closure-assistant")

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == case_id
    assert body["state"] == "needs_work"
    assert body["checks"]
    assert body["recommended_next_action"]
