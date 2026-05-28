from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from jarvis_cyber.core.schemas import Watchlist, WatchlistCreateRequest
from jarvis_cyber.storage.database import database


class SQLiteWatchlistStore:
    """Persist user-specific vulnerability watchlists."""

    def add(self, user_id: str, payload: WatchlistCreateRequest) -> Watchlist:
        now = datetime.now(UTC).isoformat()
        watchlist = Watchlist(
            watchlist_id=str(uuid4()),
            title=payload.title,
            keywords=payload.keywords,
            exact_match=payload.exact_match,
            kev_only=payload.kev_only,
            created_at=now,
            updated_at=now,
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO watchlists
                (watchlist_id, user_id, title, keywords, exact_match, kev_only, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    watchlist.watchlist_id,
                    user_id,
                    watchlist.title,
                    watchlist.keywords,
                    int(watchlist.exact_match),
                    int(watchlist.kev_only),
                    watchlist.created_at,
                    watchlist.updated_at,
                ),
            )
        return watchlist

    def list(self, user_id: str) -> list[Watchlist]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT watchlist_id, title, keywords, exact_match, kev_only, created_at, updated_at
                FROM watchlists
                WHERE user_id = ?
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [
            Watchlist(
                watchlist_id=row["watchlist_id"],
                title=row["title"],
                keywords=row["keywords"],
                exact_match=bool(row["exact_match"]),
                kev_only=bool(row["kev_only"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def delete(self, user_id: str, watchlist_id: str) -> bool:
        with database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM watchlists
                WHERE user_id = ? AND watchlist_id = ?
                """,
                (user_id, watchlist_id),
            )
        return cursor.rowcount > 0


watchlist_store = SQLiteWatchlistStore()
