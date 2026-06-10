from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JARVIS_",
        extra="ignore",
        populate_by_name=True,
    )

    env: str = "development"
    main_model: str = "gpt-5.4"
    fast_model: str = "gpt-5.4-mini"
    realtime_model: str = "gpt-realtime-mini"
    history_limit: int = 12
    memory_backend: str = "local"
    data_dir: str = "./data"
    storage_backend: str = "sqlite"
    database_path: str = "./data/jarvis.db"
    log_level: str = "INFO"
    auth_required: bool = False
    auth_token_ttl_hours: int = 12
    auth_login_window_minutes: int = 15
    auth_login_max_failures: int = 5
    auth_login_lock_minutes: int = 15
    auth_password_min_length: int = 12
    mfa_encryption_key: SecretStr | None = None
    secret_vault_key: SecretStr | None = None
    hsts_enabled: bool = False
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    knowledge_max_chunks: int = 3
    knowledge_chunk_size: int = 900
    knowledge_chunk_overlap: int = 120
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int | None = 256
    transcription_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "alloy"
    realtime_voice: str = "marin"
    nvd_base_url: str = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    nvd_api_key: SecretStr | None = None
    github_api_base_url: str = "https://api.github.com"
    github_token: SecretStr | None = None
    google_drive_api_base_url: str = "https://www.googleapis.com/drive/v3"
    google_drive_access_token: SecretStr | None = None
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: SecretStr | None = None
    entra_id_graph_base_url: str = "https://graph.microsoft.com/v1.0"
    entra_id_access_token: SecretStr | None = None
    defender_graph_base_url: str = "https://graph.microsoft.com/v1.0"
    defender_access_token: SecretStr | None = None
    sentinel_api_base_url: str = "https://api.loganalytics.azure.com/v1"
    sentinel_workspace_id: str | None = None
    sentinel_access_token: SecretStr | None = None
    http_timeout_seconds: float = 20.0
    host: str = "127.0.0.1"
    port: int = 8000
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    @field_validator(
        "mfa_encryption_key",
        "secret_vault_key",
        "nvd_api_key",
        "github_token",
        "google_drive_access_token",
        "jira_api_token",
        "entra_id_access_token",
        "defender_access_token",
        "sentinel_access_token",
        "openai_api_key",
        mode="before",
    )
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


settings = Settings()
