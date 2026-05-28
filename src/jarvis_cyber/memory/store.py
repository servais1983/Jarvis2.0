from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jarvis_cyber.config import settings
from jarvis_cyber.storage.database import database


@dataclass(frozen=True)
class MemoryTurn:
    session_id: str
    role: str
    content: str
    created_at: str


class SQLiteMemoryStore:
    """Durable local conversation store."""

    def __init__(self, data_dir: str | Path = settings.data_dir) -> None:
        self.legacy_path = Path(data_dir) / "conversations.jsonl"
        self._migrate_legacy_if_needed()

    def append(self, user_id: str, session_id: str, role: str, content: str) -> None:
        payload = MemoryTurn(
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.now(UTC).isoformat(),
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_turns (user_id, session_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, payload.session_id, payload.role, payload.content, payload.created_at),
            )

    def recent(self, user_id: str, session_id: str, limit: int) -> list[MemoryTurn]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, role, content, created_at
                FROM conversation_turns
                WHERE user_id = ? AND session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, session_id, limit),
            ).fetchall()
        return [MemoryTurn(**dict(row)) for row in reversed(rows)]

    def _migrate_legacy_if_needed(self) -> None:
        with database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0]
        if count > 0 or not self.legacy_path.exists():
            return

        with self.legacy_path.open("r", encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]

        with database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO conversation_turns (user_id, session_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        "local-dev",
                        row["session_id"],
                        row["role"],
                        row["content"],
                        row["created_at"],
                    )
                    for row in rows
                ],
            )


memory_store = SQLiteMemoryStore()
