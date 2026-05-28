from __future__ import annotations

from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken

from jarvis_cyber.config import settings
from jarvis_cyber.storage.database import database


class SecretVaultUnavailableError(RuntimeError):
    """Raised when the local vault cannot safely encrypt or decrypt secrets."""


class SecretVaultService:
    """Small encrypted local vault for application-scoped secrets."""

    def set(self, name: str, value: str) -> None:
        now = datetime.now(UTC).isoformat()
        ciphertext = self._fernet().encrypt(value.encode("utf-8")).decode("ascii")
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO secret_vault_entries (name, ciphertext, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    ciphertext = excluded.ciphertext,
                    updated_at = excluded.updated_at
                """,
                (name, ciphertext, now, now),
            )

    def get(self, name: str) -> str | None:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT ciphertext
                FROM secret_vault_entries
                WHERE name = ?
                """,
                (name,),
            ).fetchone()
        if row is None:
            return None
        try:
            return self._fernet().decrypt(row["ciphertext"].encode("ascii")).decode("utf-8")
        except InvalidToken as error:
            raise SecretVaultUnavailableError("invalid_vault_ciphertext") from error

    def exists(self, name: str) -> bool:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM secret_vault_entries
                WHERE name = ?
                LIMIT 1
                """,
                (name,),
            ).fetchone()
        return row is not None

    def delete(self, name: str) -> bool:
        with database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM secret_vault_entries
                WHERE name = ?
                """,
                (name,),
            )
        return cursor.rowcount > 0

    def _fernet(self) -> Fernet:
        if settings.secret_vault_key is None:
            raise SecretVaultUnavailableError("secret_vault_key_missing")
        return Fernet(settings.secret_vault_key.get_secret_value().encode("ascii"))


secret_vault_service = SecretVaultService()
