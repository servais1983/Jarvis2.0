from __future__ import annotations

import base64

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import JiraIssue
from jarvis_cyber.services.connector_secrets import connector_secret_service


class JiraConnector:
    """Read-only Jira Cloud connector using instance-scoped credentials."""

    def __init__(
        self,
        *,
        base_url: str | None = settings.jira_base_url,
        email: str | None = settings.jira_email,
        api_token: str | None = None,
        timeout_seconds: float = settings.http_timeout_seconds,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.email = email
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.email and self.resolved_api_token)

    @property
    def resolved_api_token(self) -> str | None:
        return self.api_token or connector_secret_service.get("jira")

    def search_issues(self, jql: str, limit: int = 10) -> list[JiraIssue]:
        payload = self._post(
            "/rest/api/3/search",
            json_payload={
                "jql": jql,
                "maxResults": limit,
                "fields": ["summary", "status", "updated"],
            },
        )
        return [
            JiraIssue(
                issue_id=item["id"],
                key=item["key"],
                summary=item["fields"]["summary"],
                status=item["fields"].get("status", {}).get("name"),
                updated_at=item["fields"].get("updated"),
                web_url=f"{self.base_url}/browse/{item['key']}" if self.base_url else None,
            )
            for item in payload.get("issues", [])
        ]

    def _post(self, path: str, *, json_payload: dict) -> dict:
        assert self.base_url is not None
        assert self.email is not None
        resolved_api_token = self.resolved_api_token
        assert resolved_api_token is not None
        token = base64.b64encode(f"{self.email}:{resolved_api_token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = self._client.post(
                f"{self.base_url}{path}",
                json=json_payload,
                headers=headers,
            )
        else:
            response = httpx.post(
                f"{self.base_url}{path}",
                json=json_payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        return response.json()


jira_connector = JiraConnector()
