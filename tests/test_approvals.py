from jarvis_cyber.approvals.store import SQLiteToolApprovalStore
from jarvis_cyber.storage.database import Database


def test_tool_approval_store_round_trip(monkeypatch, tmp_path) -> None:
    approval_database = Database(tmp_path / "approvals.db")
    monkeypatch.setattr("jarvis_cyber.approvals.store.database", approval_database)
    store = SQLiteToolApprovalStore()

    approval = store.create(
        "analyst-1",
        tool_name="create_watchlist",
        arguments={"title": "Microsoft 365", "keywords": "Microsoft Outlook"},
        reason="sensitive_tool",
        source="text_chat",
    )
    listed = store.list("analyst-1", status="pending")
    executed = store.mark_executed(
        "analyst-1",
        approval.approval_id,
        result={"watchlist": {"title": "Microsoft 365"}},
    )

    assert listed[0].tool_name == "create_watchlist"
    assert executed is not None
    assert executed.status == "executed"
    assert executed.result == {"watchlist": {"title": "Microsoft 365"}}
