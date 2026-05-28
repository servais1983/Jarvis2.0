from __future__ import annotations

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import (
    EntraAuthenticationMethod,
    EntraRiskyUser,
    EntraSignIn,
)
from jarvis_cyber.services.connector_secrets import connector_secret_service


class EntraIDConnector:
    """Read-only Microsoft Entra ID connector backed by a Graph access token."""

    def __init__(
        self,
        *,
        base_url: str = settings.entra_id_graph_base_url,
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
        return self.access_token or connector_secret_service.get("entra_id")

    def list_sign_ins(
        self,
        *,
        limit: int = 10,
        user_principal_name: str | None = None,
    ) -> list[EntraSignIn]:
        params: dict[str, str | int] = {"$top": limit}
        if user_principal_name:
            escaped_upn = user_principal_name.replace("'", "''")
            params["$filter"] = f"userPrincipalName eq '{escaped_upn}'"
        payload = self._get("/auditLogs/signIns", params=params)
        return [
            EntraSignIn(
                sign_in_id=item["id"],
                created_at=item.get("createdDateTime"),
                user_display_name=item.get("userDisplayName"),
                user_principal_name=item.get("userPrincipalName"),
                app_display_name=item.get("appDisplayName"),
                ip_address=item.get("ipAddress"),
                client_app_used=item.get("clientAppUsed"),
                conditional_access_status=item.get("conditionalAccessStatus"),
                failure_reason=item.get("status", {}).get("failureReason"),
                city=item.get("location", {}).get("city"),
                country_or_region=item.get("location", {}).get("countryOrRegion"),
                risk_level_aggregated=item.get("riskLevelAggregated"),
            )
            for item in payload.get("value", [])
        ]

    def list_risky_users(self, *, limit: int = 10) -> list[EntraRiskyUser]:
        payload = self._get("/identityProtection/riskyUsers", params={"$top": limit})
        return [
            EntraRiskyUser(
                user_id=item["id"],
                user_principal_name=item.get("userPrincipalName"),
                user_display_name=item.get("userDisplayName"),
                risk_level=item.get("riskLevel"),
                risk_state=item.get("riskState"),
                risk_detail=item.get("riskDetail"),
                risk_last_updated_at=item.get("riskLastUpdatedDateTime"),
            )
            for item in payload.get("value", [])
        ]

    def list_authentication_methods(self, user_id: str) -> list[EntraAuthenticationMethod]:
        payload = self._get(f"/users/{user_id}/authentication/methods", params={})
        return [
            EntraAuthenticationMethod(
                method_id=item["id"],
                method_type=self._method_type(item.get("@odata.type")),
            )
            for item in payload.get("value", [])
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

    @staticmethod
    def _method_type(odata_type: str | None) -> str:
        if not odata_type:
            return "unknown"
        return odata_type.rsplit(".", maxsplit=1)[-1]


entra_id_connector = EntraIDConnector()
