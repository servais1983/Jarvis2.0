from cryptography.fernet import Fernet
from pydantic import SecretStr

from jarvis_cyber.services.connector_secrets import ConnectorSecretService
from jarvis_cyber.services.secret_vault import SecretVaultService, SecretVaultUnavailableError
from jarvis_cyber.storage.database import Database


def test_secret_vault_round_trip(monkeypatch, tmp_path) -> None:
    vault_database = Database(tmp_path / "vault.db")
    monkeypatch.setattr("jarvis_cyber.services.secret_vault.database", vault_database)
    monkeypatch.setattr(
        "jarvis_cyber.services.secret_vault.settings.secret_vault_key",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    vault = SecretVaultService()

    vault.set("connector.github.token", "secret-token")

    assert vault.get("connector.github.token") == "secret-token"
    assert vault.exists("connector.github.token") is True


def test_connector_secret_prefers_environment(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_secrets.settings.github_token",
        SecretStr("env-token"),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_secrets.secret_vault_service.get",
        lambda name: "vault-token",
    )

    service = ConnectorSecretService()

    assert service.get("github") == "env-token"
    assert service.source("github") == "environment"


def test_connector_secret_returns_none_when_vault_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_secrets.settings.github_token",
        None,
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_secrets.secret_vault_service.get",
        lambda name: (_ for _ in ()).throw(SecretVaultUnavailableError("secret_vault_key_missing")),
    )

    service = ConnectorSecretService()

    assert service.get("github") is None


def test_connector_secret_supports_entra_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_secrets.settings.entra_id_access_token",
        SecretStr("entra-token"),
    )

    service = ConnectorSecretService()

    assert service.get("entra_id") == "entra-token"
    assert service.source("entra_id") == "environment"


def test_connector_secret_supports_microsoft_defender(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_secrets.settings.defender_access_token",
        SecretStr("defender-token"),
    )

    service = ConnectorSecretService()

    assert service.get("microsoft_defender") == "defender-token"
    assert service.source("microsoft_defender") == "environment"


def test_connector_secret_supports_microsoft_sentinel(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.connector_secrets.settings.sentinel_access_token",
        SecretStr("sentinel-token"),
    )

    service = ConnectorSecretService()

    assert service.get("microsoft_sentinel") == "sentinel-token"
    assert service.source("microsoft_sentinel") == "environment"
