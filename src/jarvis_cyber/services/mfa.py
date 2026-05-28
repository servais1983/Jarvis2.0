from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from datetime import UTC, datetime
from secrets import token_bytes, token_urlsafe
from urllib.parse import quote
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import (
    MFAEnrollmentResponse,
    MFARecoveryCodesResponse,
    MFAStatusResponse,
)
from jarvis_cyber.storage.database import database


class MFAEncryptionUnavailableError(RuntimeError):
    """Raised when MFA secrets cannot be safely encrypted."""


class MFAFactorNotFoundError(ValueError):
    """Raised when an MFA factor cannot be resolved."""


class InvalidMFACodeError(ValueError):
    """Raised when a supplied MFA code is invalid."""


class LastMFAFactorError(ValueError):
    """Raised when disabling a factor would remove the final required factor."""


class RecoveryCodesUnavailableError(ValueError):
    """Raised when recovery codes cannot be issued yet."""


class MFAService:
    issuer = "Jarvis Cyber"
    digits = 6
    period_seconds = 30

    def enroll_totp(self, user_id: str, email: str, label: str | None = None) -> MFAEnrollmentResponse:
        secret = base64.b32encode(token_bytes(20)).decode("ascii").rstrip("=")
        factor_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO mfa_factors
                (factor_id, user_id, factor_type, label, secret_ciphertext, enrolled_at,
                 verified_at, last_used_at, last_used_step, disabled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    factor_id,
                    user_id,
                    "totp",
                    label,
                    self._encrypt(secret),
                    now,
                    None,
                    None,
                    None,
                    None,
                ),
            )
        return MFAEnrollmentResponse(
            factor_id=factor_id,
            secret=secret,
            otpauth_uri=self._provisioning_uri(email, secret),
        )

    def verify_enrollment(self, user_id: str, factor_id: str, code: str) -> MFAStatusResponse:
        factor = self._factor(user_id, factor_id)
        secret = self._decrypt(factor["secret_ciphertext"])
        step = self._matching_step(secret, code)
        if step is None:
            raise InvalidMFACodeError("invalid_mfa_code")

        now = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                UPDATE mfa_factors
                SET verified_at = COALESCE(verified_at, ?),
                    last_used_at = ?,
                    last_used_step = ?
                WHERE user_id = ? AND factor_id = ?
                """,
                (now, now, step, user_id, factor_id),
            )
            connection.execute(
                """
                UPDATE users
                SET mfa_required = 1
                WHERE user_id = ?
                """,
                (user_id,),
            )
        from jarvis_cyber.auth import auth_service

        auth_service.record_audit_event(
            event_type="auth.mfa_totp_verified",
            actor_user_id=user_id,
            target_user_id=user_id,
            metadata={"factor_id": factor_id},
        )
        return auth_service.mfa_status(user_id)

    def verify_login(self, user_id: str, code: str | None) -> bool:
        if code is None:
            return False
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT factor_id, secret_ciphertext, last_used_step
                FROM mfa_factors
                WHERE user_id = ?
                  AND factor_type = 'totp'
                  AND verified_at IS NOT NULL
                  AND disabled_at IS NULL
                """,
                (user_id,),
            ).fetchall()
        for row in rows:
            secret = self._decrypt(row["secret_ciphertext"])
            step = self._matching_step(secret, code)
            if step is None or row["last_used_step"] == step:
                continue
            now = datetime.now(UTC).isoformat()
            with database.connect() as connection:
                connection.execute(
                    """
                    UPDATE mfa_factors
                    SET last_used_at = ?, last_used_step = ?
                    WHERE factor_id = ?
                    """,
                    (now, step, row["factor_id"]),
                )
            return True
        return self._consume_recovery_code(user_id, code)

    def has_verified_factor(self, user_id: str) -> bool:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM mfa_factors
                WHERE user_id = ?
                  AND verified_at IS NOT NULL
                  AND disabled_at IS NULL
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return row is not None

    def generate_recovery_codes(self, user_id: str, count: int = 10) -> MFARecoveryCodesResponse:
        if not self.has_verified_factor(user_id):
            raise RecoveryCodesUnavailableError("verified_factor_required")
        codes = [self._recovery_code() for _ in range(count)]
        now = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                DELETE FROM mfa_recovery_codes
                WHERE user_id = ? AND used_at IS NULL
                """,
                (user_id,),
            )
            connection.executemany(
                """
                INSERT INTO mfa_recovery_codes (code_hash, user_id, created_at, used_at)
                VALUES (?, ?, ?, ?)
                """,
                [(self._hash_recovery_code(code), user_id, now, None) for code in codes],
            )
        from jarvis_cyber.auth import auth_service

        auth_service.record_audit_event(
            event_type="auth.mfa_recovery_codes_generated",
            actor_user_id=user_id,
            target_user_id=user_id,
            metadata={"count": count},
        )
        return MFARecoveryCodesResponse(codes=codes)

    def disable_factor(
        self,
        user_id: str,
        factor_id: str,
        *,
        code: str | None,
        allow_disable_last_factor: bool,
    ) -> MFAStatusResponse:
        factor = self._factor(user_id, factor_id)
        if factor["verified_at"] is not None and not self.verify_login(user_id, code):
            raise InvalidMFACodeError("invalid_mfa_code")
        active_factors = self._active_factor_count(user_id)
        if active_factors <= 1 and not allow_disable_last_factor:
            raise LastMFAFactorError("last_mfa_factor")
        now = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                UPDATE mfa_factors
                SET disabled_at = ?
                WHERE user_id = ? AND factor_id = ?
                """,
                (now, user_id, factor_id),
            )
            if active_factors <= 1 and allow_disable_last_factor:
                connection.execute(
                    """
                    UPDATE users
                    SET mfa_required = 0
                    WHERE user_id = ?
                    """,
                    (user_id,),
                )
                connection.execute(
                    """
                    DELETE FROM mfa_recovery_codes
                    WHERE user_id = ? AND used_at IS NULL
                    """,
                    (user_id,),
                )
        from jarvis_cyber.auth import auth_service

        auth_service.record_audit_event(
            event_type="auth.mfa_factor_disabled",
            actor_user_id=user_id,
            target_user_id=user_id,
            metadata={"factor_id": factor_id, "disabled_last_factor": active_factors <= 1},
        )
        return auth_service.mfa_status(user_id)

    def _factor(self, user_id: str, factor_id: str):
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT factor_id, secret_ciphertext, verified_at
                FROM mfa_factors
                WHERE user_id = ? AND factor_id = ?
                  AND disabled_at IS NULL
                """,
                (user_id, factor_id),
            ).fetchone()
        if row is None or row["secret_ciphertext"] is None:
            raise MFAFactorNotFoundError("mfa_factor_not_found")
        return row

    def _active_factor_count(self, user_id: str) -> int:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM mfa_factors
                WHERE user_id = ?
                  AND verified_at IS NOT NULL
                  AND disabled_at IS NULL
                """,
                (user_id,),
            ).fetchone()
        return int(row["count"])

    def _encrypt(self, secret: str) -> str:
        return self._fernet().encrypt(secret.encode("utf-8")).decode("ascii")

    def _decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as error:
            raise MFAEncryptionUnavailableError("invalid_mfa_ciphertext") from error

    def _fernet(self) -> Fernet:
        if settings.mfa_encryption_key is None:
            raise MFAEncryptionUnavailableError("mfa_encryption_key_missing")
        return Fernet(settings.mfa_encryption_key.get_secret_value().encode("ascii"))

    def _matching_step(self, secret: str, code: str, now: float | None = None) -> int | None:
        current_step = int((now or time.time()) // self.period_seconds)
        for step in (current_step - 1, current_step, current_step + 1):
            if hmac.compare_digest(self._totp(secret, step), code):
                return step
        return None

    def _totp(self, secret: str, step: int) -> str:
        padded_secret = secret + "=" * (-len(secret) % 8)
        key = base64.b32decode(padded_secret, casefold=True)
        digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(binary % (10**self.digits)).zfill(self.digits)

    def _provisioning_uri(self, email: str, secret: str) -> str:
        issuer = quote(self.issuer)
        label = quote(f"{self.issuer}:{email}")
        return (
            f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
            f"&algorithm=SHA1&digits={self.digits}&period={self.period_seconds}"
        )

    @staticmethod
    def _recovery_code() -> str:
        return token_urlsafe(9).replace("-", "").replace("_", "")[:12]

    @staticmethod
    def _hash_recovery_code(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    def _consume_recovery_code(self, user_id: str, code: str) -> bool:
        code_hash = self._hash_recovery_code(code)
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE mfa_recovery_codes
                SET used_at = ?
                WHERE user_id = ?
                  AND code_hash = ?
                  AND used_at IS NULL
                """,
                (datetime.now(UTC).isoformat(), user_id, code_hash),
            )
        used = cursor.rowcount > 0
        if used:
            from jarvis_cyber.auth import auth_service

            auth_service.record_audit_event(
                event_type="auth.mfa_recovery_code_used",
                actor_user_id=user_id,
                target_user_id=user_id,
            )
        return used


mfa_service = MFAService()
