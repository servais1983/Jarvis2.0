from datetime import UTC, datetime

from jarvis_cyber.automations.store import SQLiteAutomationStore
from jarvis_cyber.core.schemas import (
    AutomationCreateRequest,
    ConnectorDigestAutomationPayload,
    ConnectorDigestResponse,
    DailyBriefAutomationPayload,
    DailyBriefResponse,
)
from jarvis_cyber.services.automations import AutomationService
from jarvis_cyber.storage.database import Database
from jarvis_cyber.inbox.store import SQLiteInboxStore


def test_automation_store_and_manual_run(monkeypatch, tmp_path) -> None:
    automation_database = Database(tmp_path / "automations.db")
    monkeypatch.setattr("jarvis_cyber.automations.store.database", automation_database)
    monkeypatch.setattr(
        "jarvis_cyber.services.automations.automation_store",
        SQLiteAutomationStore(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.inbox.store.database",
        automation_database,
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.automations.inbox_store",
        SQLiteInboxStore(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.automations.briefing_service.daily_brief",
        lambda user_id, days, per_watchlist_limit: DailyBriefResponse(
            generated_at="2026-05-16T00:00:00+00:00",
            window_start="2026-05-15T00:00:00+00:00",
            window_end="2026-05-16T00:00:00+00:00",
            items=[],
        ),
    )

    store = SQLiteAutomationStore()
    automation = store.add(
        "analyst-1",
        AutomationCreateRequest(
            name="Brief du matin",
            schedule_time="08:00",
            timezone="Europe/Brussels",
            payload=DailyBriefAutomationPayload(days=1, per_watchlist_limit=5),
        ),
    )
    run = AutomationService().run(
        "analyst-1",
        automation,
        now=datetime(2026, 5, 16, 6, 0, tzinfo=UTC),
    )
    runs = store.list_runs("analyst-1", automation.automation_id)

    assert run.status == "succeeded"
    assert runs[0].status == "succeeded"
    assert store.get("analyst-1", automation.automation_id).last_run_at is not None
    assert SQLiteInboxStore().list("analyst-1")[0].item_type == "automation_succeeded"


def test_automation_requires_approval(monkeypatch, tmp_path) -> None:
    automation_database = Database(tmp_path / "automations.db")
    monkeypatch.setattr("jarvis_cyber.automations.store.database", automation_database)
    monkeypatch.setattr(
        "jarvis_cyber.services.automations.automation_store",
        SQLiteAutomationStore(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.inbox.store.database",
        automation_database,
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.automations.inbox_store",
        SQLiteInboxStore(),
    )
    store = SQLiteAutomationStore()
    automation = store.add(
        "analyst-1",
        AutomationCreateRequest(
            name="Brief sensible",
            schedule_time="08:00",
            timezone="Europe/Brussels",
            requires_approval=True,
        ),
    )

    run = AutomationService().run("analyst-1", automation)

    assert run.status == "approval_required"
    assert SQLiteInboxStore().list("analyst-1")[0].item_type == "approval_required"


def test_connector_digest_automation(monkeypatch, tmp_path) -> None:
    automation_database = Database(tmp_path / "automations.db")
    monkeypatch.setattr("jarvis_cyber.automations.store.database", automation_database)
    monkeypatch.setattr(
        "jarvis_cyber.services.automations.automation_store",
        SQLiteAutomationStore(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.inbox.store.database",
        automation_database,
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.automations.inbox_store",
        SQLiteInboxStore(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.automations.connector_digest_service.build",
        lambda payload: ConnectorDigestResponse(generated_at="now"),
    )
    store = SQLiteAutomationStore()
    automation = store.add(
        "analyst-1",
        AutomationCreateRequest(
            name="Digest connecteurs",
            automation_type="connector_digest",
            schedule_time="08:00",
            timezone="Europe/Brussels",
            payload=ConnectorDigestAutomationPayload(),
        ),
    )

    run = AutomationService().run("analyst-1", automation)

    assert run.status == "succeeded"
    assert "Digest connecteurs prêt" in SQLiteInboxStore().list("analyst-1")[0].body
