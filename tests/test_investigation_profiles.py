from jarvis_cyber.core.schemas import (
    AlertInvestigationRequest,
    ConnectorDigestResponse,
    InvestigationProfileCreateRequest,
)
from jarvis_cyber.investigation_profiles.store import SQLiteInvestigationProfileStore
from jarvis_cyber.services.workflows import CyberWorkflowService, assistant_service
from jarvis_cyber.storage.database import Database


def test_investigation_profile_round_trip_and_search(monkeypatch, tmp_path) -> None:
    profile_database = Database(tmp_path / "investigation_profiles.db")
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", profile_database)
    store = SQLiteInvestigationProfileStore()

    profile = store.add(
        "analyst-1",
        InvestigationProfileCreateRequest(
            name="Compromission de compte",
            description="Enquêtes identité et connexions suspectes.",
            trigger_phrases="impossible travel connexion suspecte",
            default_goal="Déterminer si le compte est compromis.",
            recommended_checks="Vérifier les connexions impossibles.",
            include_recent_github=True,
            drive_query="name contains 'identity'",
            jira_jql="project = SEC AND labels = identity",
        ),
    )

    listed = store.list("analyst-1")
    results = store.search("analyst-1", "impossible travel utilisateur")

    assert listed[0].profile_id == profile.profile_id
    assert listed[0].include_recent_github is True
    assert listed[0].recommended_checks == "Vérifier les connexions impossibles."
    assert results[0].profile.name == "Compromission de compte"
    assert store.delete("analyst-1", profile.profile_id) is True
    assert store.list("analyst-1") == []


def test_alert_investigation_applies_explicit_profile(monkeypatch, tmp_path) -> None:
    profile_database = Database(tmp_path / "investigation_profiles.db")
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", profile_database)
    store = SQLiteInvestigationProfileStore()
    monkeypatch.setattr("jarvis_cyber.services.workflows.investigation_profile_store", store)
    monkeypatch.setattr("jarvis_cyber.services.workflows.knowledge_store.search", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.knowledge_store.chunks_for_results",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.playbook_store.search_playbooks",
        lambda *args, **kwargs: [],
    )
    captured_payloads = []
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.connector_digest_service.build",
        lambda payload: captured_payloads.append(payload) or ConnectorDigestResponse(generated_at="now"),
    )
    profile = store.add(
        "analyst-1",
        InvestigationProfileCreateRequest(
            name="Compromission de compte",
            default_goal="Confirmer une compromission d'identité.",
            recommended_checks="Contrôler les changements MFA.",
            include_recent_github=True,
            drive_query="name contains 'identity'",
            jira_jql="project = SEC AND labels = identity",
        ),
    )

    *_, applied_profile = CyberWorkflowService().investigate_alert(
        "analyst-1",
        AlertInvestigationRequest(
            title="Alerte non spécifique",
            raw_alert="Événement à qualifier.",
            investigation_profile_id=profile.profile_id,
        ),
    )

    assert applied_profile is not None
    assert applied_profile.profile_id == profile.profile_id
    assert applied_profile.recommended_checks == "Contrôler les changements MFA."
    assert captured_payloads[0].include_github is True
    assert captured_payloads[0].include_google_drive is True
    assert captured_payloads[0].include_jira is True


def test_alert_investigation_infers_matching_profile(monkeypatch, tmp_path) -> None:
    profile_database = Database(tmp_path / "investigation_profiles.db")
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", profile_database)
    store = SQLiteInvestigationProfileStore()
    monkeypatch.setattr("jarvis_cyber.services.workflows.investigation_profile_store", store)
    monkeypatch.setattr("jarvis_cyber.services.workflows.knowledge_store.search", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.knowledge_store.chunks_for_results",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.playbook_store.search_playbooks",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.connector_digest_service.build",
        lambda payload: ConnectorDigestResponse(generated_at="now"),
    )
    store.add(
        "analyst-1",
        InvestigationProfileCreateRequest(
            name="Phishing",
            trigger_phrases="phishing email suspect",
            default_goal="Qualifier un email suspect.",
        ),
    )

    *_, applied_profile = CyberWorkflowService().investigate_alert(
        "analyst-1",
        AlertInvestigationRequest(
            title="Email suspect",
            raw_alert="Signalement phishing reçu par un utilisateur.",
        ),
    )

    assert applied_profile is not None
    assert applied_profile.name == "Phishing"


def test_alert_investigation_injects_profile_checklist(monkeypatch, tmp_path) -> None:
    profile_database = Database(tmp_path / "investigation_profiles.db")
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", profile_database)
    store = SQLiteInvestigationProfileStore()
    monkeypatch.setattr("jarvis_cyber.services.workflows.investigation_profile_store", store)
    monkeypatch.setattr("jarvis_cyber.services.workflows.knowledge_store.search", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.knowledge_store.chunks_for_results",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.playbook_store.search_playbooks",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.connector_digest_service.build",
        lambda payload: ConnectorDigestResponse(generated_at="now"),
    )
    profile = store.add(
        "analyst-1",
        InvestigationProfileCreateRequest(
            name="Phishing",
            recommended_checks="Vérifier les URLs.",
        ),
    )
    captured_inputs = []
    original_complete_structured = assistant_service.complete_structured

    def capture_complete_structured(prompt, input_text, response_model, fallback_factory):
        captured_inputs.append(input_text)
        return original_complete_structured(prompt, input_text, response_model, fallback_factory)

    monkeypatch.setattr(
        "jarvis_cyber.services.workflows.assistant_service.complete_structured",
        capture_complete_structured,
    )

    CyberWorkflowService().investigate_alert(
        "analyst-1",
        AlertInvestigationRequest(
            title="Email suspect",
            raw_alert="Lien reçu.",
            investigation_profile_id=profile.profile_id,
        ),
    )

    assert any("Checklist recommandée par le profil" in item for item in captured_inputs)
    assert any("Vérifier les URLs." in item for item in captured_inputs)
