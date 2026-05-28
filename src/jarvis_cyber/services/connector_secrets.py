from __future__ import annotations

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import ConnectorCredentialSource, ConnectorProvider
from jarvis_cyber.services.secret_vault import SecretVaultUnavailableError, secret_vault_service


class ConnectorSecretService:
    _vault_names: dict[ConnectorProvider, str] = {
        "github": "connector.github.token",
        "google_drive": "connector.google_drive.access_token",
        "jira": "connector.jira.api_token",
        "entra_id": "connector.entra_id.access_token",
        "microsoft_defender": "connector.microsoft_defender.access_token",
        "microsoft_sentinel": "connector.microsoft_sentinel.access_token",
    }

    def get(self, provider: ConnectorProvider) -> str | None:
        environment_value = self._environment_value(provider)
        if environment_value is not None:
            return environment_value
        try:
            return secret_vault_service.get(self._vault_names[provider])
        except SecretVaultUnavailableError:
            return None

    def source(self, provider: ConnectorProvider) -> ConnectorCredentialSource:
        if self._environment_value(provider) is not None:
            return "environment"
        if secret_vault_service.exists(self._vault_names[provider]):
            return "vault"
        return "missing"

    def set(self, provider: ConnectorProvider, value: str) -> None:
        secret_vault_service.set(self._vault_names[provider], value)

    def stored_in_vault(self, provider: ConnectorProvider) -> bool:
        return secret_vault_service.exists(self._vault_names[provider])

    def delete(self, provider: ConnectorProvider) -> bool:
        return secret_vault_service.delete(self._vault_names[provider])

    @staticmethod
    def _environment_value(provider: ConnectorProvider) -> str | None:
        if provider == "github":
            return settings.github_token.get_secret_value() if settings.github_token else None
        if provider == "google_drive":
            return (
                settings.google_drive_access_token.get_secret_value()
                if settings.google_drive_access_token
                else None
            )
        if provider == "jira":
            return settings.jira_api_token.get_secret_value() if settings.jira_api_token else None
        if provider == "entra_id":
            return (
                settings.entra_id_access_token.get_secret_value()
                if settings.entra_id_access_token
                else None
            )
        if provider == "microsoft_defender":
            return (
                settings.defender_access_token.get_secret_value()
                if settings.defender_access_token
                else None
            )
        if provider == "microsoft_sentinel":
            return (
                settings.sentinel_access_token.get_secret_value()
                if settings.sentinel_access_token
                else None
            )
        return None


connector_secret_service = ConnectorSecretService()
