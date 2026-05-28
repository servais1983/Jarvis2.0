from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Callable
from uuid import uuid4

from fastapi import Depends, Header, HTTPException

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import (
    AuditEventResponse,
    AuthSessionResponse,
    AuthTokenResponse,
    LogoutResponse,
    MFAFactorResponse,
    MFAStatusResponse,
    UserCapabilitiesResponse,
    UserResponse,
)
from jarvis_cyber.storage.database import database


LOCAL_DEV_USER_ID = "local-dev"
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "chat.use",
        "knowledge.read",
        "knowledge.write",
        "knowledge.delete",
        "voice.use",
        "realtime.use",
        "workflow.cve_summary",
        "workflow.cve_enrichment",
        "workflow.alert_triage",
        "workflow.alert_investigation",
        "workflow.incident_report",
        "task_profiles.read",
        "task_profiles.write",
        "task_profiles.delete",
        "playbooks.read",
        "playbooks.write",
        "playbooks.delete",
        "investigation_profiles.read",
        "investigation_profiles.write",
        "investigation_profiles.delete",
        "investigations.read",
        "investigations.write",
        "investigations.delete",
        "watchlists.read",
        "watchlists.write",
        "watchlists.delete",
        "briefs.daily",
        "automations.read",
        "automations.write",
        "automations.run",
        "automations.delete",
        "inbox.read",
        "inbox.write",
        "approvals.read",
        "approvals.write",
        "connectors.read",
        "admin.users.read",
        "admin.users.write",
        "admin.audit.read",
        "admin.audit.export",
        "admin.secrets.read",
        "admin.secrets.write",
    },
    "analyst": {
        "chat.use",
        "knowledge.read",
        "knowledge.write",
        "knowledge.delete",
        "voice.use",
        "realtime.use",
        "workflow.cve_summary",
        "workflow.cve_enrichment",
        "workflow.alert_triage",
        "workflow.alert_investigation",
        "workflow.incident_report",
        "task_profiles.read",
        "task_profiles.write",
        "task_profiles.delete",
        "playbooks.read",
        "playbooks.write",
        "playbooks.delete",
        "investigation_profiles.read",
        "investigation_profiles.write",
        "investigation_profiles.delete",
        "investigations.read",
        "investigations.write",
        "investigations.delete",
        "watchlists.read",
        "watchlists.write",
        "watchlists.delete",
        "briefs.daily",
        "automations.read",
        "automations.write",
        "automations.run",
        "automations.delete",
        "inbox.read",
        "inbox.write",
        "approvals.read",
        "approvals.write",
        "connectors.read",
    },
}
COMMON_PASSWORDS = {
    "password",
    "password123",
    "123456789",
    "qwerty123",
    "admin123",
    "letmein123",
}


class AuthService:
    def register(
        self,
        email: str,
        password: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuthTokenResponse:
        self._validate_password(email, password)
        created_at = datetime.now(UTC).isoformat()
        user_id = str(uuid4())
        password_hash = self._hash_password(password)
        with database.connect() as connection:
            existing_users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            role = "admin" if existing_users == 0 else "analyst"
            connection.execute(
                """
                INSERT INTO users (user_id, email, role, mfa_required, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, email.lower(), role, False, password_hash, created_at),
            )
        self.record_audit_event(
            event_type="auth.registered",
            actor_user_id=user_id,
            target_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"role": role},
        )
        return self._issue_token(user_id)

    def login(
        self,
        email: str,
        password: str,
        mfa_code: str | None = None,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuthTokenResponse:
        normalized_email = email.lower()
        if self._is_login_blocked(normalized_email, ip_address):
            self.record_audit_event(
                event_type="auth.login_blocked",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"email": normalized_email},
            )
            raise LoginRateLimitedError("login_rate_limited")

        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, password_hash
                FROM users
                WHERE email = ?
                """,
                (normalized_email,),
            ).fetchone()
        if row is None or not self._verify_password(password, row["password_hash"]):
            self._record_login_attempt(normalized_email, ip_address, success=False)
            self.record_audit_event(
                event_type="auth.login_failed",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"email": normalized_email},
            )
            raise InvalidCredentialsError("invalid_credentials")
        from jarvis_cyber.services.mfa import mfa_service

        if mfa_service.has_verified_factor(row["user_id"]) and not mfa_service.verify_login(
            row["user_id"], mfa_code
        ):
            self._record_login_attempt(normalized_email, ip_address, success=False)
            self.record_audit_event(
                event_type="auth.mfa_failed",
                actor_user_id=row["user_id"],
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise InvalidCredentialsError("invalid_mfa_code")
        self._record_login_attempt(normalized_email, ip_address, success=True)
        self._clear_failed_login_attempts(normalized_email, ip_address)
        self.record_audit_event(
            event_type="auth.login_succeeded",
            actor_user_id=row["user_id"],
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return self._issue_token(row["user_id"])

    def authenticate_token(self, token: str) -> UserResponse | None:
        token_hash = self._hash_token(token)
        now = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT users.user_id, users.email, users.role, users.mfa_required, users.created_at
                FROM auth_tokens
                JOIN users ON users.user_id = auth_tokens.user_id
                WHERE auth_tokens.token_hash = ?
                  AND auth_tokens.revoked_at IS NULL
                  AND auth_tokens.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            if row is not None:
                connection.execute(
                    """
                    UPDATE auth_tokens
                    SET last_used_at = ?
                    WHERE token_hash = ?
                    """,
                    (now, token_hash),
                )
        return UserResponse(**dict(row)) if row is not None else None

    def _issue_token(self, user_id: str) -> AuthTokenResponse:
        token = token_urlsafe(32)
        token_hash = self._hash_token(token)
        session_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        expires_at = (
            datetime.now(UTC) + timedelta(hours=settings.auth_token_ttl_hours)
        ).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_tokens
                (session_id, token_hash, user_id, created_at, expires_at, last_used_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, token_hash, user_id, created_at, expires_at, None, None),
            )
            row = connection.execute(
                """
                SELECT user_id, email, role, mfa_required, created_at
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return AuthTokenResponse(token=token, user=UserResponse(**dict(row)))

    def revoke_token(
        self,
        token: str,
        *,
        actor_user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> LogoutResponse:
        token_hash = self._hash_token(token)
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_tokens
                SET revoked_at = ?
                WHERE token_hash = ?
                  AND revoked_at IS NULL
                """,
                (datetime.now(UTC).isoformat(), token_hash),
            )
        revoked = cursor.rowcount > 0
        if revoked:
            self.record_audit_event(
                event_type="auth.logout",
                actor_user_id=actor_user_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return LogoutResponse(revoked=revoked)

    def list_sessions(self, user_id: str, current_token: str) -> list[AuthSessionResponse]:
        current_hash = self._hash_token(current_token)
        now = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, token_hash, created_at, expires_at, last_used_at
                FROM auth_tokens
                WHERE user_id = ?
                  AND revoked_at IS NULL
                  AND expires_at > ?
                ORDER BY created_at DESC
                """,
                (user_id, now),
            ).fetchall()
        return [
            AuthSessionResponse(
                session_id=row["session_id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                last_used_at=row["last_used_at"],
                current=row["token_hash"] == current_hash,
            )
            for row in rows
        ]

    def revoke_session(
        self,
        user_id: str,
        session_id: str,
        *,
        actor_user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_tokens
                SET revoked_at = ?
                WHERE session_id = ?
                  AND user_id = ?
                  AND revoked_at IS NULL
                """,
                (datetime.now(UTC).isoformat(), session_id, user_id),
            )
        revoked = cursor.rowcount > 0
        if revoked:
            self.record_audit_event(
                event_type="auth.session_revoked",
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"session_id": session_id},
            )
        return revoked

    def list_users(self) -> list[UserResponse]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id, email, role, mfa_required, created_at
                FROM users
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [UserResponse(**dict(row)) for row in rows]

    def list_user_ids(self) -> list[str]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id
                FROM users
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [row["user_id"] for row in rows]

    def update_role(
        self,
        user_id: str,
        role: str,
        *,
        actor_user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserResponse | None:
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET role = ?
                WHERE user_id = ?
                """,
                (role, user_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT user_id, email, role, mfa_required, created_at
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        updated = UserResponse(**dict(row))
        self.record_audit_event(
            event_type="admin.role_updated",
            actor_user_id=actor_user_id,
            target_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"role": role},
        )
        return updated

    @staticmethod
    def capabilities_for(user: UserResponse) -> UserCapabilitiesResponse:
        return UserCapabilitiesResponse(role=user.role, permissions=sorted(ROLE_PERMISSIONS[user.role]))

    def mfa_status(self, user_id: str) -> MFAStatusResponse:
        with database.connect() as connection:
            user_row = connection.execute(
                """
                SELECT mfa_required
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            factor_rows = connection.execute(
                """
                SELECT factor_id, factor_type, label, enrolled_at, verified_at, last_used_at, disabled_at
                FROM mfa_factors
                WHERE user_id = ?
                ORDER BY enrolled_at ASC
                """,
                (user_id,),
            ).fetchall()
            recovery_code_row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM mfa_recovery_codes
                WHERE user_id = ?
                  AND used_at IS NULL
                """,
                (user_id,),
            ).fetchone()
        factors = [MFAFactorResponse(**dict(row)) for row in factor_rows]
        return MFAStatusResponse(
            required=bool(user_row["mfa_required"]) if user_row is not None else False,
            enabled=any(factor.verified_at is not None and factor.disabled_at is None for factor in factors),
            factors=factors,
            unused_recovery_codes=int(recovery_code_row["count"]) if recovery_code_row is not None else 0,
        )

    def list_audit_events(
        self,
        *,
        limit: int = 50,
        event_type: str | None = None,
        actor_user_id: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> list[AuditEventResponse]:
        clauses: list[str] = []
        params: list[str | int] = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if actor_user_id:
            clauses.append("actor_user_id = ?")
            params.append(actor_user_id)
        if created_from:
            clauses.append("created_at >= ?")
            params.append(created_from)
        if created_to:
            clauses.append("created_at <= ?")
            params.append(created_to)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT event_id, actor_user_id, event_type, target_user_id, ip_address,
                       user_agent, metadata_json, created_at
                FROM security_audit_events
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [
            AuditEventResponse(
                event_id=row["event_id"],
                actor_user_id=row["actor_user_id"],
                event_type=row["event_type"],
                target_user_id=row["target_user_id"],
                ip_address=row["ip_address"],
                user_agent=row["user_agent"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def record_audit_event(
        self,
        *,
        event_type: str,
        actor_user_id: str | None = None,
        target_user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO security_audit_events
                (event_id, actor_user_id, event_type, target_user_id, ip_address,
                 user_agent, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    actor_user_id,
                    event_type,
                    target_user_id,
                    ip_address,
                    user_agent,
                    json.dumps(metadata or {}, sort_keys=True),
                    datetime.now(UTC).isoformat(),
                ),
            )

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
        return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        salt_b64, digest_b64 = stored.split("$", maxsplit=1)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _is_login_blocked(self, email: str, ip_address: str | None) -> bool:
        window_start = (
            datetime.now(UTC) - timedelta(minutes=settings.auth_login_window_minutes)
        ).isoformat()
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS failures, MAX(created_at) AS latest_failure
                FROM login_attempts
                WHERE email = ?
                  AND COALESCE(ip_address, '') = COALESCE(?, '')
                  AND success = 0
                  AND created_at >= ?
                """,
                (email, ip_address, window_start),
            ).fetchone()
        if row["failures"] < settings.auth_login_max_failures or row["latest_failure"] is None:
            return False
        latest_failure = datetime.fromisoformat(row["latest_failure"])
        if latest_failure.tzinfo is None:
            latest_failure = latest_failure.replace(tzinfo=UTC)
        return latest_failure + timedelta(minutes=settings.auth_login_lock_minutes) > datetime.now(UTC)

    def _record_login_attempt(self, email: str, ip_address: str | None, *, success: bool) -> None:
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO login_attempts (email, ip_address, success, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (email, ip_address, int(success), datetime.now(UTC).isoformat()),
            )

    def _clear_failed_login_attempts(self, email: str, ip_address: str | None) -> None:
        with database.connect() as connection:
            connection.execute(
                """
                DELETE FROM login_attempts
                WHERE email = ?
                  AND COALESCE(ip_address, '') = COALESCE(?, '')
                  AND success = 0
                """,
                (email, ip_address),
            )

    def _validate_password(self, email: str, password: str) -> None:
        if len(password) < settings.auth_password_min_length:
            raise WeakPasswordError("password_too_short")
        if password.lower() in COMMON_PASSWORDS:
            raise WeakPasswordError("password_too_common")
        if email.split("@", maxsplit=1)[0].lower() in password.lower():
            raise WeakPasswordError("password_contains_email")
        if not re.search(r"[A-Z]", password):
            raise WeakPasswordError("password_missing_uppercase")
        if not re.search(r"[a-z]", password):
            raise WeakPasswordError("password_missing_lowercase")
        if not re.search(r"\d", password):
            raise WeakPasswordError("password_missing_digit")
        if not re.search(r"[^A-Za-z0-9]", password):
            raise WeakPasswordError("password_missing_symbol")


auth_service = AuthService()


class InvalidCredentialsError(ValueError):
    """Raised when supplied credentials do not match a user."""


class LoginRateLimitedError(RuntimeError):
    """Raised when a login tuple is temporarily blocked after repeated failures."""


class WeakPasswordError(ValueError):
    """Raised when a password does not satisfy the configured local policy."""


def current_user(authorization: str | None = Header(default=None)) -> UserResponse:
    if not settings.auth_required and authorization is None:
        return UserResponse(
            user_id=LOCAL_DEV_USER_ID,
            email="local-dev@jarvis",
            role="admin",
            mfa_required=False,
            created_at="development",
        )

    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")

    token = authorization.removeprefix("Bearer ").strip()
    user = auth_service.authenticate_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return user


def current_token(authorization: str | None = Header(default=None)) -> str | None:
    if authorization is None:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")
    return authorization.removeprefix("Bearer ").strip()


def require_roles(*allowed_roles: str) -> Callable[[UserResponse], UserResponse]:
    def dependency(user: UserResponse = Depends(current_user)) -> UserResponse:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return user

    return dependency


def require_permissions(*required_permissions: str) -> Callable[[UserResponse], UserResponse]:
    def dependency(user: UserResponse = Depends(current_user)) -> UserResponse:
        user_permissions = ROLE_PERMISSIONS[user.role]
        if not set(required_permissions) <= user_permissions:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return user

    return dependency
