import httpx

from jarvis_cyber.integrations.github import GitHubConnector
from jarvis_cyber.integrations.google_drive import GoogleDriveConnector
from jarvis_cyber.integrations.jira import JiraConnector
from jarvis_cyber.integrations.entra_id import EntraIDConnector
from jarvis_cyber.integrations.microsoft_defender import MicrosoftDefenderConnector
from jarvis_cyber.integrations.microsoft_sentinel import MicrosoftSentinelConnector


def test_github_connector_lists_repositories() -> None:
    payload = [
        {
            "id": 1,
            "full_name": "org/repo",
            "private": True,
            "html_url": "https://github.com/org/repo",
            "description": "Repo",
            "updated_at": "2026-05-16T00:00:00Z",
        }
    ]
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    repositories = GitHubConnector(token="token", client=client).list_repositories()

    assert repositories[0].full_name == "org/repo"


def test_google_drive_connector_lists_files() -> None:
    payload = {
        "files": [
            {
                "id": "file-1",
                "name": "Playbook",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-05-16T00:00:00Z",
                "webViewLink": "https://drive.google.com/file-1",
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    files = GoogleDriveConnector(access_token="token", client=client).list_files()

    assert files[0].name == "Playbook"


def test_jira_connector_searches_issues() -> None:
    payload = {
        "issues": [
            {
                "id": "1001",
                "key": "SEC-1",
                "fields": {
                    "summary": "Investigate alert",
                    "status": {"name": "Open"},
                    "updated": "2026-05-16T00:00:00Z",
                },
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    issues = JiraConnector(
        base_url="https://example.atlassian.net",
        email="analyst@example.com",
        api_token="token",
        client=client,
    ).search_issues("project = SEC")

    assert issues[0].key == "SEC-1"


def test_entra_id_connector_lists_sign_ins() -> None:
    payload = {
        "value": [
            {
                "id": "sign-in-1",
                "createdDateTime": "2026-05-18T08:00:00Z",
                "userDisplayName": "Analyst",
                "userPrincipalName": "analyst@example.com",
                "appDisplayName": "Microsoft Teams",
                "ipAddress": "203.0.113.10",
                "clientAppUsed": "Browser",
                "conditionalAccessStatus": "success",
                "status": {"failureReason": None},
                "location": {"city": "Brussels", "countryOrRegion": "BE"},
                "riskLevelAggregated": "low",
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    sign_ins = EntraIDConnector(access_token="token", client=client).list_sign_ins(
        user_principal_name="analyst@example.com"
    )

    assert sign_ins[0].user_principal_name == "analyst@example.com"
    assert sign_ins[0].country_or_region == "BE"


def test_entra_id_connector_lists_risky_users() -> None:
    payload = {
        "value": [
            {
                "id": "user-1",
                "userPrincipalName": "analyst@example.com",
                "userDisplayName": "Analyst",
                "riskLevel": "high",
                "riskState": "atRisk",
                "riskDetail": "adminConfirmedUserCompromised",
                "riskLastUpdatedDateTime": "2026-05-18T08:00:00Z",
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    users = EntraIDConnector(access_token="token", client=client).list_risky_users()

    assert users[0].risk_level == "high"
    assert users[0].risk_state == "atRisk"


def test_entra_id_connector_lists_authentication_method_types_only() -> None:
    payload = {
        "value": [
            {
                "id": "method-1",
                "@odata.type": "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod",
                "displayName": "Personal phone",
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    methods = EntraIDConnector(access_token="token", client=client).list_authentication_methods("user-1")

    assert methods[0].method_type == "microsoftAuthenticatorAuthenticationMethod"


def test_microsoft_defender_connector_lists_incidents() -> None:
    payload = {
        "value": [
            {
                "id": "29",
                "displayName": "Account compromise",
                "status": "active",
                "severity": "high",
                "classification": "unknown",
                "determination": "unknown",
                "createdDateTime": "2026-05-18T08:00:00Z",
                "lastUpdateDateTime": "2026-05-18T09:00:00Z",
                "incidentWebUrl": "https://security.microsoft.com/incident2/29",
                "assignedTo": "analyst@example.com",
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    incidents = MicrosoftDefenderConnector(access_token="token", client=client).list_incidents()

    assert incidents[0].incident_id == "29"
    assert incidents[0].severity == "high"


def test_microsoft_defender_connector_lists_alerts() -> None:
    payload = {
        "value": [
            {
                "id": "alert-1",
                "providerAlertId": "provider-1",
                "incidentId": "29",
                "title": "Suspicious sign-in",
                "description": "Impossible travel",
                "status": "new",
                "severity": "high",
                "classification": "unknown",
                "determination": "unknown",
                "serviceSource": "microsoftDefenderForEndpoint",
                "detectionSource": "antivirus",
                "createdDateTime": "2026-05-18T08:00:00Z",
                "firstActivityDateTime": "2026-05-18T07:50:00Z",
                "lastActivityDateTime": "2026-05-18T08:05:00Z",
                "evidence": [{"id": "e1"}, {"id": "e2"}],
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    alerts = MicrosoftDefenderConnector(access_token="token", client=client).list_alerts(
        service_source="microsoftDefenderForEndpoint"
    )

    assert alerts[0].alert_id == "alert-1"
    assert alerts[0].evidence_count == 2


def test_microsoft_sentinel_connector_runs_kql_query() -> None:
    payload = {
        "tables": [
            {
                "name": "PrimaryResult",
                "columns": [
                    {"name": "TimeGenerated", "type": "datetime"},
                    {"name": "UserPrincipalName", "type": "string"},
                    {"name": "IPAddress", "type": "string"},
                ],
                "rows": [["2026-05-18T08:00:00Z", "analyst@example.com", "203.0.113.10"]],
            }
        ]
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    result = MicrosoftSentinelConnector(
        workspace_id="workspace-1",
        access_token="token",
        client=client,
    ).query("SigninLogs | take 1")

    assert result.row_count == 1
    assert result.rows[0]["UserPrincipalName"] == "analyst@example.com"
