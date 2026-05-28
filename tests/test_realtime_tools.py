from jarvis_cyber.core.schemas import (
    AlertTriageResult,
    CVERecord,
    CVESummaryResult,
    DefenderAlert,
    DefenderIncident,
    Playbook,
    PlaybookSearchResult,
    SentinelQueryResult,
    TaskProfile,
    InboxItem,
    DriveFile,
    EntraAuthenticationMethod,
    EntraRiskyUser,
    EntraSignIn,
    GitHubRepository,
    JiraIssue,
)
from jarvis_cyber.services.realtime_tools import RealtimeToolService


def test_realtime_search_knowledge(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.knowledge_store.search",
        lambda user_id, query, limit: [],
    )
    assert RealtimeToolService().search_knowledge("phishing") == {"results": []}


def test_realtime_search_playbooks(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.playbook_store.search_playbooks",
        lambda user_id, query, limit: [
            PlaybookSearchResult(
                playbook=Playbook(
                    playbook_id="pb-1",
                    title="Triage phishing",
                    purpose="Qualifier un email.",
                    trigger_phrases="phishing",
                    steps="Vérifier les URLs.",
                    expected_outcome="Décision.",
                    task_profile_id="tp-1",
                    created_at="now",
                    updated_at="now",
                ),
                task_profile=TaskProfile(
                    profile_id="tp-1",
                    name="Brief SOC",
                    description=None,
                    output_format="Résumé",
                    review_checklist=None,
                    created_at="now",
                    updated_at="now",
                ),
                score=1.0,
            )
        ],
    )

    response = RealtimeToolService().search_playbooks("phishing", user_id="analyst-1")

    assert response["results"][0]["playbook"]["title"] == "Triage phishing"


def test_realtime_list_inbox(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.inbox_store.list",
        lambda user_id, unread_only: [
            InboxItem(
                item_id="item-1",
                item_type="automation_succeeded",
                title="Brief prêt",
                body="1 watchlist traitée.",
                related_run_id="run-1",
                payload=None,
                read_at=None,
                created_at="now",
            )
        ],
    )

    response = RealtimeToolService().list_inbox(user_id="analyst-1")

    assert response["items"][0]["title"] == "Brief prêt"


def test_realtime_connector_tools(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.github_connector.token", "token")
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.google_drive_connector.access_token", "token")
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.jira_connector.base_url", "https://jira.example")
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.jira_connector.email", "a@example.com")
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.jira_connector.api_token", "token")
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.entra_id_connector.access_token", "token")
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.microsoft_defender_connector.access_token", "token")
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.microsoft_sentinel_connector.access_token", "token")
    monkeypatch.setattr("jarvis_cyber.services.realtime_tools.microsoft_sentinel_connector.workspace_id", "workspace-1")
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.github_connector.list_repositories",
        lambda limit: [
            GitHubRepository(
                repository_id=1,
                full_name="org/repo",
                private=False,
                html_url="https://github.com/org/repo",
            )
        ],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.google_drive_connector.list_files",
        lambda query, limit: [DriveFile(file_id="f1", name="Playbook")],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.jira_connector.search_issues",
        lambda jql, limit: [JiraIssue(issue_id="1", key="SEC-1", summary="Investigate")],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.entra_id_connector.list_sign_ins",
        lambda **kwargs: [EntraSignIn(sign_in_id="s1", user_principal_name="analyst@example.com")],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.entra_id_connector.list_risky_users",
        lambda limit: [EntraRiskyUser(user_id="u1", risk_level="high")],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.entra_id_connector.list_authentication_methods",
        lambda user_id: [EntraAuthenticationMethod(method_id="m1", method_type="fido2AuthenticationMethod")],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.microsoft_defender_connector.list_incidents",
        lambda **kwargs: [DefenderIncident(incident_id="29", display_name="Account compromise")],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.microsoft_defender_connector.list_alerts",
        lambda **kwargs: [DefenderAlert(alert_id="a1", title="Suspicious sign-in")],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.microsoft_sentinel_connector.query",
        lambda query, **kwargs: SentinelQueryResult(
            columns=["UserPrincipalName"],
            rows=[{"UserPrincipalName": "analyst@example.com"}],
            row_count=1,
        ),
    )
    service = RealtimeToolService()

    assert service.list_github_repositories()["repositories"][0]["full_name"] == "org/repo"
    assert service.list_google_drive_files()["files"][0]["name"] == "Playbook"
    assert service.search_jira_issues("project = SEC")["issues"][0]["key"] == "SEC-1"
    assert service.list_entra_sign_ins()["sign_ins"][0]["user_principal_name"] == "analyst@example.com"
    assert service.list_entra_risky_users()["risky_users"][0]["risk_level"] == "high"
    assert (
        service.list_entra_authentication_methods("u1")["methods"][0]["method_type"]
        == "fido2AuthenticationMethod"
    )
    assert service.list_defender_incidents()["incidents"][0]["incident_id"] == "29"
    assert service.list_defender_alerts()["alerts"][0]["alert_id"] == "a1"
    assert service.run_sentinel_query("SigninLogs | take 1")["result"]["row_count"] == 1


def test_realtime_summarize_cve(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.cyber_workflow_service.enrich_cve",
        lambda payload: (
            CVERecord(cve_id=payload.cve_id, description="RCE"),
            CVESummaryResult(
                cve_id=payload.cve_id,
                executive_summary="RCE",
                affected_products=[],
                technical_impact="RCE",
                urgency="high",
                exploitation_signals=[],
                recommended_actions=[],
                uncertainties=[],
                confidence="high",
            ),
            "model",
            True,
        ),
    )
    result = RealtimeToolService().summarize_cve("CVE-2026-0001")
    assert result["analysis"]["urgency"] == "high"


def test_realtime_triage_alert(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.cyber_workflow_service.triage_alert",
        lambda payload: (
            AlertTriageResult(
                classification="suspicious",
                observed_facts=[],
                hypotheses=[],
                priority_checks=[],
                severity="medium",
                decision="investigate",
                rationale="Contexte insuffisant.",
                confidence="medium",
            ),
            "model",
            True,
        ),
    )
    result = RealtimeToolService().triage_alert("Titre", "Alerte brute")
    assert result["result"]["decision"] == "investigate"
