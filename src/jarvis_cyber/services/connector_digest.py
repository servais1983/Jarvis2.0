from __future__ import annotations

from datetime import UTC, datetime

from jarvis_cyber.core.schemas import ConnectorDigestAutomationPayload, ConnectorDigestResponse
from jarvis_cyber.integrations.github import github_connector
from jarvis_cyber.integrations.google_drive import google_drive_connector
from jarvis_cyber.integrations.jira import jira_connector


class ConnectorDigestService:
    """Build a compact read-only digest from configured external connectors."""

    def build(self, payload: ConnectorDigestAutomationPayload) -> ConnectorDigestResponse:
        repositories = (
            github_connector.list_repositories(limit=payload.github_limit)
            if payload.include_github and github_connector.configured
            else []
        )
        drive_files = (
            google_drive_connector.list_files(query=payload.drive_query, limit=payload.drive_limit)
            if payload.include_google_drive and google_drive_connector.configured
            else []
        )
        jira_issues = (
            jira_connector.search_issues(payload.jira_jql, limit=payload.jira_limit)
            if payload.include_jira and payload.jira_jql and jira_connector.configured
            else []
        )
        return ConnectorDigestResponse(
            generated_at=datetime.now(UTC).isoformat(),
            repositories=repositories,
            drive_files=drive_files,
            jira_issues=jira_issues,
        )


connector_digest_service = ConnectorDigestService()
