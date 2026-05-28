from __future__ import annotations

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import DriveFile
from jarvis_cyber.services.connector_secrets import connector_secret_service


class GoogleDriveConnector:
    """Read-only Google Drive connector backed by an instance-scoped access token."""

    def __init__(
        self,
        *,
        base_url: str = settings.google_drive_api_base_url,
        access_token: str | None = None,
        timeout_seconds: float = settings.http_timeout_seconds,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds
        self._client = client

    @property
    def configured(self) -> bool:
        return self.resolved_access_token is not None

    @property
    def resolved_access_token(self) -> str | None:
        return self.access_token or connector_secret_service.get("google_drive")

    def list_files(self, query: str | None = None, limit: int = 10) -> list[DriveFile]:
        params: dict[str, str | int] = {
            "pageSize": limit,
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
            "orderBy": "modifiedTime desc",
        }
        if query:
            params["q"] = query
        payload = self._get("/files", params=params)
        return [
            DriveFile(
                file_id=item["id"],
                name=item["name"],
                mime_type=item.get("mimeType"),
                modified_time=item.get("modifiedTime"),
                web_view_link=item.get("webViewLink"),
            )
            for item in payload.get("files", [])
        ]

    def _get(self, path: str, *, params: dict[str, str | int]) -> dict:
        headers = {"Authorization": f"Bearer {self.resolved_access_token}"}
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


google_drive_connector = GoogleDriveConnector()
