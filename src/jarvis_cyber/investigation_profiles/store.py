from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from jarvis_cyber.core.schemas import (
    InvestigationProfile,
    InvestigationProfileCreateRequest,
    InvestigationProfileSearchResult,
)
from jarvis_cyber.storage.database import database


class SQLiteInvestigationProfileStore:
    """Persist reusable investigation defaults by user."""

    def add(self, user_id: str, payload: InvestigationProfileCreateRequest) -> InvestigationProfile:
        now = datetime.now(UTC).isoformat()
        profile = InvestigationProfile(
            profile_id=str(uuid4()),
            name=payload.name,
            description=payload.description,
            trigger_phrases=payload.trigger_phrases,
            default_goal=payload.default_goal,
            recommended_checks=payload.recommended_checks,
            include_recent_github=payload.include_recent_github,
            drive_query=payload.drive_query,
            jira_jql=payload.jira_jql,
            created_at=now,
            updated_at=now,
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO investigation_profiles
                (profile_id, user_id, name, description, trigger_phrases, default_goal,
                 recommended_checks, include_recent_github, drive_query, jira_jql, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    user_id,
                    profile.name,
                    profile.description,
                    profile.trigger_phrases,
                    profile.default_goal,
                    profile.recommended_checks,
                    int(profile.include_recent_github),
                    profile.drive_query,
                    profile.jira_jql,
                    profile.created_at,
                    profile.updated_at,
                ),
            )
        return profile

    def list(self, user_id: str) -> list[InvestigationProfile]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT profile_id, name, description, trigger_phrases, default_goal, recommended_checks,
                       include_recent_github, drive_query, jira_jql, created_at, updated_at
                FROM investigation_profiles
                WHERE user_id = ?
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [self._profile_from_row(row) for row in rows]

    def get(self, user_id: str, profile_id: str) -> InvestigationProfile | None:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT profile_id, name, description, trigger_phrases, default_goal, recommended_checks,
                       include_recent_github, drive_query, jira_jql, created_at, updated_at
                FROM investigation_profiles
                WHERE user_id = ? AND profile_id = ?
                """,
                (user_id, profile_id),
            ).fetchone()
        return self._profile_from_row(row) if row is not None else None

    def delete(self, user_id: str, profile_id: str) -> bool:
        with database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM investigation_profiles
                WHERE user_id = ? AND profile_id = ?
                """,
                (user_id, profile_id),
            )
        return cursor.rowcount > 0

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 3,
    ) -> list[InvestigationProfileSearchResult]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []
        results: list[InvestigationProfileSearchResult] = []
        for profile in self.list(user_id):
            content = " ".join(
                item
                for item in [
                    profile.name,
                    profile.description or "",
                    profile.trigger_phrases or "",
                    profile.default_goal or "",
                    profile.recommended_checks or "",
                ]
                if item
            )
            overlap = query_terms & self._tokenize(content)
            if not overlap:
                continue
            results.append(
                InvestigationProfileSearchResult(
                    profile=profile,
                    score=round(len(overlap) / len(query_terms), 4),
                )
            )
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    @staticmethod
    def _profile_from_row(row) -> InvestigationProfile:
        payload = dict(row)
        payload["include_recent_github"] = bool(payload["include_recent_github"])
        return InvestigationProfile(**payload)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.findall(r"\w+", text.lower()) if len(token) > 2}


investigation_profile_store = SQLiteInvestigationProfileStore()
