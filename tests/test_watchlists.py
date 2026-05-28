from datetime import UTC, datetime

from jarvis_cyber.core.schemas import CVERecord, WatchlistCreateRequest
from jarvis_cyber.services.briefings import BriefingService
from jarvis_cyber.storage.database import Database
from jarvis_cyber.watchlists.store import SQLiteWatchlistStore


def test_daily_brief_uses_watchlists(monkeypatch, tmp_path) -> None:
    watchlist_database = Database(tmp_path / "watchlists.db")
    monkeypatch.setattr("jarvis_cyber.watchlists.store.database", watchlist_database)
    monkeypatch.setattr("jarvis_cyber.services.briefings.watchlist_store", SQLiteWatchlistStore())
    monkeypatch.setattr(
        "jarvis_cyber.services.briefings.nvd_client.search_recent_cves",
        lambda **kwargs: [CVERecord(cve_id="CVE-2026-0003", description="Microsoft issue.")],
    )

    SQLiteWatchlistStore().add(
        "analyst-1",
        WatchlistCreateRequest(title="Microsoft 365", keywords="Microsoft Outlook"),
    )

    brief = BriefingService().daily_brief(
        "analyst-1",
        days=1,
        per_watchlist_limit=5,
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )

    assert len(brief.items) == 1
    assert brief.items[0].watchlist.title == "Microsoft 365"
    assert brief.items[0].records[0].cve_id == "CVE-2026-0003"
