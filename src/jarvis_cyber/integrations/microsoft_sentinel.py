from __future__ import annotations

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import SentinelQueryResult
from jarvis_cyber.services.connector_secrets import connector_secret_service


class MicrosoftSentinelConnector:
    """Read-only Sentinel / Log Analytics connector for explicit KQL queries."""

    def __init__(
        self,
        *,
        base_url: str = settings.sentinel_api_base_url,
        workspace_id: str | None = settings.sentinel_workspace_id,
        access_token: str | None = None,
        timeout_seconds: float = settings.http_timeout_seconds,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.workspace_id = workspace_id
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.workspace_id and self.resolved_access_token)

    @property
    def resolved_access_token(self) -> str | None:
        return self.access_token or connector_secret_service.get("microsoft_sentinel")

    def query(
        self,
        query: str,
        *,
        timespan: str | None = None,
        max_rows: int = 100,
    ) -> SentinelQueryResult:
        assert self.workspace_id is not None
        payload: dict[str, str] = {"query": query}
        if timespan:
            payload["timespan"] = timespan
        response_payload = self._post(f"/workspaces/{self.workspace_id}/query", json_payload=payload)
        tables = response_payload.get("tables", [])
        if not tables:
            return SentinelQueryResult()
        first_table = tables[0]
        columns = [item["name"] for item in first_table.get("columns", [])]
        rows = [
            {column: values[index] if index < len(values) else None for index, column in enumerate(columns)}
            for values in first_table.get("rows", [])
        ]
        return SentinelQueryResult(
            columns=columns,
            rows=rows[:max_rows],
            row_count=len(rows),
            truncated=len(rows) > max_rows,
        )

    def _post(self, path: str, *, json_payload: dict[str, str]) -> dict:
        headers = {
            "Authorization": f"Bearer {self.resolved_access_token}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = self._client.post(f"{self.base_url}{path}", json=json_payload, headers=headers)
        else:
            response = httpx.post(
                f"{self.base_url}{path}",
                json=json_payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        return response.json()


microsoft_sentinel_connector = MicrosoftSentinelConnector()
