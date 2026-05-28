from fastapi.testclient import TestClient

from jarvis_cyber.api.main import app
from jarvis_cyber.core.schemas import (
    AlertInvestigationResult,
    AlertTriageResult,
    ConnectorDigestResponse,
    DriveFile,
    CVERecord,
    InvestigationCase,
    InvestigationCaseDetail,
    InvestigationCaseEvent,
    InvestigationCaseHypothesis,
    InvestigationCaseNote,
    InvestigationCaseSummary,
    JiraIssue,
    WatchlistSuggestion,
)


client = TestClient(app)


def test_cve_summary_workflow() -> None:
    response = client.post(
        "/workflows/cve-summary",
        json={"cve_id": "CVE-2026-0001", "source_text": "Remote code execution in product X."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["used_remote_model"] is False
    assert body["result"]["urgency"] == "unknown"
    assert body["result"]["confidence"] == "low"


def test_alert_triage_workflow() -> None:
    response = client.post(
        "/workflows/alert-triage",
        json={
            "title": "Impossible travel",
            "raw_alert": "Login from Brussels followed by login from Tokyo in 4 minutes.",
            "environment_context": "User is not known to travel.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["used_remote_model"] is False
    assert body["result"]["decision"] == "investigate"
    assert body["result"]["severity"] == "unknown"


def test_incident_report_workflow() -> None:
    response = client.post(
        "/workflows/incident-report",
        json={
            "incident_summary": "Suspicious PowerShell execution on workstation WS-42.",
            "timeline": "10:02 alert, 10:05 host isolated.",
            "impact": "One workstation affected.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["used_remote_model"] is False
    assert body["result"]["confidence"] == "low"
    assert body["result"]["scope_and_impact"] == "One workstation affected."


def test_alert_investigation_workflow() -> None:
    response = client.post(
        "/workflows/alert-investigation",
        json={
            "title": "Impossible travel",
            "raw_alert": "Login from Brussels followed by login from Tokyo in 4 minutes.",
            "environment_context": "User is not known to travel.",
            "goal": "Decide whether to escalate.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["used_remote_model"] is False
    assert body["result"]["triage"]["decision"] == "investigate"
    assert body["result"]["confidence"] == "low"


def test_alert_investigation_can_create_pending_approval(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.api.main.cyber_workflow_service.investigate_alert",
        lambda user_id, payload: (
            AlertInvestigationResult(
                executive_summary="Suspicious alert.",
                triage=AlertTriageResult(
                    classification="suspicious",
                    observed_facts=["Impossible travel"],
                    hypotheses=["Compromised credentials"],
                    priority_checks=["Review sign-in logs"],
                    severity="medium",
                    decision="investigate",
                    rationale="Needs verification.",
                    confidence="medium",
                ),
                context_findings=["Playbook MFA available."],
                matched_playbooks=["Triage account compromise"],
                priority_checks=["Review sign-in logs"],
                recommended_actions=["Reset password if confirmed."],
                suggested_watchlist=WatchlistSuggestion(
                    title="Microsoft Entra",
                    keywords="Microsoft Entra",
                    rationale="Identity platform under review.",
                ),
                uncertainties=["Travel not confirmed."],
                confidence="medium",
            ),
            "model",
            True,
            [],
            [],
            ConnectorDigestResponse(generated_at="now"),
            None,
        ),
    )
    monkeypatch.setattr(
        "jarvis_cyber.api.main.tool_catalog_service.execute",
        lambda *args, **kwargs: {"approval_id": "approval-1"},
    )

    response = client.post(
        "/workflows/alert-investigation",
        json={"title": "Impossible travel", "raw_alert": "Suspicious login"},
    )

    assert response.status_code == 200
    assert response.json()["pending_approval_id"] == "approval-1"


def test_alert_investigation_returns_external_context(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.connector_digest_service.build",
        lambda payload: ConnectorDigestResponse(
            generated_at="now",
            drive_files=[DriveFile(file_id="f1", name="Incident notes")],
            jira_issues=[JiraIssue(issue_id="1", key="SEC-1", summary="Investigate alert")],
        ),
    )

    response = client.post(
        "/workflows/alert-investigation",
        json={
            "title": "Impossible travel",
            "raw_alert": "Suspicious login",
            "drive_query": "name contains 'incident'",
            "jira_jql": "project = SEC",
        },
    )

    assert response.status_code == 200
    assert response.json()["external_context"]["drive_files"][0]["name"] == "Incident notes"
    assert response.json()["external_context"]["jira_issues"][0]["key"] == "SEC-1"


def test_cve_enrichment_workflow(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.nvd_client.fetch_cve",
        lambda cve_id: CVERecord(
            cve_id=cve_id,
            description="Remote code execution.",
            known_exploited=True,
        ),
    )

    response = client.post("/workflows/cve-enrichment", json={"cve_id": "CVE-2026-0001"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "nvd"
    assert body["record"]["known_exploited"] is True
    assert body["analysis"]["confidence"] == "low"


def test_investigation_progress_summary_workflow() -> None:
    detail = InvestigationCaseDetail(
        case=InvestigationCase(
            case_id="case-1",
            title="Impossible travel",
            raw_alert="Connexion Bruxelles puis Tokyo.",
            environment_context=None,
            goal="Qualifier la compromission.",
            investigation_profile_id=None,
            status="open",
            created_at="now",
            updated_at="now",
        ),
        checklist_items=[],
        notes=[InvestigationCaseNote(note_id="note-1", body="Escalade IAM.", created_at="now")],
        events=[
            InvestigationCaseEvent(
                event_id="event-1",
                occurred_at="2026-05-18T08:00:00Z",
                title="Connexion Bruxelles",
                description=None,
                created_at="now",
            )
        ],
        hypotheses=[
            InvestigationCaseHypothesis(
                hypothesis_id="hyp-1",
                statement="Compte compromis",
                status="supported",
                rationale="Connexion impossible.",
                created_at="now",
                updated_at="now",
            )
        ],
        summary=InvestigationCaseSummary(
            total_checks=0,
            done_checks=0,
            blocked_checks=0,
            todo_checks=0,
            completion_ratio=0.0,
            next_open_checks=[],
            latest_note="Escalade IAM.",
            open_hypotheses=0,
            supported_hypotheses=1,
            rejected_hypotheses=0,
        ),
    )

    result, _, used_remote_model = __import__(
        "jarvis_cyber.services.workflows",
        fromlist=["cyber_workflow_service"],
    ).cyber_workflow_service.summarize_investigation_progress(detail)

    assert used_remote_model is False
    assert result.established_facts == ["Connexion Bruxelles"]
    assert result.supported_hypotheses == ["Compte compromis"]


def test_investigation_case_report_workflow() -> None:
    detail = InvestigationCaseDetail(
        case=InvestigationCase(
            case_id="case-1",
            title="Impossible travel",
            raw_alert="Connexion Bruxelles puis Tokyo.",
            environment_context=None,
            goal="Qualifier la compromission.",
            investigation_profile_id=None,
            status="open",
            created_at="now",
            updated_at="now",
        ),
        checklist_items=[],
        notes=[InvestigationCaseNote(note_id="note-1", body="Compte potentiellement compromis.", created_at="now")],
        events=[
            InvestigationCaseEvent(
                event_id="event-1",
                occurred_at="2026-05-18T08:00:00Z",
                title="Connexion Bruxelles",
                description=None,
                created_at="now",
            )
        ],
        hypotheses=[],
        summary=InvestigationCaseSummary(
            total_checks=0,
            done_checks=0,
            blocked_checks=0,
            todo_checks=0,
            completion_ratio=0.0,
            next_open_checks=[],
            latest_note="Compte potentiellement compromis.",
        ),
    )

    result, _, used_remote_model = __import__(
        "jarvis_cyber.services.workflows",
        fromlist=["cyber_workflow_service"],
    ).cyber_workflow_service.draft_incident_report_from_case(detail)

    assert used_remote_model is False
    assert result.timeline == ["2026-05-18T08:00:00Z — Connexion Bruxelles"]
