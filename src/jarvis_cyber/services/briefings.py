from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis_cyber.core.schemas import DailyBriefResponse, DailyBriefWatchlistResult
from jarvis_cyber.integrations.nvd import nvd_client
from jarvis_cyber.watchlists.store import watchlist_store


class BriefingService:
    """Build recurring analyst briefings from persistent watchlists."""

    def daily_brief(
        self,
        user_id: str,
        *,
        days: int = 1,
        per_watchlist_limit: int = 5,
        now: datetime | None = None,
    ) -> DailyBriefResponse:
        window_end = now or datetime.now(UTC)
        window_start = window_end - timedelta(days=days)
        items = [
            DailyBriefWatchlistResult(
                watchlist=watchlist,
                records=nvd_client.search_recent_cves(
                    keywords=watchlist.keywords,
                    published_from=window_start,
                    published_to=window_end,
                    exact_match=watchlist.exact_match,
                    kev_only=watchlist.kev_only,
                    limit=per_watchlist_limit,
                ),
            )
            for watchlist in watchlist_store.list(user_id)
        ]
        return DailyBriefResponse(
            generated_at=window_end.isoformat(),
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            items=items,
        )


briefing_service = BriefingService()
