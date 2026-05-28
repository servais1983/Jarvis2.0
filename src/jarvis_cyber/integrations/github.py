from __future__ import annotations

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import GitHubPullRequest, GitHubRepository
from jarvis_cyber.services.connector_secrets import connector_secret_service


class GitHubConnector:
    """Read-only GitHub connector backed by an instance-scoped token."""

    def __init__(
        self,
        *,
        base_url: str = settings.github_api_base_url,
        token: str | None = None,
        timeout_seconds: float = settings.http_timeout_seconds,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self._client = client

    @property
    def configured(self) -> bool:
        return self.resolved_token is not None

    @property
    def resolved_token(self) -> str | None:
        return self.token or connector_secret_service.get("github")

    def list_repositories(self, limit: int = 10) -> list[GitHubRepository]:
        payload = self._get("/user/repos", params={"sort": "updated", "per_page": limit})
        return [
            GitHubRepository(
                repository_id=item["id"],
                full_name=item["full_name"],
                private=item["private"],
                html_url=item["html_url"],
                description=item.get("description"),
                updated_at=item.get("updated_at"),
            )
            for item in payload
        ]

    def list_pull_requests(self, owner: str, repo: str, limit: int = 10) -> list[GitHubPullRequest]:
        payload = self._get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "open", "per_page": limit},
        )
        return [
            GitHubPullRequest(
                pull_request_id=item["id"],
                number=item["number"],
                title=item["title"],
                state=item["state"],
                html_url=item["html_url"],
                updated_at=item.get("updated_at"),
            )
            for item in payload
        ]

    def _get(self, path: str, *, params: dict[str, str | int]) -> list[dict]:
        headers = {
            "Authorization": f"Bearer {self.resolved_token}",
            "Accept": "application/vnd.github+json",
        }
        if self._client is not None:
            response = self._client.get(f"{self.base_url}{path}", params=params, headers=headers)
        else:
            response = httpx.get(
                f"{self.base_url}{path}",
                params=params,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        return response.json()


github_connector = GitHubConnector()
