from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from jarvis_cyber.core.schemas import InboxItem, InboxMarkReadResponse
from jarvis_cyber.storage.database import database


class SQLiteInboxStore:
    """Persist user-visible messages produced by Jarvis."""

    def add(
        self,
        user_id: str,
        *,
        item_type: str,
        title: str,
        body: str,
        related_run_id: str | None = None,
        payload_json: str | None = None,
    ) -> InboxItem:
        created_at = datetime.now(UTC).isoformat()
        item = InboxItem(
            item_id=str(uuid4()),
            item_type=item_type,
            title=title,
            body=body,
            related_run_id=related_run_id,
            payload=json.loads(payload_json) if payload_json else None,
            read_at=None,
            created_at=created_at,
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO inbox_items
                (item_id, user_id, item_type, title, body, related_run_id, payload_json,
                 read_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.item_id,
                    user_id,
                    item.item_type,
                    item.title,
                    item.body,
                    item.related_run_id,
                    payload_json,
                    item.read_at,
                    item.created_at,
                ),
            )
        return item

    def list(self, user_id: str, *, unread_only: bool = False) -> list[InboxItem]:
        where_clause = "AND read_at IS NULL" if unread_only else ""
        with database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT item_id, item_type, title, body, related_run_id, payload_json,
                       read_at, created_at
                FROM inbox_items
                WHERE user_id = ?
                {where_clause}
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def summary_context(self, user_id: str, *, limit: int = 3) -> str:
        unread_items = self.list(user_id, unread_only=True)[:limit]
        if not unread_items:
            return "Aucun élément non lu dans l'inbox."
        return "\n".join(
            f"- {item.title} ({item.item_type})"
            for item in unread_items
        )

    def mark_read(self, user_id: str, item_id: str) -> InboxMarkReadResponse | None:
        read_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE inbox_items
                SET read_at = COALESCE(read_at, ?)
                WHERE user_id = ? AND item_id = ?
                """,
                (read_at, user_id, item_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT item_id, read_at
                FROM inbox_items
                WHERE user_id = ? AND item_id = ?
                """,
                (user_id, item_id),
            ).fetchone()
        return InboxMarkReadResponse(item_id=row["item_id"], read_at=row["read_at"])

    @staticmethod
    def _item_from_row(row) -> InboxItem:
        return InboxItem(
            item_id=row["item_id"],
            item_type=row["item_type"],
            title=row["title"],
            body=row["body"],
            related_run_id=row["related_run_id"],
            payload=json.loads(row["payload_json"]) if row["payload_json"] else None,
            read_at=row["read_at"],
            created_at=row["created_at"],
        )


inbox_store = SQLiteInboxStore()
