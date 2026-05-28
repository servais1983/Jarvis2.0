from __future__ import annotations

import sqlite3
from pathlib import Path

from jarvis_cyber.config import settings


class Database:
    """Small SQLite helper for durable local persistence."""

    def __init__(self, path: str | Path = settings.database_path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'local-dev',
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'local-dev',
                    title TEXT NOT NULL,
                    source TEXT,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'local-dev',
                    document_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    embedding_json TEXT,
                    FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id)
                );

                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'analyst',
                    mfa_required INTEGER NOT NULL DEFAULT 0,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_tokens (
                    session_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    ip_address TEXT,
                    success INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS security_audit_events (
                    event_id TEXT PRIMARY KEY,
                    actor_user_id TEXT,
                    event_type TEXT NOT NULL,
                    target_user_id TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mfa_factors (
                    factor_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    factor_type TEXT NOT NULL,
                    label TEXT,
                    secret_ciphertext TEXT,
                    enrolled_at TEXT NOT NULL,
                    verified_at TEXT,
                    last_used_at TEXT,
                    last_used_step INTEGER,
                    disabled_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    job_title TEXT,
                    organization TEXT,
                    environment_summary TEXT,
                    focus_areas TEXT,
                    preferred_language TEXT NOT NULL DEFAULT 'fr',
                    response_style TEXT NOT NULL DEFAULT 'balanced',
                    approval_preference TEXT NOT NULL DEFAULT 'ask_before_sensitive_actions',
                    timezone TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_profiles (
                    profile_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    output_format TEXT NOT NULL,
                    review_checklist TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS playbooks (
                    playbook_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    trigger_phrases TEXT,
                    steps TEXT NOT NULL,
                    expected_outcome TEXT,
                    task_profile_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_profile_id) REFERENCES task_profiles(profile_id)
                );

                CREATE TABLE IF NOT EXISTS investigation_profiles (
                    profile_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    trigger_phrases TEXT,
                    default_goal TEXT,
                    recommended_checks TEXT,
                    include_recent_github INTEGER NOT NULL DEFAULT 0,
                    drive_query TEXT,
                    jira_jql TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS investigation_cases (
                    case_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    raw_alert TEXT NOT NULL,
                    environment_context TEXT,
                    goal TEXT,
                    investigation_profile_id TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS investigation_case_checklist_items (
                    item_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'todo',
                    notes TEXT,
                    position INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES investigation_cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS investigation_case_notes (
                    note_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES investigation_cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS investigation_case_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES investigation_cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS investigation_case_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES investigation_cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS investigation_case_hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    rationale TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES investigation_cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS watchlists (
                    watchlist_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    exact_match INTEGER NOT NULL DEFAULT 0,
                    kev_only INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS automations (
                    automation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    automation_type TEXT NOT NULL,
                    schedule_kind TEXT NOT NULL,
                    schedule_time TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    next_run_at TEXT,
                    last_run_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS automation_runs (
                    run_id TEXT PRIMARY KEY,
                    automation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    output_json TEXT,
                    error_message TEXT,
                    FOREIGN KEY(automation_id) REFERENCES automations(automation_id)
                );

                CREATE TABLE IF NOT EXISTS inbox_items (
                    item_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    related_run_id TEXT,
                    payload_json TEXT,
                    read_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tool_approval_requests (
                    approval_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS secret_vault_entries (
                    name TEXT PRIMARY KEY,
                    ciphertext TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mfa_recovery_codes (
                    code_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    used_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                """
            )
            self._migrate_legacy_schema(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_turns_session_created
                ON conversation_turns(user_id, session_id, created_at);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_documents_user_hash
                ON knowledge_documents(user_id, content_hash);

                CREATE INDEX IF NOT EXISTS idx_login_attempts_lookup
                ON login_attempts(email, ip_address, created_at);

                CREATE INDEX IF NOT EXISTS idx_security_audit_events_created
                ON security_audit_events(created_at);

                CREATE INDEX IF NOT EXISTS idx_task_profiles_user_created
                ON task_profiles(user_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_playbooks_user_created
                ON playbooks(user_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_investigation_profiles_user_created
                ON investigation_profiles(user_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_investigation_cases_user_updated
                ON investigation_cases(user_id, updated_at);

                CREATE INDEX IF NOT EXISTS idx_investigation_case_items_case_position
                ON investigation_case_checklist_items(case_id, position);

                CREATE INDEX IF NOT EXISTS idx_investigation_case_notes_case_created
                ON investigation_case_notes(case_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_investigation_case_events_case_occurred
                ON investigation_case_events(case_id, occurred_at);

                CREATE INDEX IF NOT EXISTS idx_investigation_case_evidence_case_created
                ON investigation_case_evidence(case_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_investigation_case_hypotheses_case_updated
                ON investigation_case_hypotheses(case_id, updated_at);

                CREATE INDEX IF NOT EXISTS idx_watchlists_user_created
                ON watchlists(user_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_automations_user_created
                ON automations(user_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_automations_due
                ON automations(enabled, next_run_at);

                CREATE INDEX IF NOT EXISTS idx_automation_runs_lookup
                ON automation_runs(user_id, automation_id, started_at);

                CREATE INDEX IF NOT EXISTS idx_inbox_items_user_created
                ON inbox_items(user_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_inbox_items_user_read
                ON inbox_items(user_id, read_at);

                CREATE INDEX IF NOT EXISTS idx_tool_approval_requests_user_status
                ON tool_approval_requests(user_id, status, created_at);

                CREATE INDEX IF NOT EXISTS idx_mfa_recovery_codes_user
                ON mfa_recovery_codes(user_id, used_at);
                """
            )

    def _migrate_legacy_schema(self, connection: sqlite3.Connection) -> None:
        """Upgrade pre-authentication schemas in place without losing local data."""
        self._ensure_column(
            connection,
            table="conversation_turns",
            column="user_id",
            definition="TEXT NOT NULL DEFAULT 'local-dev'",
        )
        self._ensure_column(
            connection,
            table="knowledge_chunks",
            column="user_id",
            definition="TEXT NOT NULL DEFAULT 'local-dev'",
        )
        self._ensure_column(
            connection,
            table="users",
            column="role",
            definition="TEXT NOT NULL DEFAULT 'analyst'",
        )
        self._ensure_column(
            connection,
            table="users",
            column="mfa_required",
            definition="INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(
            connection,
            table="mfa_factors",
            column="secret_ciphertext",
            definition="TEXT",
        )
        self._ensure_column(
            connection,
            table="mfa_factors",
            column="last_used_step",
            definition="INTEGER",
        )
        self._ensure_column(
            connection,
            table="investigation_profiles",
            column="recommended_checks",
            definition="TEXT",
        )
        connection.execute(
            """
            UPDATE users
            SET role = 'admin'
            WHERE user_id = (
                SELECT user_id
                FROM users
                ORDER BY created_at ASC
                LIMIT 1
            )
            AND NOT EXISTS (
                SELECT 1
                FROM users
                WHERE role = 'admin'
            )
            """
        )
        self._migrate_auth_tokens(connection)

        knowledge_document_columns = self._columns(connection, "knowledge_documents")
        if "user_id" not in knowledge_document_columns or self._has_legacy_content_hash_unique_constraint(
            connection
        ):
            self._rebuild_knowledge_documents(connection)

        connection.execute("DROP INDEX IF EXISTS idx_conversation_turns_session_created")

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        if column not in self._columns(connection, table):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _has_legacy_content_hash_unique_constraint(connection: sqlite3.Connection) -> bool:
        for row in connection.execute("PRAGMA index_list(knowledge_documents)"):
            if not row["unique"]:
                continue
            indexed_columns = [
                column_row["name"]
                for column_row in connection.execute(f"PRAGMA index_info({row['name']})")
            ]
            if indexed_columns == ["content_hash"]:
                return True
        return False

    def _rebuild_knowledge_documents(self, connection: sqlite3.Connection) -> None:
        existing_columns = self._columns(connection, "knowledge_documents")
        user_id_expression = "COALESCE(user_id, 'local-dev')" if "user_id" in existing_columns else "'local-dev'"
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            f"""
            CREATE TABLE knowledge_documents_new (
                document_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'local-dev',
                title TEXT NOT NULL,
                source TEXT,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            INSERT INTO knowledge_documents_new
            (document_id, user_id, title, source, content, content_hash, created_at)
            SELECT
                document_id,
                {user_id_expression},
                title,
                source,
                content,
                content_hash,
                created_at
            FROM knowledge_documents;

            DROP TABLE knowledge_documents;
            ALTER TABLE knowledge_documents_new RENAME TO knowledge_documents;
            """
        )
        connection.execute("PRAGMA foreign_keys = ON")

    def _migrate_auth_tokens(self, connection: sqlite3.Connection) -> None:
        columns = self._columns(connection, "auth_tokens")
        if {"session_id", "token_hash", "expires_at", "last_used_at", "revoked_at"} <= columns:
            return

        rows = connection.execute("SELECT * FROM auth_tokens").fetchall()
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            CREATE TABLE auth_tokens_new (
                session_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            DROP TABLE auth_tokens;
            ALTER TABLE auth_tokens_new RENAME TO auth_tokens;
            """
        )
        from datetime import UTC, datetime, timedelta
        from hashlib import sha256
        from uuid import uuid4

        for row in rows:
            created_at = row["created_at"]
            created_dt = datetime.fromisoformat(created_at)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=UTC)
            expires_at = (created_dt + timedelta(hours=settings.auth_token_ttl_hours)).isoformat()
            connection.execute(
                """
                INSERT INTO auth_tokens
                (session_id, token_hash, user_id, created_at, expires_at, last_used_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    sha256(row["token"].encode("utf-8")).hexdigest(),
                    row["user_id"],
                    created_at,
                    expires_at,
                    None,
                    None,
                ),
            )
        connection.execute("PRAGMA foreign_keys = ON")

    def ready(self) -> bool:
        try:
            with self.connect():
                return True
        except sqlite3.Error:
            return False


database = Database()
