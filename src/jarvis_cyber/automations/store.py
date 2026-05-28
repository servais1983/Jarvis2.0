from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from jarvis_cyber.core.schemas import (
    Automation,
    AutomationCreateRequest,
    AutomationRun,
    ConnectorDigestAutomationPayload,
    DailyBriefAutomationPayload,
)
from jarvis_cyber.storage.database import database


class SQLiteAutomationStore:
    """Persist automation definitions and execution history."""

    def add(self, user_id: str, payload: AutomationCreateRequest) -> Automation:
        now = datetime.now(UTC)
        next_run_at = self._next_daily_run(
            schedule_time=payload.schedule_time,
            timezone=payload.timezone,
            after=now,
        )
        automation = Automation(
            automation_id=str(uuid4()),
            name=payload.name,
            automation_type=payload.automation_type,
            schedule_kind=payload.schedule_kind,
            schedule_time=payload.schedule_time,
            timezone=payload.timezone,
            payload=payload.payload,
            enabled=payload.enabled,
            requires_approval=payload.requires_approval,
            next_run_at=next_run_at.isoformat(),
            last_run_at=None,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO automations
                (automation_id, user_id, name, automation_type, schedule_kind, schedule_time,
                 timezone, payload_json, enabled, requires_approval, next_run_at, last_run_at,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    automation.automation_id,
                    user_id,
                    automation.name,
                    automation.automation_type,
                    automation.schedule_kind,
                    automation.schedule_time,
                    automation.timezone,
                    automation.payload.model_dump_json(),
                    int(automation.enabled),
                    int(automation.requires_approval),
                    automation.next_run_at,
                    automation.last_run_at,
                    automation.created_at,
                    automation.updated_at,
                ),
            )
        return automation

    def list(self, user_id: str) -> list[Automation]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT automation_id, name, automation_type, schedule_kind, schedule_time, timezone,
                       payload_json, enabled, requires_approval, next_run_at, last_run_at,
                       created_at, updated_at
                FROM automations
                WHERE user_id = ?
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [self._automation_from_row(row) for row in rows]

    def get(self, user_id: str, automation_id: str) -> Automation | None:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT automation_id, name, automation_type, schedule_kind, schedule_time, timezone,
                       payload_json, enabled, requires_approval, next_run_at, last_run_at,
                       created_at, updated_at
                FROM automations
                WHERE user_id = ? AND automation_id = ?
                """,
                (user_id, automation_id),
            ).fetchone()
        return self._automation_from_row(row) if row is not None else None

    def delete(self, user_id: str, automation_id: str) -> bool:
        with database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM automations
                WHERE user_id = ? AND automation_id = ?
                """,
                (user_id, automation_id),
            )
        return cursor.rowcount > 0

    def due(self, user_id: str, now: datetime) -> list[Automation]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT automation_id, name, automation_type, schedule_kind, schedule_time, timezone,
                       payload_json, enabled, requires_approval, next_run_at, last_run_at,
                       created_at, updated_at
                FROM automations
                WHERE user_id = ?
                  AND enabled = 1
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (user_id, now.isoformat()),
            ).fetchall()
        return [self._automation_from_row(row) for row in rows]

    def record_run(
        self,
        user_id: str,
        automation_id: str,
        *,
        status: str,
        started_at: datetime,
        finished_at: datetime | None,
        output_json: str | None,
        error_message: str | None,
    ) -> AutomationRun:
        run = AutomationRun(
            run_id=str(uuid4()),
            automation_id=automation_id,
            status=status,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat() if finished_at else None,
            output=json.loads(output_json) if output_json else None,
            error_message=error_message,
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO automation_runs
                (run_id, automation_id, user_id, status, started_at, finished_at,
                 output_json, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    automation_id,
                    user_id,
                    status,
                    run.started_at,
                    run.finished_at,
                    output_json,
                    error_message,
                ),
            )
        return run

    def list_runs(self, user_id: str, automation_id: str) -> list[AutomationRun]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, automation_id, status, started_at, finished_at, output_json,
                       error_message
                FROM automation_runs
                WHERE user_id = ? AND automation_id = ?
                ORDER BY started_at DESC
                """,
                (user_id, automation_id),
            ).fetchall()
        return [
            AutomationRun(
                run_id=row["run_id"],
                automation_id=row["automation_id"],
                status=row["status"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                output=json.loads(row["output_json"]) if row["output_json"] else None,
                error_message=row["error_message"],
            )
            for row in rows
        ]

    def mark_scheduled(self, user_id: str, automation: Automation, *, ran_at: datetime) -> Automation:
        next_run_at = self._next_daily_run(
            schedule_time=automation.schedule_time,
            timezone=automation.timezone,
            after=ran_at,
        )
        updated_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                UPDATE automations
                SET last_run_at = ?, next_run_at = ?, updated_at = ?
                WHERE user_id = ? AND automation_id = ?
                """,
                (
                    ran_at.isoformat(),
                    next_run_at.isoformat(),
                    updated_at,
                    user_id,
                    automation.automation_id,
                ),
            )
        refreshed = self.get(user_id, automation.automation_id)
        assert refreshed is not None
        return refreshed

    @staticmethod
    def _automation_from_row(row) -> Automation:
        payload_data = json.loads(row["payload_json"])
        payload = (
            DailyBriefAutomationPayload(**payload_data)
            if row["automation_type"] == "daily_brief"
            else ConnectorDigestAutomationPayload(**payload_data)
        )
        return Automation(
            automation_id=row["automation_id"],
            name=row["name"],
            automation_type=row["automation_type"],
            schedule_kind=row["schedule_kind"],
            schedule_time=row["schedule_time"],
            timezone=row["timezone"],
            payload=payload,
            enabled=bool(row["enabled"]),
            requires_approval=bool(row["requires_approval"]),
            next_run_at=row["next_run_at"],
            last_run_at=row["last_run_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _next_daily_run(*, schedule_time: str, timezone: str, after: datetime) -> datetime:
        local_zone = ZoneInfo(timezone)
        local_after = after.astimezone(local_zone)
        hour, minute = (int(part) for part in schedule_time.split(":"))
        candidate = local_after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_after:
            candidate += timedelta(days=1)
        return candidate.astimezone(UTC)


automation_store = SQLiteAutomationStore()
