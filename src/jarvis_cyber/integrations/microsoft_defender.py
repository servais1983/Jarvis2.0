from __future__ import annotations

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import DefenderAlert, DefenderIncident
from jarvis_cyber.services.connector_secrets import connector_secret_service


class MicrosoftDefenderConnector:
    """Read-only Microsoft Graph Security connector for Defender incidents and alerts."""

    def __init__(
        self,
        *,
        base_url: str = settings.defender_graph_base_url,
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
        return self.access_token or connector_secret_service.get("microsoft_defender")

    def list_incidents(
        self,
        *,
        limit: int = 10,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[DefenderIncident]:
        params = self._params(limit=limit, status=status, severity=severity)
        payload = self._get("/security/incidents", params=params)
        return [
            DefenderIncident(
                incident_id=item["id"],
                display_name=item.get("displayName"),
                status=item.get("status"),
                severity=item.get("severity"),
                classification=item.get("classification"),
                determination=item.get("determination"),
                created_at=item.get("createdDateTime"),
                last_update_at=item.get("lastUpdateDateTime"),
                incident_web_url=item.get("incidentWebUrl"),
                assigned_to=item.get("assignedTo"),
            )
            for item in payload.get("value", [])
        ]

    def list_alerts(
        self,
        *,
        limit: int = 10,
        status: str | None = None,
        severity: str | None = None,
        service_source: str | None = None,
    ) -> list[DefenderAlert]:
        params = self._params(limit=limit, status=status, severity=severity)
        if service_source:
            escaped_source = service_source.replace("'", "''")
            source_filter = f"serviceSource eq '{escaped_source}'"
            params["$filter"] = (
                f"{params['$filter']} and {source_filter}" if "$filter" in params else source_filter
            )
        payload = self._get("/security/alerts_v2", params=params)
        return [
            DefenderAlert(
                alert_id=item["id"],
                provider_alert_id=item.get("providerAlertId"),
                incident_id=item.get("incidentId"),
                title=item.get("title"),
                description=item.get("description"),
                status=item.get("status"),
                severity=item.get("severity"),
                classification=item.get("classification"),
                determination=item.get("determination"),
                service_source=item.get("serviceSource"),
                detection_source=item.get("detectionSource"),
                created_at=item.get("createdDateTime"),
                first_activity_at=item.get("firstActivityDateTime"),
                last_activity_at=item.get("lastActivityDateTime"),
                evidence_count=len(item.get("evidence", [])),
            )
            for item in payload.get("value", [])
        ]

    @staticmethod
    def _params(
        *,
        limit: int,
        status: str | None,
        severity: str | None,
    ) -> dict[str, str | int]:
        params: dict[str, str | int] = {"$top": limit}
        filters = []
        if status:
            escaped_status = status.replace("'", "''")
            filters.append(f"status eq '{escaped_status}'")
        if severity:
            escaped_severity = severity.replace("'", "''")
            filters.append(f"severity eq '{escaped_severity}'")
        if filters:
            params["$filter"] = " and ".join(filters)
        return params

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


microsoft_defender_connector = MicrosoftDefenderConnector()
