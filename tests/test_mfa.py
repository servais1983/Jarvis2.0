from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet

from jarvis_cyber.auth import AuthService, InvalidCredentialsError
from jarvis_cyber.services.mfa import MFAService
from jarvis_cyber.storage.database import Database


def test_totp_enrollment_and_login(monkeypatch, tmp_path) -> None:
    mfa_database = Database(tmp_path / "mfa.db")
    encryption_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr("jarvis_cyber.auth.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.settings.mfa_encryption_key", _secret(encryption_key))

    auth = AuthService()
    user = auth.register("alice@example.com", "StrongPassword!123").user
    mfa = MFAService()
    enrollment = mfa.enroll_totp(user.user_id, user.email, "Téléphone")
    code = mfa._totp(enrollment.secret, int(datetime.now(UTC).timestamp() // mfa.period_seconds))
    status = mfa.verify_enrollment(user.user_id, enrollment.factor_id, code)

    assert status.enabled is True
    assert status.required is True

    with pytest.raises(InvalidCredentialsError):
        auth.login(user.email, "StrongPassword!123")

    next_code = mfa._totp(
        enrollment.secret,
        int(datetime.now(UTC).timestamp() // mfa.period_seconds) + 1,
    )
    login = auth.login(user.email, "StrongPassword!123", next_code)
    assert login.user.email == user.email


def test_totp_rejects_replayed_code(monkeypatch, tmp_path) -> None:
    mfa_database = Database(tmp_path / "mfa.db")
    encryption_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr("jarvis_cyber.auth.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.settings.mfa_encryption_key", _secret(encryption_key))

    auth = AuthService()
    user = auth.register("alice@example.com", "StrongPassword!123").user
    mfa = MFAService()
    enrollment = mfa.enroll_totp(user.user_id, user.email)
    code = mfa._totp(enrollment.secret, int(datetime.now(UTC).timestamp() // mfa.period_seconds))
    mfa.verify_enrollment(user.user_id, enrollment.factor_id, code)

    assert mfa.verify_login(user.user_id, code) is False


def test_recovery_codes_are_single_use(monkeypatch, tmp_path) -> None:
    mfa_database = Database(tmp_path / "mfa.db")
    encryption_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr("jarvis_cyber.auth.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.settings.mfa_encryption_key", _secret(encryption_key))

    auth = AuthService()
    user = auth.register("alice@example.com", "StrongPassword!123").user
    mfa = MFAService()
    enrollment = mfa.enroll_totp(user.user_id, user.email)
    code = mfa._totp(enrollment.secret, int(datetime.now(UTC).timestamp() // mfa.period_seconds))
    mfa.verify_enrollment(user.user_id, enrollment.factor_id, code)
    recovery_code = mfa.generate_recovery_codes(user.user_id, count=1).codes[0]

    assert auth.login(user.email, "StrongPassword!123", recovery_code).user.email == user.email
    with pytest.raises(InvalidCredentialsError):
        auth.login(user.email, "StrongPassword!123", recovery_code)


def test_disable_last_factor_requires_explicit_override(monkeypatch, tmp_path) -> None:
    from jarvis_cyber.services.mfa import LastMFAFactorError

    mfa_database = Database(tmp_path / "mfa.db")
    encryption_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr("jarvis_cyber.auth.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.settings.mfa_encryption_key", _secret(encryption_key))

    auth = AuthService()
    user = auth.register("alice@example.com", "StrongPassword!123").user
    mfa = MFAService()
    enrollment = mfa.enroll_totp(user.user_id, user.email)
    code = mfa._totp(enrollment.secret, int(datetime.now(UTC).timestamp() // mfa.period_seconds))
    mfa.verify_enrollment(user.user_id, enrollment.factor_id, code)
    next_code = mfa._totp(
        enrollment.secret,
        int(datetime.now(UTC).timestamp() // mfa.period_seconds) + 1,
    )

    with pytest.raises(LastMFAFactorError):
        mfa.disable_factor(
            user.user_id,
            enrollment.factor_id,
            code=next_code,
            allow_disable_last_factor=False,
        )


def test_disabling_last_factor_revokes_unused_recovery_codes(monkeypatch, tmp_path) -> None:
    mfa_database = Database(tmp_path / "mfa.db")
    encryption_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr("jarvis_cyber.auth.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.settings.mfa_encryption_key", _secret(encryption_key))

    auth = AuthService()
    user = auth.register("alice@example.com", "StrongPassword!123").user
    mfa = MFAService()
    enrollment = mfa.enroll_totp(user.user_id, user.email)
    code = mfa._totp(enrollment.secret, int(datetime.now(UTC).timestamp() // mfa.period_seconds))
    mfa.verify_enrollment(user.user_id, enrollment.factor_id, code)
    mfa.generate_recovery_codes(user.user_id, count=2)
    next_code = mfa._totp(
        enrollment.secret,
        int(datetime.now(UTC).timestamp() // mfa.period_seconds) + 1,
    )

    status = mfa.disable_factor(
        user.user_id,
        enrollment.factor_id,
        code=next_code,
        allow_disable_last_factor=True,
    )

    assert status.required is False
    assert status.enabled is False
    assert status.unused_recovery_codes == 0


def test_recovery_codes_require_verified_factor(monkeypatch, tmp_path) -> None:
    from jarvis_cyber.services.mfa import RecoveryCodesUnavailableError

    mfa_database = Database(tmp_path / "mfa.db")
    monkeypatch.setattr("jarvis_cyber.auth.database", mfa_database)
    monkeypatch.setattr("jarvis_cyber.services.mfa.database", mfa_database)

    auth = AuthService()
    user = auth.register("alice@example.com", "StrongPassword!123").user
    mfa = MFAService()

    with pytest.raises(RecoveryCodesUnavailableError):
        mfa.generate_recovery_codes(user.user_id)


def _secret(value: str):
    from pydantic import SecretStr

    return SecretStr(value)
