from jarvis_cyber.core.schemas import (
    ConnectorDigestAutomationPayload,
    DriveFile,
    GitHubRepository,
    JiraIssue,
)
from jarvis_cyber.services.connector_digest import ConnectorDigestService


def test_connector_digest_uses_configured_connectors(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.services.connector_digest.github_connector.token", "token")
    monkeypatch.setattr("jarvis_cyber.services.connector_digest.google_drive_connector.access_token", "token")
    monkeypatch.setattr("jarvis_cyber.services.connector_digest.jira_connector.base_url", "https://jira.example")
    monkeypatch.setattr("jarvis_cyber.services.connector_digest.jira_connector.email", "a@example.com")
    monkeypatch.setattr("jarvis_cyber.services.connector_digest.jira_connector.api_token", "token")
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_digest.github_connector.list_repositories",
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
        "jarvis_cyber.services.connector_digest.google_drive_connector.list_files",
        lambda query, limit: [DriveFile(file_id="f1", name="Playbook")],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_digest.jira_connector.search_issues",
        lambda jql, limit: [JiraIssue(issue_id="1", key="SEC-1", summary="Investigate")],
    )

    digest = ConnectorDigestService().build(
        ConnectorDigestAutomationPayload(drive_query="name contains 'playbook'", jira_jql="project = SEC")
    )

    assert digest.repositories[0].full_name == "org/repo"
    assert digest.drive_files[0].name == "Playbook"
    assert digest.jira_issues[0].key == "SEC-1"
