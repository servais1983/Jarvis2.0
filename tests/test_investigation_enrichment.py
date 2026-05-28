from datetime import datetime

from jarvis_cyber.core.schemas import (
    DefenderAlert,
    DefenderIncident,
    EntraRiskyUser,
    EntraSignIn,
    InvestigationCaseCreateRequest,
    InvestigationCaseDefenderEnrichmentRequest,
    InvestigationCaseEntraEnrichmentRequest,
    InvestigationCaseEventCreateRequest,
    InvestigationCaseEvidenceCreateRequest,
    InvestigationCaseSentinelEnrichmentRequest,
    SentinelQueryResult,
)
from jarvis_cyber.investigations.store import SQLiteInvestigationCaseStore
from jarvis_cyber.services.investigation_enrichment import InvestigationEnrichmentService
from jarvis_cyber.storage.database import Database


def test_investigation_case_entra_enrichment_adds_observable_facts_once(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.entra_id_connector.list_sign_ins",
        lambda **kwargs: [
            EntraSignIn(
                sign_in_id="s1",
                created_at="2026-05-18T08:00:00Z",
                user_principal_name="analyst@example.com",
                app_display_name="Microsoft Teams",
                ip_address="203.0.113.10",
                city="Brussels",
                country_or_region="BE",
            )
        ],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.entra_id_connector.list_risky_users",
        lambda limit: [
            EntraRiskyUser(
                user_id="u1",
                user_principal_name="analyst@example.com",
                risk_level="high",
                risk_state="atRisk",
                risk_detail="adminConfirmedUserCompromised",
            )
        ],
    )
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(title="Impossible travel", raw_alert="Suspicious login"),
    )
    service = InvestigationEnrichmentService()
    payload = InvestigationCaseEntraEnrichmentRequest(user_principal_name="analyst@example.com")

    first = service.enrich_from_entra_id("analyst-1", detail.case.case_id, payload)
    second = service.enrich_from_entra_id("analyst-1", detail.case.case_id, payload)

    assert first is not None
    assert first.result.added_events == 1
    assert first.result.added_evidence == 2
    assert first.detail.events[0].title.startswith("Connexion Entra ID")
    assert len(first.detail.evidence) == 2
    assert second is not None
    assert second.result.added_events == 0
    assert second.result.added_evidence == 0


def test_investigation_case_defender_enrichment_adds_observable_facts_once(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.microsoft_defender_connector.list_incidents",
        lambda **kwargs: [
            DefenderIncident(
                incident_id="29",
                display_name="Account compromise",
                status="active",
                severity="high",
            )
        ],
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.microsoft_defender_connector.list_alerts",
        lambda **kwargs: [
            DefenderAlert(
                alert_id="a1",
                incident_id="29",
                title="Suspicious sign-in",
                status="new",
                severity="high",
                service_source="microsoftDefenderForEndpoint",
                detection_source="antivirus",
                first_activity_at="2026-05-18T08:00:00Z",
                evidence_count=2,
            )
        ],
    )
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(title="Impossible travel", raw_alert="Suspicious login"),
    )
    service = InvestigationEnrichmentService()

    first = service.enrich_from_defender(
        "analyst-1",
        detail.case.case_id,
        InvestigationCaseDefenderEnrichmentRequest(),
    )
    second = service.enrich_from_defender(
        "analyst-1",
        detail.case.case_id,
        InvestigationCaseDefenderEnrichmentRequest(),
    )

    assert first is not None
    assert first.result.added_events == 1
    assert first.result.added_evidence == 2
    assert first.detail.events[0].title.startswith("Alerte Defender")
    assert second is not None
    assert second.result.added_events == 0
    assert second.result.added_evidence == 0


def test_investigation_case_sentinel_enrichment_adds_query_results_once(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr(
        "jarvis_cyber.services.investigation_enrichment.microsoft_sentinel_connector.query",
        lambda query, **kwargs: SentinelQueryResult(
            columns=["TimeGenerated", "UserPrincipalName", "IPAddress"],
            rows=[
                {
                    "TimeGenerated": "2026-05-18T08:00:00Z",
                    "UserPrincipalName": "analyst@example.com",
                    "IPAddress": "203.0.113.10",
                }
            ],
            row_count=1,
        ),
    )
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(title="Impossible travel", raw_alert="Suspicious login"),
    )
    service = InvestigationEnrichmentService()
    payload = InvestigationCaseSentinelEnrichmentRequest(query="SigninLogs | take 1")

    first = service.enrich_from_sentinel("analyst-1", detail.case.case_id, payload)
    second = service.enrich_from_sentinel("analyst-1", detail.case.case_id, payload)

    assert first is not None
    assert first.result.added_events == 1
    assert first.result.added_evidence == 1
    assert first.detail.events[0].title.startswith("Résultat Sentinel")
    assert second is not None
    assert second.result.added_events == 0
    assert second.result.added_evidence == 0


def test_investigation_enrichment_plan_recommends_account_connectors(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="Impossible travel analyst@example.com",
            raw_alert="Suspicious login from Brussels then Tokyo with MFA prompt.",
        ),
    )

    plan = InvestigationEnrichmentService().recommend_plan("analyst-1", detail.case.case_id)

    assert plan is not None
    assert plan.inferred_category == "account_compromise"
    recommendation_ids = {item.recommendation_id for item in plan.recommendations}
    assert {
        "entra-sign-ins",
        "defender-account-alerts",
        "sentinel-account-signin-overview",
        "sentinel-account-risky-signins",
    } <= recommendation_ids
    entra = next(item for item in plan.recommendations if item.recommendation_id == "entra-sign-ins")
    assert entra.suggested_parameters["user_principal_name"] == "analyst@example.com"
    assert entra.required_inputs == []
    assert "aucune requête externe" in plan.safety_notes[0]


def test_investigation_enrichment_plan_marks_existing_sources(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="Phishing reçu par victim@example.com",
            raw_alert="Email suspect avec URL https://evil.example/login",
        ),
    )
    case_store.add_evidence(
        "analyst-1",
        detail.case.case_id,
        InvestigationCaseEvidenceCreateRequest(
            title="Sentinel — résultat KQL",
            source="microsoft_sentinel.kql",
        ),
    )

    plan = InvestigationEnrichmentService().recommend_plan("analyst-1", detail.case.case_id)

    assert plan is not None
    assert plan.inferred_category == "phishing"
    sentinel_items = [item for item in plan.recommendations if item.connector == "microsoft_sentinel"]
    assert sentinel_items
    assert all(item.already_enriched for item in sentinel_items)


def test_investigation_incident_view_summarizes_phishing_case(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="Phishing reçu par victim@example.com",
            raw_alert="Email suspect avec URL https://evil.example/login",
        ),
    )

    view = InvestigationEnrichmentService().incident_view("analyst-1", detail.case.case_id)

    assert view is not None
    assert view.inferred_category == "phishing"
    assert view.indicators["recipient"] == "victim@example.com"
    assert view.indicators["url_fragment"] == "https://evil.example/login"
    assert view.headline.startswith("Exposition phishing")
    assert any(section.title == "Indicateurs email / URL" for section in view.sections)
    assert "aucun connecteur" not in view.analyst_note.casefold()


def test_investigation_incident_view_marks_missing_cve_indicator(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="Vulnérabilité critique exposée",
            raw_alert="Exploitation probable mais CVE non précisée.",
        ),
    )

    view = InvestigationEnrichmentService().incident_view("analyst-1", detail.case.case_id)

    assert view is not None
    assert view.inferred_category == "critical_vulnerability"
    vulnerability_section = next(section for section in view.sections if section.title == "Vulnérabilité")
    assert vulnerability_section.status == "missing"


def test_soc_queue_prioritizes_active_cases(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    high = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="CVE-2026-12345 critique exposée",
            raw_alert="Vulnérabilité critique sans preuve encore ajoutée.",
        ),
    )
    low = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="Investigation générale documentée",
            raw_alert="Observation interne à suivre.",
        ),
    )
    case_store.add_evidence(
        "analyst-1",
        low.case.case_id,
        InvestigationCaseEvidenceCreateRequest(title="Note analyste", source="manual"),
    )

    queue = InvestigationEnrichmentService().soc_queue("analyst-1")

    assert queue.total_cases == 2
    assert queue.active_cases == 2
    assert queue.items[0].case_id == high.case.case_id
    assert queue.items[0].priority in {"critical", "high"}
    assert "Aucune preuve" in " ".join(queue.items[0].reasons)
    assert queue.items[0].next_action.startswith("Proposer")


def test_soc_shift_brief_groups_operational_work(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    cve = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="CVE-2026-12345 critique exposée",
            raw_alert="Vulnérabilité critique sans preuve.",
        ),
    )
    documented = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="Dossier documenté",
            raw_alert="Observation interne suivie.",
        ),
    )
    case_store.add_evidence(
        "analyst-1",
        documented.case.case_id,
        InvestigationCaseEvidenceCreateRequest(title="Preuve manuelle", source="manual"),
    )

    brief = InvestigationEnrichmentService().shift_brief("analyst-1")

    assert brief.total_active_cases == 2
    assert brief.critical_cases >= 1
    assert brief.focus_now[0].case_id == cve.case.case_id
    assert any(item.case_id == cve.case.case_id for item in brief.blocked_or_under_evidenced)
    assert brief.operator_guidance
    assert brief.generated_at


def test_soc_sla_watch_flags_old_critical_without_evidence(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(
            title="CVE-2026-12345 critique exposée",
            raw_alert="Vulnérabilité critique sans preuve.",
        ),
    )
    old = "2026-05-19T08:00:00+00:00"
    with investigation_database.connect() as connection:
        connection.execute(
            "UPDATE investigation_cases SET created_at = ?, updated_at = ? WHERE case_id = ?",
            (old, old, detail.case.case_id),
        )

    sla = InvestigationEnrichmentService().sla_watch(
        "analyst-1",
        now=datetime.fromisoformat("2026-05-19T10:00:00+00:00"),
    )

    assert sla.breached_count == 1
    item = sla.items[0]
    assert item.case_id == detail.case.case_id
    assert item.state == "breached"
    assert any("Aucune preuve" in finding for finding in item.breaches)
    assert item.next_action.startswith("Ajouter une preuve")


def test_closure_assistant_blocks_incomplete_case(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(title="Investigation incomplète", raw_alert="Alerte sans preuve."),
    )

    closure = InvestigationEnrichmentService().closure_assistant("analyst-1", detail.case.case_id)

    assert closure is not None
    assert closure.state == "needs_work"
    assert closure.readiness_score < 85
    assert closure.blockers
    assert closure.report_recommended is False
    assert any(check.title == "Preuves" and check.status == "missing" for check in closure.checks)


def test_closure_assistant_marks_documented_case_ready(monkeypatch, tmp_path) -> None:
    investigation_database = Database(tmp_path / "investigations.db")
    monkeypatch.setattr("jarvis_cyber.investigations.store.database", investigation_database)
    monkeypatch.setattr("jarvis_cyber.investigation_profiles.store.database", investigation_database)
    case_store = SQLiteInvestigationCaseStore()
    detail = case_store.create(
        "analyst-1",
        InvestigationCaseCreateRequest(title="Faux positif documenté", raw_alert="Alerte qualifiée."),
    )
    case_store.add_evidence(
        "analyst-1",
        detail.case.case_id,
        InvestigationCaseEvidenceCreateRequest(title="Preuve SIEM", source="manual"),
    )
    case_store.add_event(
        "analyst-1",
        detail.case.case_id,
        InvestigationCaseEventCreateRequest(occurred_at="2026-05-28T08:00:00Z", title="Alerte reçue"),
    )
    case_store.add_note("analyst-1", detail.case.case_id, "Décision : faux positif documenté.")

    closure = InvestigationEnrichmentService().closure_assistant("analyst-1", detail.case.case_id)

    assert closure is not None
    assert closure.state == "ready"
    assert closure.readiness_score >= 85
    assert closure.report_recommended is True
    assert closure.close_recommended is True
