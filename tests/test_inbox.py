from jarvis_cyber.inbox.store import SQLiteInboxStore
from jarvis_cyber.storage.database import Database


def test_inbox_round_trip(monkeypatch, tmp_path) -> None:
    inbox_database = Database(tmp_path / "inbox.db")
    monkeypatch.setattr("jarvis_cyber.inbox.store.database", inbox_database)
    store = SQLiteInboxStore()

    item = store.add(
        "analyst-1",
        item_type="automation_succeeded",
        title="Brief prêt",
        body="1 watchlist traitée.",
    )
    listed = store.list("analyst-1")
    marked = store.mark_read("analyst-1", item.item_id)

    assert listed[0].title == "Brief prêt"
    assert marked is not None
    assert marked.item_id == item.item_id
    assert store.list("analyst-1", unread_only=True) == []


def test_inbox_summary_context(monkeypatch, tmp_path) -> None:
    inbox_database = Database(tmp_path / "inbox.db")
    monkeypatch.setattr("jarvis_cyber.inbox.store.database", inbox_database)
    store = SQLiteInboxStore()
    store.add(
        "analyst-1",
        item_type="automation_succeeded",
        title="Brief du matin est prêt",
        body="1 watchlist traitée.",
    )

    summary = store.summary_context("analyst-1")

    assert "Brief du matin est prêt" in summary
