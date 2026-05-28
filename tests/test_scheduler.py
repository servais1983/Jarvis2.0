from datetime import UTC, datetime

import pytest

from jarvis_cyber.services.scheduler import AutomationScheduler


@pytest.mark.anyio
async def test_scheduler_runs_due_automations(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.scheduler.auth_service.list_user_ids",
        lambda: ["analyst-1", "analyst-2"],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.scheduler.automation_service.run_due",
        lambda user_id, now: [object()] if user_id == "analyst-1" else [],
    )
    scheduler = AutomationScheduler(interval_seconds=1)

    runs = await scheduler.run_once(now=datetime(2026, 5, 16, tzinfo=UTC))

    assert runs == 1


@pytest.mark.anyio
async def test_scheduler_includes_local_dev_when_auth_is_disabled(monkeypatch) -> None:
    seen_user_ids: list[str] = []
    monkeypatch.setattr("jarvis_cyber.services.scheduler.settings.auth_required", False)
    monkeypatch.setattr(
        "jarvis_cyber.services.scheduler.auth_service.list_user_ids",
        lambda: ["analyst-1"],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.scheduler.automation_service.run_due",
        lambda user_id, now: seen_user_ids.append(user_id) or [],
    )
    scheduler = AutomationScheduler(interval_seconds=1)

    await scheduler.run_once(now=datetime(2026, 5, 16, tzinfo=UTC))

    assert seen_user_ids == ["analyst-1", "local-dev"]


@pytest.mark.anyio
async def test_scheduler_starts_and_stops(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.services.scheduler.settings.scheduler_enabled", True)
    monkeypatch.setattr(
        "jarvis_cyber.services.scheduler.auth_service.list_user_ids",
        lambda: [],
    )
    scheduler = AutomationScheduler(interval_seconds=60)

    await scheduler.start()
    assert scheduler.running is True

    await scheduler.stop()
    assert scheduler.running is False
