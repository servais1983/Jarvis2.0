from jarvis_cyber.core.schemas import PlaybookCreateRequest, TaskProfileCreateRequest
from jarvis_cyber.playbooks.store import SQLitePlaybookStore
from jarvis_cyber.storage.database import Database


def test_playbook_search_returns_profile(monkeypatch, tmp_path) -> None:
    playbook_database = Database(tmp_path / "playbooks.db")
    monkeypatch.setattr("jarvis_cyber.playbooks.store.database", playbook_database)
    store = SQLitePlaybookStore()

    profile = store.add_task_profile(
        "analyst-1",
        TaskProfileCreateRequest(
            name="Brief SOC",
            description="Synthèse rapide.",
            output_format="Résumé, faits, actions.",
            review_checklist="Séparer faits et hypothèses.",
        ),
    )
    store.add_playbook(
        "analyst-1",
        PlaybookCreateRequest(
            title="Triage phishing",
            purpose="Qualifier un email suspect.",
            trigger_phrases="phishing email suspect",
            steps="Vérifier expéditeur, URLs et pièces jointes.",
            expected_outcome="Décision et actions.",
            task_profile_id=profile.profile_id,
        ),
    )

    results = store.search_playbooks("analyst-1", "email phishing")
    context = store.prompt_context("analyst-1", "email phishing")

    assert results[0].playbook.title == "Triage phishing"
    assert results[0].task_profile is not None
    assert results[0].task_profile.name == "Brief SOC"
    assert "Profil de tâche associé : Brief SOC" in context
