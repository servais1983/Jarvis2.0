from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from jarvis_cyber.core.schemas import (
    Playbook,
    PlaybookCreateRequest,
    PlaybookSearchResult,
    TaskProfile,
    TaskProfileCreateRequest,
)
from jarvis_cyber.storage.database import database


class SQLitePlaybookStore:
    """Persist reusable task profiles and user playbooks."""

    def add_task_profile(self, user_id: str, payload: TaskProfileCreateRequest) -> TaskProfile:
        now = datetime.now(UTC).isoformat()
        profile = TaskProfile(
            profile_id=str(uuid4()),
            name=payload.name,
            description=payload.description,
            output_format=payload.output_format,
            review_checklist=payload.review_checklist,
            created_at=now,
            updated_at=now,
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO task_profiles
                (profile_id, user_id, name, description, output_format, review_checklist,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    user_id,
                    profile.name,
                    profile.description,
                    profile.output_format,
                    profile.review_checklist,
                    profile.created_at,
                    profile.updated_at,
                ),
            )
        return profile

    def list_task_profiles(self, user_id: str) -> list[TaskProfile]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT profile_id, name, description, output_format, review_checklist,
                       created_at, updated_at
                FROM task_profiles
                WHERE user_id = ?
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [TaskProfile(**dict(row)) for row in rows]

    def get_task_profile(self, user_id: str, profile_id: str) -> TaskProfile | None:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT profile_id, name, description, output_format, review_checklist,
                       created_at, updated_at
                FROM task_profiles
                WHERE user_id = ? AND profile_id = ?
                """,
                (user_id, profile_id),
            ).fetchone()
        return TaskProfile(**dict(row)) if row is not None else None

    def delete_task_profile(self, user_id: str, profile_id: str) -> bool:
        with database.connect() as connection:
            connection.execute(
                """
                UPDATE playbooks
                SET task_profile_id = NULL, updated_at = ?
                WHERE user_id = ? AND task_profile_id = ?
                """,
                (datetime.now(UTC).isoformat(), user_id, profile_id),
            )
            cursor = connection.execute(
                """
                DELETE FROM task_profiles
                WHERE user_id = ? AND profile_id = ?
                """,
                (user_id, profile_id),
            )
        return cursor.rowcount > 0

    def add_playbook(self, user_id: str, payload: PlaybookCreateRequest) -> Playbook:
        if payload.task_profile_id is not None and self.get_task_profile(user_id, payload.task_profile_id) is None:
            raise UnknownTaskProfileError(payload.task_profile_id)
        now = datetime.now(UTC).isoformat()
        playbook = Playbook(
            playbook_id=str(uuid4()),
            title=payload.title,
            purpose=payload.purpose,
            trigger_phrases=payload.trigger_phrases,
            steps=payload.steps,
            expected_outcome=payload.expected_outcome,
            task_profile_id=payload.task_profile_id,
            created_at=now,
            updated_at=now,
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO playbooks
                (playbook_id, user_id, title, purpose, trigger_phrases, steps,
                 expected_outcome, task_profile_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    playbook.playbook_id,
                    user_id,
                    playbook.title,
                    playbook.purpose,
                    playbook.trigger_phrases,
                    playbook.steps,
                    playbook.expected_outcome,
                    playbook.task_profile_id,
                    playbook.created_at,
                    playbook.updated_at,
                ),
            )
        return playbook

    def list_playbooks(self, user_id: str) -> list[Playbook]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT playbook_id, title, purpose, trigger_phrases, steps, expected_outcome,
                       task_profile_id, created_at, updated_at
                FROM playbooks
                WHERE user_id = ?
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [Playbook(**dict(row)) for row in rows]

    def delete_playbook(self, user_id: str, playbook_id: str) -> bool:
        with database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM playbooks
                WHERE user_id = ? AND playbook_id = ?
                """,
                (user_id, playbook_id),
            )
        return cursor.rowcount > 0

    def search_playbooks(
        self,
        user_id: str,
        query: str,
        limit: int = 3,
    ) -> list[PlaybookSearchResult]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []
        profiles = {profile.profile_id: profile for profile in self.list_task_profiles(user_id)}
        results: list[PlaybookSearchResult] = []
        for playbook in self.list_playbooks(user_id):
            content = " ".join(
                item
                for item in [
                    playbook.title,
                    playbook.purpose,
                    playbook.trigger_phrases or "",
                    playbook.steps,
                    playbook.expected_outcome or "",
                ]
                if item
            )
            overlap = query_terms & self._tokenize(content)
            if not overlap:
                continue
            score = len(overlap) / len(query_terms)
            results.append(
                PlaybookSearchResult(
                    playbook=playbook,
                    task_profile=profiles.get(playbook.task_profile_id or ""),
                    score=round(score, 4),
                )
            )
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def prompt_context(self, user_id: str, query: str, limit: int = 3) -> str:
        results = self.search_playbooks(user_id, query, limit=limit)
        if not results:
            return "Aucun playbook personnel pertinent retrouvé."

        blocks: list[str] = []
        for index, result in enumerate(results, start=1):
            playbook = result.playbook
            profile = result.task_profile
            lines = [
                f"[P{index}] {playbook.title}",
                f"Objectif : {playbook.purpose}",
                f"Étapes : {playbook.steps}",
            ]
            if playbook.expected_outcome:
                lines.append(f"Résultat attendu : {playbook.expected_outcome}")
            if profile is not None:
                lines.extend(
                    [
                        f"Profil de tâche associé : {profile.name}",
                        f"Format de sortie : {profile.output_format}",
                    ]
                )
                if profile.review_checklist:
                    lines.append(f"Checklist de relecture : {profile.review_checklist}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.findall(r"\w+", text.lower()) if len(token) > 2}


class UnknownTaskProfileError(ValueError):
    """Raised when a playbook references a task profile outside the user's scope."""


playbook_store = SQLitePlaybookStore()
