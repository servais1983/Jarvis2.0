import sqlite3

from jarvis_cyber.storage.database import Database


def test_database_migrates_legacy_users_to_admin(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            INSERT INTO users (user_id, email, password_hash, created_at)
            VALUES ('legacy-user', 'legacy@example.com', 'hash', '2026-05-16T00:00:00+00:00');
            """
        )

    database = Database(path)
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT role
            FROM users
            WHERE user_id = 'legacy-user'
            """
        ).fetchone()

    assert row["role"] == "admin"


def test_database_migrates_legacy_plaintext_tokens(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'admin',
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE auth_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            INSERT INTO users (user_id, email, role, password_hash, created_at)
            VALUES ('legacy-user', 'legacy@example.com', 'admin', 'hash', '2026-05-16T00:00:00+00:00');

            INSERT INTO auth_tokens (token, user_id, created_at)
            VALUES ('legacy-token', 'legacy-user', '2026-05-16T00:00:00+00:00');
            """
        )

    database = Database(path)
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT session_id, token_hash, expires_at
            FROM auth_tokens
            """
        ).fetchone()

    assert row["session_id"]
    assert row["token_hash"] != "legacy-token"
    assert row["expires_at"]


def test_database_creates_user_profiles_table(tmp_path) -> None:
    database = Database(tmp_path / "profiles.db")
    with database.connect() as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'user_profiles'
            """
        ).fetchone()

    assert table["name"] == "user_profiles"


def test_database_creates_playbook_tables(tmp_path) -> None:
    database = Database(tmp_path / "playbooks.db")
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('task_profiles', 'playbooks')
            ORDER BY name
            """
        ).fetchall()

    assert [row["name"] for row in rows] == ["playbooks", "task_profiles"]


def test_database_creates_investigation_profiles_table_with_checklist(tmp_path) -> None:
    database = Database(tmp_path / "investigation_profiles.db")
    with database.connect() as connection:
        columns = connection.execute("PRAGMA table_info(investigation_profiles)").fetchall()

    column_names = {column["name"] for column in columns}
    assert "recommended_checks" in column_names


def test_database_creates_investigation_case_tables(tmp_path) -> None:
    database = Database(tmp_path / "investigation_cases.db")
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                'investigation_cases',
                'investigation_case_checklist_items',
                'investigation_case_notes',
                'investigation_case_events',
                'investigation_case_evidence',
                'investigation_case_hypotheses'
              )
            ORDER BY name
            """
        ).fetchall()

    assert [row["name"] for row in rows] == [
        "investigation_case_checklist_items",
        "investigation_case_events",
        "investigation_case_evidence",
        "investigation_case_hypotheses",
        "investigation_case_notes",
        "investigation_cases",
    ]


def test_database_migrates_legacy_investigation_profiles_with_checklist(tmp_path) -> None:
    path = tmp_path / "legacy_investigation_profiles.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE investigation_profiles (
                profile_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                trigger_phrases TEXT,
                default_goal TEXT,
                include_recent_github INTEGER NOT NULL DEFAULT 0,
                drive_query TEXT,
                jira_jql TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    database = Database(path)
    with database.connect() as connection:
        columns = connection.execute("PRAGMA table_info(investigation_profiles)").fetchall()

    column_names = {column["name"] for column in columns}
    assert "recommended_checks" in column_names


def test_database_creates_watchlists_table(tmp_path) -> None:
    database = Database(tmp_path / "watchlists.db")
    with database.connect() as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'watchlists'
            """
        ).fetchone()

    assert table["name"] == "watchlists"


def test_database_creates_automation_tables(tmp_path) -> None:
    database = Database(tmp_path / "automations.db")
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('automations', 'automation_runs')
            ORDER BY name
            """
        ).fetchall()

    assert [row["name"] for row in rows] == ["automation_runs", "automations"]


def test_database_creates_inbox_table(tmp_path) -> None:
    database = Database(tmp_path / "inbox.db")
    with database.connect() as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'inbox_items'
            """
        ).fetchone()

    assert table["name"] == "inbox_items"
