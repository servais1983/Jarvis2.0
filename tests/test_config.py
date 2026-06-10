from jarvis_cyber.config import Settings


def test_empty_optional_secrets_are_normalized_to_none() -> None:
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="",
        secret_vault_key="",
        mfa_encryption_key="",
        github_token="",
    )

    assert settings.openai_api_key is None
    assert settings.secret_vault_key is None
    assert settings.mfa_encryption_key is None
    assert settings.github_token is None
