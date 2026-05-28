from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from jarvis_cyber.core.schemas import (
    InvestigationCase,
    InvestigationCaseCreateRequest,
    InvestigationCaseDetail,
    InvestigationCaseEvent,
    InvestigationCaseEventCreateRequest,
    InvestigationCaseEvidence,
    InvestigationCaseEvidenceCreateRequest,
    InvestigationCaseHypothesis,
    InvestigationCaseHypothesisCreateRequest,
    InvestigationCaseHypothesisUpdateRequest,
    InvestigationCaseNote,
    InvestigationCaseSummary,
    InvestigationChecklistItem,
    InvestigationChecklistItemUpdateRequest,
)
from jarvis_cyber.investigation_profiles.store import investigation_profile_store
from jarvis_cyber.storage.database import database


class SQLiteInvestigationCaseStore:
    """Persist live investigation dossiers with checklist progress and notes."""

    def create(self, user_id: str, payload: InvestigationCaseCreateRequest) -> InvestigationCaseDetail:
        now = datetime.now(UTC).isoformat()
        case = InvestigationCase(
            case_id=str(uuid4()),
            title=payload.title,
            raw_alert=payload.raw_alert,
            environment_context=payload.environment_context,
            goal=payload.goal,
            investigation_profile_id=payload.investigation_profile_id,
            status="open",
            created_at=now,
            updated_at=now,
        )
        profile = (
            investigation_profile_store.get(user_id, payload.investigation_profile_id)
            if payload.investigation_profile_id
            else None
        )
        checklist_titles = self._checklist_titles(profile.recommended_checks if profile else None)
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO investigation_cases
                (case_id, user_id, title, raw_alert, environment_context, goal,
                 investigation_profile_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case.case_id,
                    user_id,
                    case.title,
                    case.raw_alert,
                    case.environment_context,
                    case.goal,
                    case.investigation_profile_id,
                    case.status,
                    case.created_at,
                    case.updated_at,
                ),
            )
            for position, title in enumerate(checklist_titles, start=1):
                connection.execute(
                    """
                    INSERT INTO investigation_case_checklist_items
                    (item_id, case_id, title, status, notes, position, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid4()), case.case_id, title, "todo", None, position, now, now),
                )
        return self.get_detail(user_id, case.case_id)

    def list(self, user_id: str) -> list[InvestigationCase]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT case_id, title, raw_alert, environment_context, goal,
                       investigation_profile_id, status, created_at, updated_at
                FROM investigation_cases
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._case_from_row(row) for row in rows]

    def get_detail(self, user_id: str, case_id: str) -> InvestigationCaseDetail | None:
        with database.connect() as connection:
            case_row = connection.execute(
                """
                SELECT case_id, title, raw_alert, environment_context, goal,
                       investigation_profile_id, status, created_at, updated_at
                FROM investigation_cases
                WHERE user_id = ? AND case_id = ?
                """,
                (user_id, case_id),
            ).fetchone()
            if case_row is None:
                return None
            item_rows = connection.execute(
                """
                SELECT item_id, title, status, notes, position, created_at, updated_at
                FROM investigation_case_checklist_items
                WHERE case_id = ?
                ORDER BY position ASC
                """,
                (case_id,),
            ).fetchall()
            note_rows = connection.execute(
                """
                SELECT note_id, body, created_at
                FROM investigation_case_notes
                WHERE case_id = ?
                ORDER BY created_at DESC
                """,
                (case_id,),
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT event_id, occurred_at, title, description, created_at
                FROM investigation_case_events
                WHERE case_id = ?
                ORDER BY occurred_at ASC, created_at ASC
                """,
                (case_id,),
            ).fetchall()
            evidence_rows = connection.execute(
                """
                SELECT evidence_id, title, description, source, created_at
                FROM investigation_case_evidence
                WHERE case_id = ?
                ORDER BY created_at DESC
                """,
                (case_id,),
            ).fetchall()
            hypothesis_rows = connection.execute(
                """
                SELECT hypothesis_id, statement, status, rationale, created_at, updated_at
                FROM investigation_case_hypotheses
                WHERE case_id = ?
                ORDER BY updated_at DESC
                """,
                (case_id,),
            ).fetchall()
        case = self._case_from_row(case_row)
        items = [self._item_from_row(row) for row in item_rows]
        notes = [InvestigationCaseNote(**dict(row)) for row in note_rows]
        events = [InvestigationCaseEvent(**dict(row)) for row in event_rows]
        evidence = [InvestigationCaseEvidence(**dict(row)) for row in evidence_rows]
        hypotheses = [InvestigationCaseHypothesis(**dict(row)) for row in hypothesis_rows]
        return InvestigationCaseDetail(
            case=case,
            checklist_items=items,
            notes=notes,
            events=events,
            evidence=evidence,
            hypotheses=hypotheses,
            summary=self._summary(items, notes, hypotheses),
        )

    def update_status(self, user_id: str, case_id: str, status: str) -> InvestigationCase | None:
        updated_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE investigation_cases
                SET status = ?, updated_at = ?
                WHERE user_id = ? AND case_id = ?
                """,
                (status, updated_at, user_id, case_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT case_id, title, raw_alert, environment_context, goal,
                       investigation_profile_id, status, created_at, updated_at
                FROM investigation_cases
                WHERE user_id = ? AND case_id = ?
                """,
                (user_id, case_id),
            ).fetchone()
        return self._case_from_row(row)

    def update_checklist_item(
        self,
        user_id: str,
        case_id: str,
        item_id: str,
        payload: InvestigationChecklistItemUpdateRequest,
    ) -> InvestigationCaseDetail | None:
        if self.get_detail(user_id, case_id) is None:
            return None
        updated_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE investigation_case_checklist_items
                SET status = ?, notes = ?, updated_at = ?
                WHERE case_id = ? AND item_id = ?
                """,
                (payload.status, payload.notes, updated_at, case_id, item_id),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                """
                UPDATE investigation_cases
                SET updated_at = ?
                WHERE case_id = ?
                """,
                (updated_at, case_id),
            )
        return self.get_detail(user_id, case_id)

    def add_note(self, user_id: str, case_id: str, body: str) -> InvestigationCaseDetail | None:
        if self.get_detail(user_id, case_id) is None:
            return None
        created_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO investigation_case_notes
                (note_id, case_id, body, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (str(uuid4()), case_id, body, created_at),
            )
            connection.execute(
                """
                UPDATE investigation_cases
                SET updated_at = ?
                WHERE case_id = ?
                """,
                (created_at, case_id),
            )
        return self.get_detail(user_id, case_id)

    def add_event(
        self,
        user_id: str,
        case_id: str,
        payload: InvestigationCaseEventCreateRequest,
    ) -> InvestigationCaseDetail | None:
        if self.get_detail(user_id, case_id) is None:
            return None
        created_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO investigation_case_events
                (event_id, case_id, occurred_at, title, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), case_id, payload.occurred_at, payload.title, payload.description, created_at),
            )
            connection.execute(
                "UPDATE investigation_cases SET updated_at = ? WHERE case_id = ?",
                (created_at, case_id),
            )
        return self.get_detail(user_id, case_id)

    def add_evidence(
        self,
        user_id: str,
        case_id: str,
        payload: InvestigationCaseEvidenceCreateRequest,
    ) -> InvestigationCaseDetail | None:
        if self.get_detail(user_id, case_id) is None:
            return None
        created_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO investigation_case_evidence
                (evidence_id, case_id, title, description, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), case_id, payload.title, payload.description, payload.source, created_at),
            )
            connection.execute(
                "UPDATE investigation_cases SET updated_at = ? WHERE case_id = ?",
                (created_at, case_id),
            )
        return self.get_detail(user_id, case_id)

    def add_hypothesis(
        self,
        user_id: str,
        case_id: str,
        payload: InvestigationCaseHypothesisCreateRequest,
    ) -> InvestigationCaseDetail | None:
        if self.get_detail(user_id, case_id) is None:
            return None
        now = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO investigation_case_hypotheses
                (hypothesis_id, case_id, statement, status, rationale, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), case_id, payload.statement, "open", payload.rationale, now, now),
            )
            connection.execute(
                "UPDATE investigation_cases SET updated_at = ? WHERE case_id = ?",
                (now, case_id),
            )
        return self.get_detail(user_id, case_id)

    def update_hypothesis(
        self,
        user_id: str,
        case_id: str,
        hypothesis_id: str,
        payload: InvestigationCaseHypothesisUpdateRequest,
    ) -> InvestigationCaseDetail | None:
        if self.get_detail(user_id, case_id) is None:
            return None
        updated_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE investigation_case_hypotheses
                SET status = ?, rationale = ?, updated_at = ?
                WHERE case_id = ? AND hypothesis_id = ?
                """,
                (payload.status, payload.rationale, updated_at, case_id, hypothesis_id),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                "UPDATE investigation_cases SET updated_at = ? WHERE case_id = ?",
                (updated_at, case_id),
            )
        return self.get_detail(user_id, case_id)

    def delete(self, user_id: str, case_id: str) -> bool:
        with database.connect() as connection:
            existing = connection.execute(
                """
                SELECT case_id
                FROM investigation_cases
                WHERE user_id = ? AND case_id = ?
                """,
                (user_id, case_id),
            ).fetchone()
            if existing is None:
                return False
            connection.execute(
                "DELETE FROM investigation_case_notes WHERE case_id = ?",
                (case_id,),
            )
            connection.execute(
                "DELETE FROM investigation_case_events WHERE case_id = ?",
                (case_id,),
            )
            connection.execute(
                "DELETE FROM investigation_case_evidence WHERE case_id = ?",
                (case_id,),
            )
            connection.execute(
                "DELETE FROM investigation_case_hypotheses WHERE case_id = ?",
                (case_id,),
            )
            connection.execute(
                "DELETE FROM investigation_case_checklist_items WHERE case_id = ?",
                (case_id,),
            )
            connection.execute(
                "DELETE FROM investigation_cases WHERE user_id = ? AND case_id = ?",
                (user_id, case_id),
            )
        return True

    @staticmethod
    def _checklist_titles(recommended_checks: str | None) -> list[str]:
        if not recommended_checks:
            return []
        return [line.strip(" -") for line in recommended_checks.splitlines() if line.strip(" -")]

    @staticmethod
    def _summary(
        items: list[InvestigationChecklistItem],
        notes: list[InvestigationCaseNote],
        hypotheses: list[InvestigationCaseHypothesis],
    ) -> InvestigationCaseSummary:
        total_checks = len(items)
        done_checks = sum(item.status == "done" for item in items)
        blocked_checks = sum(item.status == "blocked" for item in items)
        todo_checks = sum(item.status == "todo" for item in items)
        completion_ratio = round(done_checks / total_checks, 4) if total_checks else 0.0
        next_open_checks = [item.title for item in items if item.status != "done"][:3]
        latest_note = notes[0].body if notes else None
        return InvestigationCaseSummary(
            total_checks=total_checks,
            done_checks=done_checks,
            blocked_checks=blocked_checks,
            todo_checks=todo_checks,
            completion_ratio=completion_ratio,
            next_open_checks=next_open_checks,
            latest_note=latest_note,
            open_hypotheses=sum(item.status == "open" for item in hypotheses),
            supported_hypotheses=sum(item.status == "supported" for item in hypotheses),
            rejected_hypotheses=sum(item.status == "rejected" for item in hypotheses),
        )

    @staticmethod
    def _case_from_row(row) -> InvestigationCase:
        return InvestigationCase(**dict(row))

    @staticmethod
    def _item_from_row(row) -> InvestigationChecklistItem:
        return InvestigationChecklistItem(**dict(row))


investigation_case_store = SQLiteInvestigationCaseStore()
