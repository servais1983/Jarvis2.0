from jarvis_cyber.core.schemas import (
    InvestigationCaseCreateRequest,
    InvestigationCaseEventCreateRequest,
    InvestigationCaseEvidenceCreateRequest,
    InvestigationCaseHypothesisCreateRequest,
    InvestigationCaseHypothesisUpdateRequest,
    InvestigationChecklistItemUpdateRequest,
    InvestigationProfileCreateRequest,
)
from jarvis_cyber.investigation_profiles.store import SQLiteInvestigationProfileStore
from jarvis_cyber.investigations.store import SQLiteInvestigationCaseStore
from jarvis_cyber.storage.database import Database


def test_investigation_case_round_trip_with_progress(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    profile_store = SQLiteInvestigationProfileStore()
    case_store = SQLiteInvestigationCaseStore()
    profile = profile_store.add(
        "analyst-1",
        InvestigationProfileCreateRequest(
            name="Compromission de compte",
            recommended_checks="Vérifier les connexions.\nContrôler MFA.",
        ),
    )

    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="Impossible travel",
            raw_alert="Connexion Bruxelles puis Tokyo.",
            investigation_profile_id=profile.profile_id,
        ),
    )
    updated = case_store.update_checklist_item(
        "analyst-1",
        detail.case.case_id,
        detail.checklist_items[0].item_id,
        InvestigationChecklistItemUpdateRequest(status="done", notes="Connexion confirmée."),
    )
    with_note = case_store.add_note("analyst-1", detail.case.case_id, "Escalade vers IAM.")
    with_event = case_store.add_event(
        "analyst-1",
        detail.case.case_id,
        InvestigationCaseEventCreateRequest(
            occurred_at="2026-05-18T08:00:00Z",
            title="Connexion Bruxelles",
        ),
    )
    with_evidence = case_store.add_evidence(
        "analyst-1",
        detail.case.case_id,
        InvestigationCaseEvidenceCreateRequest(
            title="Journal Entra ID",
            source="entra",
        ),
    )
    with_hypothesis = case_store.add_hypothesis(
        "analyst-1",
        detail.case.case_id,
        InvestigationCaseHypothesisCreateRequest(
            statement="Compte compromis",
            rationale="Connexion impossible.",
        ),
    )
    supported = case_store.update_hypothesis(
        "analyst-1",
        detail.case.case_id,
        with_hypothesis.hypotheses[0].hypothesis_id,
        InvestigationCaseHypothesisUpdateRequest(
            status="supported",
            rationale="MFA modifié puis connexion étrangère.",
        ),
    )

    assert len(detail.checklist_items) == 2
    assert updated is not None
    assert updated.summary.done_checks == 1
    assert updated.summary.completion_ratio == 0.5
    assert with_note is not None
    assert with_note.summary.latest_note == "Escalade vers IAM."
    assert with_event is not None
    assert with_event.events[0].title == "Connexion Bruxelles"
    assert with_evidence is not None
    assert with_evidence.evidence[0].source == "entra"
    assert supported is not None
    assert supported.summary.supported_hypotheses == 1
