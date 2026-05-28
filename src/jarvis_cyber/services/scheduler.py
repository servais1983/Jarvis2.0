from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from jarvis_cyber.auth import LOCAL_DEV_USER_ID, auth_service
from jarvis_cyber.config import settings
from jarvis_cyber.services.automations import automation_service


logger = logging.getLogger(__name__)


class AutomationScheduler:
    """Minimal background scheduler for due automations."""

    def __init__(self, interval_seconds: int = settings.scheduler_interval_seconds) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running or not settings.scheduler_enabled:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="jarvis-automation-scheduler")
        logger.info("automation_scheduler_started interval_seconds=%s", self.interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("automation_scheduler_stopped")

    async def run_once(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        user_ids = auth_service.list_user_ids()
        if not settings.auth_required and LOCAL_DEV_USER_ID not in user_ids:
            user_ids.append(LOCAL_DEV_USER_ID)
        if not user_ids:
            user_ids = [LOCAL_DEV_USER_ID]
        runs = 0
        for user_id in user_ids:
            try:
                runs += len(await asyncio.to_thread(automation_service.run_due, user_id, now=current))
            except Exception:
                logger.exception("automation_scheduler_user_failed user_id=%s", user_id)
        return runs

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                runs = await self.run_once()
                logger.info("automation_scheduler_tick runs=%s", runs)
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.interval_seconds,
                    )
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise


automation_scheduler = AutomationScheduler()
