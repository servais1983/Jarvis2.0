from __future__ import annotations

from datetime import UTC, datetime

from jarvis_cyber.core.schemas import UserProfileResponse, UserProfileUpdateRequest
from jarvis_cyber.storage.database import database


class SQLiteProfileStore:
    """Persist user-specific working context separately from documents."""

    DEFAULT_LANGUAGE = "fr"
    DEFAULT_RESPONSE_STYLE = "balanced"
    DEFAULT_APPROVAL_PREFERENCE = "ask_before_sensitive_actions"

    def get(self, user_id: str) -> UserProfileResponse:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, display_name, job_title, organization, environment_summary,
                       focus_areas, preferred_language, response_style, approval_preference,
                       timezone, created_at, updated_at
                FROM user_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    """
                    INSERT INTO user_profiles
                    (user_id, display_name, job_title, organization, environment_summary,
                     focus_areas, preferred_language, response_style, approval_preference,
                     timezone, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        None,
                        None,
                        None,
                        None,
                        None,
                        self.DEFAULT_LANGUAGE,
                        self.DEFAULT_RESPONSE_STYLE,
                        self.DEFAULT_APPROVAL_PREFERENCE,
                        None,
                        now,
                        now,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT user_id, display_name, job_title, organization, environment_summary,
                           focus_areas, preferred_language, response_style, approval_preference,
                           timezone, created_at, updated_at
                    FROM user_profiles
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()
        return UserProfileResponse(**dict(row))

    def update(self, user_id: str, payload: UserProfileUpdateRequest) -> UserProfileResponse:
        current = self.get(user_id)
        data = current.model_dump()
        updates = payload.model_dump(exclude_unset=True)
        for field in ("preferred_language", "response_style", "approval_preference"):
            if updates.get(field) is None:
                updates.pop(field, None)
        data.update(updates)
        data["updated_at"] = datetime.now(UTC).isoformat()

        with database.connect() as connection:
            connection.execute(
                """
                UPDATE user_profiles
                SET display_name = ?,
                    job_title = ?,
                    organization = ?,
                    environment_summary = ?,
                    focus_areas = ?,
                    preferred_language = ?,
                    response_style = ?,
                    approval_preference = ?,
                    timezone = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (
                    data["display_name"],
                    data["job_title"],
                    data["organization"],
                    data["environment_summary"],
                    data["focus_areas"],
                    data["preferred_language"],
                    data["response_style"],
                    data["approval_preference"],
                    data["timezone"],
                    data["updated_at"],
                    user_id,
                ),
            )
        return self.get(user_id)

    def prompt_context(self, user_id: str) -> str:
        profile = self.get(user_id)
        lines = [
            f"- Nom affiché : {profile.display_name}" if profile.display_name else None,
            f"- Fonction : {profile.job_title}" if profile.job_title else None,
            f"- Organisation : {profile.organization}" if profile.organization else None,
            (
                f"- Environnement de travail : {profile.environment_summary}"
                if profile.environment_summary
                else None
            ),
            f"- Domaines prioritaires : {profile.focus_areas}" if profile.focus_areas else None,
            f"- Langue préférée : {profile.preferred_language}",
            f"- Style de réponse préféré : {profile.response_style}",
            f"- Préférence d'approbation : {profile.approval_preference}",
            f"- Fuseau horaire : {profile.timezone}" if profile.timezone else None,
        ]
        populated_lines = [line for line in lines if line]
        if len(populated_lines) <= 3:
            return (
                "Profil encore peu renseigné. Utilise les préférences disponibles, "
                "mais ne déduis pas d'informations personnelles absentes."
            )
        return "\n".join(populated_lines)


profile_store = SQLiteProfileStore()
