from jarvis_cyber.core.schemas import UserProfileUpdateRequest
from jarvis_cyber.profile.store import SQLiteProfileStore
from jarvis_cyber.storage.database import Database


def test_profile_prompt_context_includes_working_context(monkeypatch, tmp_path) -> None:
    profile_database = Database(tmp_path / "profiles.db")
    monkeypatch.setattr("jarvis_cyber.profile.store.database", profile_database)
    store = SQLiteProfileStore()

    store.update(
        "analyst-1",
        UserProfileUpdateRequest(
            display_name="Stephane",
            job_title="Analyste SOC",
            organization="Blue Team",
            environment_summary="Microsoft 365, Sentinel, Defender.",
            focus_areas="phishing et réponse à incident",
            preferred_language="fr",
            response_style="detailed",
            approval_preference="always_ask",
            timezone="Europe/Brussels",
        ),
    )

    prompt_context = store.prompt_context("analyst-1")

    assert "Analyste SOC" in prompt_context
    assert "Microsoft 365" in prompt_context
    assert "toujours" not in prompt_context.lower()
    assert "always_ask" in prompt_context
