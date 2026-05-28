from __future__ import annotations

import re
from datetime import UTC, datetime

from jarvis_cyber.core.schemas import (
    DefenderAlert,
    DefenderIncident,
    EntraRiskyUser,
    EntraSignIn,
    InvestigationCaseDefenderEnrichmentRequest,
    InvestigationCaseDefenderEnrichmentResponse,
    InvestigationCaseDefenderEnrichmentResult,
    InvestigationCaseDetail,
    InvestigationEnrichmentCategory,
    InvestigationEnrichmentPlanResponse,
    InvestigationEnrichmentRecommendation,
    InvestigationCaseEntraEnrichmentRequest,
    InvestigationCaseEntraEnrichmentResponse,
    InvestigationCaseEntraEnrichmentResult,
    InvestigationCaseEventCreateRequest,
    InvestigationCaseEvidenceCreateRequest,
    InvestigationClosureAssistantResponse,
    InvestigationClosureCheck,
    InvestigationIncidentViewResponse,
    InvestigationIncidentViewSection,
    InvestigationSOCQueueItem,
    InvestigationSOCQueueResponse,
    SOCSLAItem,
    SOCSLAResponse,
    SOCShiftBriefResponse,
    InvestigationCaseSentinelEnrichmentRequest,
    InvestigationCaseSentinelEnrichmentResponse,
    InvestigationCaseSentinelEnrichmentResult,
    SentinelQueryResult,
)
from jarvis_cyber.integrations.entra_id import entra_id_connector
from jarvis_cyber.integrations.microsoft_defender import microsoft_defender_connector
from jarvis_cyber.integrations.microsoft_sentinel import microsoft_sentinel_connector
from jarvis_cyber.investigation_profiles.store import investigation_profile_store
from jarvis_cyber.investigations.store import investigation_case_store


class InvestigationEnrichmentService:
    """Enrich live investigation dossiers with explicit, observable connector facts."""

    def recommend_plan(
        self,
        user_id: str,
        case_id: str,
    ) -> InvestigationEnrichmentPlanResponse | None:
        detail = investigation_case_store.get_detail(user_id, case_id)
        if detail is None:
            return None

        corpus = self._case_corpus(user_id, detail)
        category, confidence = self._infer_category(corpus)
        indicators = self._extract_indicators(corpus)
        return InvestigationEnrichmentPlanResponse(
            case_id=case_id,
            inferred_category=category,
            confidence=confidence,
            recommendations=self._recommendations_for_category(detail, category, indicators),
            safety_notes=[
                "Plan consultatif uniquement : aucune requête externe n'est exécutée automatiquement.",
                "Les enrichissements ajoutent des faits au dossier, pas des conclusions automatiques.",
                "Les requêtes KQL Sentinel restent sensibles et doivent être validées explicitement.",
            ],
        )

    def incident_view(
        self,
        user_id: str,
        case_id: str,
    ) -> InvestigationIncidentViewResponse | None:
        detail = investigation_case_store.get_detail(user_id, case_id)
        if detail is None:
            return None

        corpus = self._case_corpus(user_id, detail)
        category, confidence = self._infer_category(corpus)
        indicators = self._extract_indicators(corpus)
        return InvestigationIncidentViewResponse(
            case_id=case_id,
            inferred_category=category,
            confidence=confidence,
            headline=self._incident_headline(category, detail),
            indicators=indicators,
            sections=self._incident_sections(category, detail, indicators),
            next_questions=self._next_questions(category, indicators),
            analyst_note=(
                "Vue de pilotage locale : elle résume le dossier et les angles d'analyse, "
                "sans interroger de connecteur ni modifier les faits."
            ),
        )

    def soc_queue(self, user_id: str) -> InvestigationSOCQueueResponse:
        cases = investigation_case_store.list(user_id)
        items: list[InvestigationSOCQueueItem] = []
        for case in cases:
            detail = investigation_case_store.get_detail(user_id, case.case_id)
            if detail is None:
                continue
            if detail.case.status == "closed":
                continue
            corpus = self._case_corpus(user_id, detail)
            category, _confidence = self._infer_category(corpus)
            score, reasons = self._soc_score(detail, category)
            items.append(
                InvestigationSOCQueueItem(
                    case_id=detail.case.case_id,
                    title=detail.case.title,
                    status=detail.case.status,
                    inferred_category=category,
                    priority=self._soc_priority(score),
                    score=score,
                    reasons=reasons,
                    next_action=self._soc_next_action(detail, category),
                    evidence_count=len(detail.evidence),
                    event_count=len(detail.events),
                    open_hypotheses=detail.summary.open_hypotheses,
                    todo_checks=detail.summary.todo_checks,
                    updated_at=detail.case.updated_at,
                )
            )
        return InvestigationSOCQueueResponse(
            total_cases=len(cases),
            active_cases=len(items),
            items=sorted(items, key=lambda item: (-item.score, item.updated_at)),
        )

    def shift_brief(self, user_id: str) -> SOCShiftBriefResponse:
        queue = self.soc_queue(user_id)
        focus_now = [
            item
            for item in queue.items
            if item.priority in ("critical", "high")
        ][:5]
        blocked_or_under_evidenced = [
            item
            for item in queue.items
            if item.evidence_count == 0 or item.event_count == 0 or "Hypothèses ouvertes à trancher" in item.reasons
        ][:5]
        ready_for_report = [
            item
            for item in queue.items
            if item.evidence_count > 0
            and item.open_hypotheses == 0
            and item.todo_checks == 0
            and item.priority in ("low", "medium")
        ][:5]
        can_wait = [
            item
            for item in queue.items
            if item.priority == "low" and item.case_id not in {ready.case_id for ready in ready_for_report}
        ][:5]
        return SOCShiftBriefResponse(
            generated_at=datetime.now(UTC).isoformat(),
            headline=self._shift_headline(queue),
            total_active_cases=queue.active_cases,
            critical_cases=sum(item.priority == "critical" for item in queue.items),
            high_cases=sum(item.priority == "high" for item in queue.items),
            focus_now=focus_now,
            blocked_or_under_evidenced=blocked_or_under_evidenced,
            ready_for_report=ready_for_report,
            can_wait=can_wait,
            operator_guidance=self._shift_guidance(queue, focus_now, blocked_or_under_evidenced, ready_for_report),
        )

    def sla_watch(self, user_id: str, now: datetime | None = None) -> SOCSLAResponse:
        now = now or datetime.now(UTC)
        queue = self.soc_queue(user_id)
        items: list[SOCSLAItem] = []
        for queue_item in queue.items:
            detail = investigation_case_store.get_detail(user_id, queue_item.case_id)
            if detail is None:
                continue
            age_minutes = self._minutes_between(self._parse_datetime(detail.case.created_at), now)
            idle_minutes = self._minutes_between(self._parse_datetime(detail.case.updated_at), now)
            breaches, warnings = self._sla_findings(queue_item, age_minutes, idle_minutes)
            state = "breached" if breaches else "warning" if warnings else "ok"
            items.append(
                SOCSLAItem(
                    case_id=queue_item.case_id,
                    title=queue_item.title,
                    priority=queue_item.priority,
                    inferred_category=queue_item.inferred_category,
                    state=state,
                    age_minutes=age_minutes,
                    idle_minutes=idle_minutes,
                    breaches=breaches,
                    warnings=warnings,
                    next_action=self._sla_next_action(queue_item, breaches, warnings),
                )
            )
        items = sorted(
            items,
            key=lambda item: (
                {"breached": 0, "warning": 1, "ok": 2}[item.state],
                -item.age_minutes,
                item.title,
            ),
        )
        return SOCSLAResponse(
            generated_at=now.isoformat(),
            total_active_cases=queue.active_cases,
            breached_count=sum(item.state == "breached" for item in items),
            warning_count=sum(item.state == "warning" for item in items),
            items=items,
        )

    def closure_assistant(
        self,
        user_id: str,
        case_id: str,
    ) -> InvestigationClosureAssistantResponse | None:
        detail = investigation_case_store.get_detail(user_id, case_id)
        if detail is None:
            return None

        checks = self._closure_checks(detail)
        blockers = [check.detail for check in checks if check.status == "missing"]
        readiness_score = self._closure_score(checks)
        if detail.case.status == "closed":
            state = "already_closed"
        else:
            state = "ready" if readiness_score >= 85 and not blockers else "needs_work"
        return InvestigationClosureAssistantResponse(
            case_id=case_id,
            state=state,
            readiness_score=readiness_score,
            headline=self._closure_headline(detail, state, readiness_score),
            checks=checks,
            blockers=blockers,
            recommended_next_action=self._closure_next_action(state, blockers, checks),
            report_recommended=state == "ready",
            close_recommended=state == "ready",
        )

    def enrich_from_entra_id(
        self,
        user_id: str,
        case_id: str,
        payload: InvestigationCaseEntraEnrichmentRequest,
    ) -> InvestigationCaseEntraEnrichmentResponse | None:
        detail = investigation_case_store.get_detail(user_id, case_id)
        if detail is None:
            return None

        sign_ins = entra_id_connector.list_sign_ins(
            limit=payload.sign_in_limit,
            user_principal_name=payload.user_principal_name,
        )
        risky_users = [
            item
            for item in entra_id_connector.list_risky_users(limit=20)
            if item.user_principal_name == payload.user_principal_name
        ]

        added_events = self._add_sign_in_events(user_id, case_id, detail, sign_ins)
        refreshed_detail = investigation_case_store.get_detail(user_id, case_id)
        assert refreshed_detail is not None
        added_evidence = self._add_evidence(
            user_id,
            case_id,
            refreshed_detail,
            payload.user_principal_name,
            sign_ins,
            risky_users,
        )
        updated_detail = investigation_case_store.get_detail(user_id, case_id)
        assert updated_detail is not None
        return InvestigationCaseEntraEnrichmentResponse(
            detail=updated_detail,
            result=InvestigationCaseEntraEnrichmentResult(
                sign_ins_reviewed=len(sign_ins),
                matched_risky_users=len(risky_users),
                added_events=added_events,
                added_evidence=added_evidence,
            ),
        )

    def enrich_from_defender(
        self,
        user_id: str,
        case_id: str,
        payload: InvestigationCaseDefenderEnrichmentRequest,
    ) -> InvestigationCaseDefenderEnrichmentResponse | None:
        detail = investigation_case_store.get_detail(user_id, case_id)
        if detail is None:
            return None

        incidents = self._filter_incidents(
            microsoft_defender_connector.list_incidents(
                limit=payload.incident_limit,
                severity=payload.severity,
            ),
            payload.query,
        )
        alerts = self._filter_alerts(
            microsoft_defender_connector.list_alerts(
                limit=payload.alert_limit,
                severity=payload.severity,
                service_source=payload.service_source,
            ),
            payload.query,
        )

        added_events = self._add_defender_alert_events(user_id, case_id, detail, alerts)
        refreshed_detail = investigation_case_store.get_detail(user_id, case_id)
        assert refreshed_detail is not None
        added_evidence = self._add_defender_evidence(
            user_id,
            case_id,
            refreshed_detail,
            incidents,
            alerts,
        )
        updated_detail = investigation_case_store.get_detail(user_id, case_id)
        assert updated_detail is not None
        return InvestigationCaseDefenderEnrichmentResponse(
            detail=updated_detail,
            result=InvestigationCaseDefenderEnrichmentResult(
                incidents_reviewed=len(incidents),
                alerts_reviewed=len(alerts),
                added_events=added_events,
                added_evidence=added_evidence,
            ),
        )

    def enrich_from_sentinel(
        self,
        user_id: str,
        case_id: str,
        payload: InvestigationCaseSentinelEnrichmentRequest,
    ) -> InvestigationCaseSentinelEnrichmentResponse | None:
        detail = investigation_case_store.get_detail(user_id, case_id)
        if detail is None:
            return None

        query_result = microsoft_sentinel_connector.query(
            payload.query,
            timespan=payload.timespan,
            max_rows=100,
        )
        added_events = self._add_sentinel_events(user_id, case_id, detail, query_result, payload.max_events)
        refreshed_detail = investigation_case_store.get_detail(user_id, case_id)
        assert refreshed_detail is not None
        added_evidence = self._add_sentinel_evidence(
            user_id,
            case_id,
            refreshed_detail,
            query_result,
            payload,
        )
        updated_detail = investigation_case_store.get_detail(user_id, case_id)
        assert updated_detail is not None
        return InvestigationCaseSentinelEnrichmentResponse(
            detail=updated_detail,
            result=InvestigationCaseSentinelEnrichmentResult(
                rows_reviewed=query_result.row_count,
                added_events=added_events,
                added_evidence=added_evidence,
                columns=query_result.columns,
            ),
        )

    @staticmethod
    def _case_corpus(user_id: str, detail: InvestigationCaseDetail) -> str:
        case = detail.case
        profile_text = ""
        if case.investigation_profile_id:
            profile = investigation_profile_store.get(user_id, case.investigation_profile_id)
            if profile is not None:
                profile_text = " ".join(
                    item
                    for item in (
                        profile.name,
                        profile.description or "",
                        profile.trigger_phrases or "",
                        profile.default_goal or "",
                        profile.recommended_checks or "",
                    )
                    if item
                )
        return " ".join(
            item
            for item in (
                case.title,
                case.raw_alert,
                case.environment_context or "",
                case.goal or "",
                profile_text,
                " ".join(check.title for check in detail.checklist_items),
                " ".join(note.body for note in detail.notes),
                " ".join(f"{evidence.title} {evidence.description or ''} {evidence.source or ''}" for evidence in detail.evidence),
                " ".join(hypothesis.statement for hypothesis in detail.hypotheses),
            )
            if item
        )

    @classmethod
    def _infer_category(cls, corpus: str) -> tuple[InvestigationEnrichmentCategory, float]:
        normalized = corpus.casefold()
        category_terms: dict[InvestigationEnrichmentCategory, tuple[str, ...]] = {
            "account_compromise": (
                "impossible travel",
                "connexion suspecte",
                "compte compromis",
                "identity",
                "mfa",
                "sign-in",
                "signin",
                "login",
                "entra",
                "userprincipalname",
            ),
            "phishing": (
                "phishing",
                "email suspect",
                "mail suspect",
                "recipient",
                "sender",
                "url",
                "pièce jointe",
                "piece jointe",
                "credential harvesting",
            ),
            "malware": (
                "malware",
                "powershell",
                "script",
                "lolbin",
                "process",
                "processus",
                "execution",
                "exécution",
                "deviceprocessevents",
                "sha256",
            ),
            "data_exfiltration": (
                "exfiltration",
                "fuite",
                "données",
                "donnees",
                "download",
                "téléchargement massif",
                "partage anormal",
                "cloudappevents",
            ),
            "critical_vulnerability": (
                "cve-",
                "vulnérabilité",
                "vulnerabilite",
                "critical",
                "critique",
                "exploit",
                "kev",
                "patch",
                "tvm",
            ),
        }
        scores = {
            category: sum(1 for term in terms if term in normalized)
            for category, terms in category_terms.items()
        }
        best_category, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score == 0:
            return "general", 0.2
        return best_category, min(0.95, round(0.45 + best_score * 0.12, 2))

    @staticmethod
    def _extract_indicators(corpus: str) -> dict[str, str]:
        indicators: dict[str, str] = {}
        email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", corpus)
        if email_match:
            email = email_match.group(0)
            indicators["user_principal_name"] = email
            indicators["recipient"] = email
            indicators["account"] = email

        cve_match = re.search(r"CVE-\d{4}-\d{4,}", corpus, flags=re.IGNORECASE)
        if cve_match:
            indicators["cve_id"] = cve_match.group(0).upper()

        url_match = re.search(r"https?://[^\s\"'<>]+", corpus)
        if url_match:
            indicators["url_fragment"] = url_match.group(0).rstrip(".,;)")
        else:
            domain_match = re.search(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", corpus, flags=re.IGNORECASE)
            if domain_match and "@" not in domain_match.group(0):
                indicators["url_fragment"] = domain_match.group(0)

        device_match = re.search(
            r"\b(?:device|host|machine|poste|ordinateur|serveur)\s*[:=]?\s*([A-Za-z0-9._-]{3,80})",
            corpus,
            flags=re.IGNORECASE,
        )
        if device_match:
            indicators["device_name"] = device_match.group(1)

        return indicators

    @classmethod
    def _recommendations_for_category(
        cls,
        detail: InvestigationCaseDetail,
        category: InvestigationEnrichmentCategory,
        indicators: dict[str, str],
    ) -> list[InvestigationEnrichmentRecommendation]:
        recommendations_by_category: dict[
            InvestigationEnrichmentCategory,
            list[dict[str, object]],
        ] = {
            "account_compromise": [
                {
                    "recommendation_id": "entra-sign-ins",
                    "title": "Examiner les connexions Entra ID du compte",
                    "connector": "microsoft_entra_id",
                    "action": "enrich_entra_sign_ins_and_risky_user",
                    "priority": "high",
                    "rationale": "Un dossier de compromission de compte doit d'abord établir les connexions, IP, applications et signaux de risque.",
                    "required_inputs": ["user_principal_name"],
                    "source": "microsoft_entra_id.sign_ins",
                },
                {
                    "recommendation_id": "defender-account-alerts",
                    "title": "Rechercher les alertes Defender liées au compte",
                    "connector": "microsoft_defender",
                    "action": "enrich_defender_alerts",
                    "priority": "high",
                    "rationale": "Defender peut relier l'identité à des alertes endpoint, email ou cloud corrélées.",
                    "required_inputs": ["query"],
                    "source": "microsoft_defender.alerts_v2",
                },
                {
                    "recommendation_id": "sentinel-account-signin-overview",
                    "title": "Lancer le pack KQL des connexions récentes",
                    "connector": "microsoft_sentinel",
                    "action": "render_and_run_kql_template",
                    "priority": "medium",
                    "rationale": "Le pack KQL donne une vue chronologique plus large, utile pour valider ou contredire l'impossible travel.",
                    "required_inputs": ["user_principal_name"],
                    "sentinel_template_id": "account-signin-overview",
                    "source": "microsoft_sentinel.kql",
                },
                {
                    "recommendation_id": "sentinel-account-risky-signins",
                    "title": "Isoler les connexions risquées du compte",
                    "connector": "microsoft_sentinel",
                    "action": "render_and_run_kql_template",
                    "priority": "medium",
                    "rationale": "Cette requête concentre l'analyse sur les signaux de risque plutôt que sur tout le bruit de connexion.",
                    "required_inputs": ["user_principal_name"],
                    "sentinel_template_id": "account-risky-signins",
                    "source": "microsoft_sentinel.kql",
                },
            ],
            "phishing": [
                {
                    "recommendation_id": "defender-phishing-alerts",
                    "title": "Rechercher les alertes Defender liées au phishing",
                    "connector": "microsoft_defender",
                    "action": "enrich_defender_alerts",
                    "priority": "high",
                    "rationale": "Defender peut fournir le statut de détection, les destinataires touchés et les éléments de preuve associés.",
                    "required_inputs": ["query"],
                    "source": "microsoft_defender.alerts_v2",
                },
                {
                    "recommendation_id": "sentinel-phishing-recipient",
                    "title": "Lister les emails reçus par le destinataire",
                    "connector": "microsoft_sentinel",
                    "action": "render_and_run_kql_template",
                    "priority": "high",
                    "rationale": "Il faut mesurer l'exposition réelle : destinataire, expéditeur, livraison et détection.",
                    "required_inputs": ["recipient"],
                    "sentinel_template_id": "phishing-recipient-email-events",
                    "source": "microsoft_sentinel.kql",
                },
                {
                    "recommendation_id": "sentinel-phishing-url-clicks",
                    "title": "Chercher les clics sur l'URL suspecte",
                    "connector": "microsoft_sentinel",
                    "action": "render_and_run_kql_template",
                    "priority": "medium",
                    "rationale": "Les clics changent fortement la priorité de réponse et le périmètre de remédiation.",
                    "required_inputs": ["url_fragment"],
                    "sentinel_template_id": "phishing-url-clicks",
                    "source": "microsoft_sentinel.kql",
                },
            ],
            "malware": [
                {
                    "recommendation_id": "defender-malware-incidents",
                    "title": "Examiner incidents et alertes Defender sur l'appareil",
                    "connector": "microsoft_defender",
                    "action": "enrich_defender_incidents_and_alerts",
                    "priority": "high",
                    "rationale": "Defender donne souvent la chaîne d'alerte, les preuves et l'incident parent pour une exécution suspecte.",
                    "required_inputs": ["query"],
                    "source": "microsoft_defender.alerts_v2",
                },
                {
                    "recommendation_id": "sentinel-malware-processes",
                    "title": "Reconstruire les processus sur l'appareil",
                    "connector": "microsoft_sentinel",
                    "action": "render_and_run_kql_template",
                    "priority": "high",
                    "rationale": "La chaîne parent/enfant et les lignes de commande sont centrales pour distinguer admin légitime et malware.",
                    "required_inputs": ["device_name"],
                    "sentinel_template_id": "malware-device-processes",
                    "source": "microsoft_sentinel.kql",
                },
                {
                    "recommendation_id": "sentinel-malware-powershell",
                    "title": "Chercher les PowerShell suspects",
                    "connector": "microsoft_sentinel",
                    "action": "render_and_run_kql_template",
                    "priority": "medium",
                    "rationale": "PowerShell encodé ou téléchargeur est un pivot fréquent en intrusion.",
                    "required_inputs": ["device_name"],
                    "sentinel_template_id": "malware-powershell",
                    "source": "microsoft_sentinel.kql",
                },
            ],
            "data_exfiltration": [
                {
                    "recommendation_id": "defender-exfil-alerts",
                    "title": "Rechercher les alertes Defender liées à l'exfiltration",
                    "connector": "microsoft_defender",
                    "action": "enrich_defender_incidents_and_alerts",
                    "priority": "high",
                    "rationale": "Les incidents corrélés peuvent relier activité cloud, endpoint et identité.",
                    "required_inputs": ["query"],
                    "source": "microsoft_defender.incidents",
                },
                {
                    "recommendation_id": "sentinel-exfil-cloud-activity",
                    "title": "Analyser l'activité cloud volumineuse du compte",
                    "connector": "microsoft_sentinel",
                    "action": "render_and_run_kql_template",
                    "priority": "high",
                    "rationale": "L'exfiltration exige de qualifier volume, objet, application et temporalité.",
                    "required_inputs": ["account"],
                    "sentinel_template_id": "data-exfil-cloud-activity",
                    "source": "microsoft_sentinel.kql",
                },
            ],
            "critical_vulnerability": [
                {
                    "recommendation_id": "sentinel-critical-cve-exposure",
                    "title": "Identifier les appareils exposés à la CVE",
                    "connector": "microsoft_sentinel",
                    "action": "render_and_run_kql_template",
                    "priority": "high",
                    "rationale": "La priorité dépend du nombre d'actifs exposés, de la criticité et de la disponibilité du correctif.",
                    "required_inputs": ["cve_id"],
                    "sentinel_template_id": "critical-cve-device-exposure",
                    "source": "microsoft_sentinel.kql",
                },
                {
                    "recommendation_id": "defender-vulnerability-incidents",
                    "title": "Chercher les alertes Defender autour de la CVE ou de l'actif",
                    "connector": "microsoft_defender",
                    "action": "enrich_defender_incidents_and_alerts",
                    "priority": "medium",
                    "rationale": "Une vulnérabilité exposée devient plus urgente si des alertes ou incidents suggèrent exploitation.",
                    "required_inputs": ["query"],
                    "source": "microsoft_defender.alerts_v2",
                },
            ],
            "general": [
                {
                    "recommendation_id": "defender-general-alerts",
                    "title": "Chercher les alertes Defender avec un indicateur du dossier",
                    "connector": "microsoft_defender",
                    "action": "enrich_defender_alerts",
                    "priority": "medium",
                    "rationale": "Quand la catégorie est incertaine, commencer par une recherche large mais lisible évite d'inventer une piste.",
                    "required_inputs": ["query"],
                    "source": "microsoft_defender.alerts_v2",
                },
            ],
        }
        source_flags = cls._source_flags(detail)
        return [
            cls._recommendation_from_spec(spec, indicators, source_flags)
            for spec in recommendations_by_category[category]
        ]

    @staticmethod
    def _source_flags(detail: InvestigationCaseDetail) -> set[str]:
        return {evidence.source or "" for evidence in detail.evidence}

    @staticmethod
    def _recommendation_from_spec(
        spec: dict[str, object],
        indicators: dict[str, str],
        source_flags: set[str],
    ) -> InvestigationEnrichmentRecommendation:
        required_inputs = list(spec.get("required_inputs", []))
        suggested_parameters = {
            name: indicators[name]
            for name in required_inputs
            if name in indicators
        }
        if "query" in required_inputs:
            suggested_parameters["query"] = (
                indicators.get("user_principal_name")
                or indicators.get("device_name")
                or indicators.get("cve_id")
                or indicators.get("url_fragment")
                or ""
            )
        missing_inputs = [name for name in required_inputs if not suggested_parameters.get(name)]
        return InvestigationEnrichmentRecommendation(
            recommendation_id=str(spec["recommendation_id"]),
            title=str(spec["title"]),
            connector=str(spec["connector"]),
            action=str(spec["action"]),
            priority=spec["priority"],  # type: ignore[arg-type]
            rationale=str(spec["rationale"]),
            required_inputs=missing_inputs,
            suggested_parameters=suggested_parameters,
            sentinel_template_id=spec.get("sentinel_template_id"),  # type: ignore[arg-type]
            already_enriched=str(spec.get("source", "")) in source_flags,
        )

    @staticmethod
    def _incident_headline(
        category: InvestigationEnrichmentCategory,
        detail: InvestigationCaseDetail,
    ) -> str:
        title = detail.case.title
        headlines = {
            "account_compromise": f"Compromission de compte possible — {title}",
            "phishing": f"Exposition phishing à qualifier — {title}",
            "malware": f"Exécution suspecte / malware à reconstruire — {title}",
            "data_exfiltration": f"Exfiltration potentielle à mesurer — {title}",
            "critical_vulnerability": f"Vulnérabilité critique à prioriser — {title}",
            "general": f"Investigation générale — {title}",
        }
        return headlines[category]

    @classmethod
    def _incident_sections(
        cls,
        category: InvestigationEnrichmentCategory,
        detail: InvestigationCaseDetail,
        indicators: dict[str, str],
    ) -> list[InvestigationIncidentViewSection]:
        established = cls._established_sections(detail)
        scenario_sections = {
            "account_compromise": [
                cls._indicator_section(
                    "Identité ciblée",
                    indicators,
                    ("user_principal_name",),
                    "Aucun UPN détecté dans le dossier.",
                ),
                cls._source_section(
                    "Signaux identité",
                    detail,
                    ("microsoft_entra_id.sign_ins", "microsoft_entra_id.risky_users"),
                    "Aucun fait Entra ID encore ajouté.",
                ),
                cls._source_section(
                    "Corrélation détection",
                    detail,
                    ("microsoft_defender.alerts_v2", "microsoft_sentinel.kql"),
                    "Aucune corrélation Defender/Sentinel encore présente.",
                ),
            ],
            "phishing": [
                cls._indicator_section(
                    "Indicateurs email / URL",
                    indicators,
                    ("recipient", "url_fragment"),
                    "Aucun destinataire ou fragment URL détecté.",
                ),
                cls._source_section(
                    "Exposition utilisateur",
                    detail,
                    ("microsoft_defender.alerts_v2", "microsoft_sentinel.kql"),
                    "Aucun événement de livraison/clic encore ajouté.",
                ),
            ],
            "malware": [
                cls._indicator_section(
                    "Machine ou artefact",
                    indicators,
                    ("device_name",),
                    "Aucun nom de machine détecté.",
                ),
                cls._source_section(
                    "Chaîne d'exécution",
                    detail,
                    ("microsoft_defender.alerts_v2", "microsoft_sentinel.kql"),
                    "Aucune chaîne de processus encore ajoutée.",
                ),
            ],
            "data_exfiltration": [
                cls._indicator_section(
                    "Compte ou périmètre",
                    indicators,
                    ("account", "user_principal_name"),
                    "Aucun compte ou périmètre détecté.",
                ),
                cls._source_section(
                    "Mesure de l'activité",
                    detail,
                    ("microsoft_defender.incidents", "microsoft_sentinel.kql"),
                    "Aucune mesure d'activité cloud ou incident corrélé.",
                ),
            ],
            "critical_vulnerability": [
                cls._indicator_section(
                    "Vulnérabilité",
                    indicators,
                    ("cve_id",),
                    "Aucun identifiant CVE détecté.",
                ),
                cls._source_section(
                    "Exposition et exploitation",
                    detail,
                    ("microsoft_sentinel.kql", "microsoft_defender.alerts_v2"),
                    "Aucune exposition d'actif ou alerte d'exploitation ajoutée.",
                ),
            ],
            "general": [
                cls._indicator_section(
                    "Indicateurs détectés",
                    indicators,
                    ("user_principal_name", "device_name", "cve_id", "url_fragment"),
                    "Aucun indicateur structuré détecté.",
                ),
            ],
        }
        return established + scenario_sections[category]

    @staticmethod
    def _established_sections(detail: InvestigationCaseDetail) -> list[InvestigationIncidentViewSection]:
        return [
            InvestigationIncidentViewSection(
                title="État du dossier",
                status="ok" if detail.evidence or detail.events else "attention",
                items=[
                    f"{len(detail.evidence)} preuve(s)",
                    f"{len(detail.events)} événement(s) de timeline",
                    f"{detail.summary.done_checks}/{detail.summary.total_checks} vérification(s) terminée(s)",
                    f"{detail.summary.open_hypotheses} hypothèse(s) ouverte(s)",
                ],
            )
        ]

    @staticmethod
    def _indicator_section(
        title: str,
        indicators: dict[str, str],
        names: tuple[str, ...],
        missing_message: str,
    ) -> InvestigationIncidentViewSection:
        items = [f"{name}: {indicators[name]}" for name in names if indicators.get(name)]
        return InvestigationIncidentViewSection(
            title=title,
            status="ok" if items else "missing",
            items=items or [missing_message],
        )

    @staticmethod
    def _source_section(
        title: str,
        detail: InvestigationCaseDetail,
        sources: tuple[str, ...],
        missing_message: str,
    ) -> InvestigationIncidentViewSection:
        matching = [
            evidence.title
            for evidence in detail.evidence
            if evidence.source in sources
        ]
        return InvestigationIncidentViewSection(
            title=title,
            status="ok" if matching else "attention",
            items=matching[:5] or [missing_message],
        )

    @staticmethod
    def _next_questions(
        category: InvestigationEnrichmentCategory,
        indicators: dict[str, str],
    ) -> list[str]:
        questions = {
            "account_compromise": [
                "Les connexions suspectes sont-elles cohérentes avec l'utilisateur et ses habitudes ?",
                "Y a-t-il eu changement MFA, consentement OAuth ou réinitialisation de mot de passe ?",
                "Le compte a-t-il déclenché des alertes Defender ou Sentinel dans la même fenêtre ?",
            ],
            "phishing": [
                "Le message a-t-il été livré, bloqué ou cliqué ?",
                "Combien de destinataires sont exposés au même expéditeur, domaine ou URL ?",
                "Faut-il purger le message ou réinitialiser des identifiants ?",
            ],
            "malware": [
                "Quelle est la chaîne parent/enfant du processus suspect ?",
                "Le hash, la ligne de commande ou le comportement indique-t-il une persistance ?",
                "D'autres hôtes montrent-ils le même artefact ?",
            ],
            "data_exfiltration": [
                "Quel volume, quelle destination et quelle fenêtre temporelle sont concernés ?",
                "Le comportement est-il attendu pour ce compte ou cette application ?",
                "Des liens publics, partages externes ou téléchargements massifs sont-ils présents ?",
            ],
            "critical_vulnerability": [
                "Quels actifs sont réellement exposés à la CVE ?",
                "Existe-t-il des signaux d'exploitation ou seulement une exposition théorique ?",
                "Quel patch ou contrôle compensatoire réduit le risque le plus vite ?",
            ],
            "general": [
                "Quel indicateur pivot faut-il stabiliser en premier ?",
                "Quelles preuves manquent pour séparer faits et hypothèses ?",
                "Quel connecteur peut confirmer ou infirmer la piste principale ?",
            ],
        }
        if not indicators:
            return ["Ajouter au moins un indicateur pivot : compte, machine, URL, hash ou CVE."] + questions[category]
        return questions[category]

    @classmethod
    def _soc_score(
        cls,
        detail: InvestigationCaseDetail,
        category: InvestigationEnrichmentCategory,
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        category_weights: dict[InvestigationEnrichmentCategory, int] = {
            "critical_vulnerability": 30,
            "data_exfiltration": 30,
            "malware": 28,
            "account_compromise": 26,
            "phishing": 22,
            "general": 12,
        }
        category_score = category_weights[category]
        score += category_score
        reasons.append(f"Scénario {category} (+{category_score})")

        if detail.case.status == "open":
            score += 15
            reasons.append("Dossier ouvert (+15)")
        elif detail.case.status == "monitoring":
            score += 8
            reasons.append("Dossier en surveillance (+8)")

        if not detail.evidence:
            score += 25
            reasons.append("Aucune preuve ajoutée (+25)")
        elif len(detail.evidence) < 2:
            score += 10
            reasons.append("Peu de preuves disponibles (+10)")

        if not detail.events:
            score += 10
            reasons.append("Timeline vide (+10)")

        if detail.summary.open_hypotheses:
            score += min(15, detail.summary.open_hypotheses * 5)
            reasons.append("Hypothèses ouvertes à trancher")

        if detail.summary.total_checks:
            todo_ratio = detail.summary.todo_checks / detail.summary.total_checks
            todo_score = round(todo_ratio * 15)
            if todo_score:
                score += todo_score
                reasons.append(f"Checklist encore ouverte (+{todo_score})")

        return min(score, 100), reasons

    @staticmethod
    def _soc_priority(score: int) -> str:
        if score >= 75:
            return "critical"
        if score >= 55:
            return "high"
        if score >= 30:
            return "medium"
        return "low"

    @staticmethod
    def _soc_next_action(
        detail: InvestigationCaseDetail,
        category: InvestigationEnrichmentCategory,
    ) -> str:
        if not detail.evidence:
            return "Proposer puis exécuter un enrichissement ciblé."
        if not detail.events and category != "critical_vulnerability":
            return "Ajouter ou enrichir la timeline avant conclusion."
        if detail.summary.open_hypotheses:
            return "Qualifier les hypothèses ouvertes avec les preuves existantes."
        if detail.summary.todo_checks:
            return "Terminer les vérifications restantes de la checklist."
        return "Préparer la synthèse ou le rapport final."

    @staticmethod
    def _shift_headline(queue: InvestigationSOCQueueResponse) -> str:
        critical = sum(item.priority == "critical" for item in queue.items)
        high = sum(item.priority == "high" for item in queue.items)
        if not queue.active_cases:
            return "Aucun dossier actif dans la file SOC."
        if critical:
            return f"{critical} dossier(s) critique(s) à traiter en priorité."
        if high:
            return f"{high} dossier(s) à priorité haute pour ce quart."
        return f"{queue.active_cases} dossier(s) actif(s), aucun critique immédiat."

    @staticmethod
    def _shift_guidance(
        queue: InvestigationSOCQueueResponse,
        focus_now: list[InvestigationSOCQueueItem],
        blocked_or_under_evidenced: list[InvestigationSOCQueueItem],
        ready_for_report: list[InvestigationSOCQueueItem],
    ) -> list[str]:
        guidance: list[str] = []
        if focus_now:
            guidance.append("Commencer par les dossiers critiques/hauts et vérifier qu'un enrichissement ciblé est lancé ou planifié.")
        if blocked_or_under_evidenced:
            guidance.append("Réduire les angles morts : ajouter preuves ou timeline avant de conclure.")
        if ready_for_report:
            guidance.append("Clore la boucle sur les dossiers mûrs : générer synthèse ou rapport final.")
        if queue.active_cases and not guidance:
            guidance.append("Maintenir la surveillance et traiter les vérifications restantes par ordre de score.")
        if not queue.active_cases:
            guidance.append("Aucune action immédiate : préparer les watchlists, playbooks ou revues de détection.")
        return guidance

    @classmethod
    def _sla_findings(
        cls,
        item: InvestigationSOCQueueItem,
        age_minutes: int,
        idle_minutes: int,
    ) -> tuple[list[str], list[str]]:
        breaches: list[str] = []
        warnings: list[str] = []

        if item.priority == "critical":
            cls._threshold(
                age_minutes,
                warning=45,
                breach=60,
                label="Dossier critique ouvert depuis trop longtemps",
                warnings=warnings,
                breaches=breaches,
            )
        elif item.priority == "high":
            cls._threshold(
                age_minutes,
                warning=180,
                breach=240,
                label="Dossier haute priorité vieillissant",
                warnings=warnings,
                breaches=breaches,
            )

        if item.evidence_count == 0:
            cls._threshold(
                age_minutes,
                warning=15,
                breach=30,
                label="Aucune preuve ajoutée",
                warnings=warnings,
                breaches=breaches,
            )

        if item.event_count == 0 and item.inferred_category != "critical_vulnerability":
            cls._threshold(
                age_minutes,
                warning=30,
                breach=90,
                label="Timeline vide",
                warnings=warnings,
                breaches=breaches,
            )

        ready_for_report = (
            item.evidence_count > 0
            and item.open_hypotheses == 0
            and item.todo_checks == 0
            and item.priority in ("low", "medium")
        )
        if ready_for_report:
            cls._threshold(
                idle_minutes,
                warning=120,
                breach=240,
                label="Dossier prêt pour rapport mais inactif",
                warnings=warnings,
                breaches=breaches,
            )

        return breaches, warnings

    @staticmethod
    def _threshold(
        value: int,
        *,
        warning: int,
        breach: int,
        label: str,
        warnings: list[str],
        breaches: list[str],
    ) -> None:
        if value >= breach:
            breaches.append(f"{label} ({value} min)")
        elif value >= warning:
            warnings.append(f"{label} ({value} min)")

    @staticmethod
    def _sla_next_action(
        item: InvestigationSOCQueueItem,
        breaches: list[str],
        warnings: list[str],
    ) -> str:
        findings = " ".join(breaches + warnings).casefold()
        if "aucune preuve" in findings:
            return "Ajouter une preuve ou lancer un enrichissement ciblé immédiatement."
        if "timeline vide" in findings:
            return "Créer une première timeline factuelle avant conclusion."
        if "rapport" in findings:
            return "Générer la synthèse ou le rapport final."
        if item.priority in ("critical", "high"):
            return "Réviser ce dossier en priorité pendant le quart."
        return item.next_action

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _minutes_between(start: datetime, end: datetime) -> int:
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        return max(0, int((end - start).total_seconds() // 60))

    @classmethod
    def _closure_checks(cls, detail: InvestigationCaseDetail) -> list[InvestigationClosureCheck]:
        return [
            cls._closure_check(
                "Preuves",
                passed=bool(detail.evidence),
                attention=False,
                passed_detail=f"{len(detail.evidence)} preuve(s) disponible(s).",
                missing_detail="Ajouter au moins une preuve sourcée avant clôture.",
            ),
            cls._closure_check(
                "Timeline",
                passed=bool(detail.events),
                attention=False,
                passed_detail=f"{len(detail.events)} événement(s) dans la timeline.",
                missing_detail="Ajouter au moins un événement factuel à la timeline.",
            ),
            cls._closure_check(
                "Hypothèses",
                passed=detail.summary.open_hypotheses == 0,
                attention=detail.summary.supported_hypotheses == 0 and detail.summary.rejected_hypotheses == 0,
                passed_detail="Aucune hypothèse ouverte.",
                missing_detail="Trancher les hypothèses ouvertes avant clôture.",
                attention_detail="Aucune hypothèse formalisée ; acceptable si le dossier est purement factuel.",
            ),
            cls._closure_check(
                "Checklist",
                passed=detail.summary.todo_checks == 0 and detail.summary.blocked_checks == 0,
                attention=detail.summary.blocked_checks > 0,
                passed_detail="Aucune vérification restante.",
                missing_detail="Terminer les vérifications restantes ou documenter leur abandon.",
                attention_detail="Des vérifications sont bloquées ; documenter le risque résiduel.",
            ),
            cls._closure_check(
                "Décision",
                passed=bool(detail.notes) or bool(detail.hypotheses),
                attention=False,
                passed_detail="Une note ou une hypothèse documente la décision.",
                missing_detail="Ajouter une note de décision : vrai positif, faux positif, surveillance ou escalade.",
            ),
        ]

    @staticmethod
    def _closure_check(
        title: str,
        *,
        passed: bool,
        attention: bool,
        passed_detail: str,
        missing_detail: str,
        attention_detail: str | None = None,
    ) -> InvestigationClosureCheck:
        if passed:
            return InvestigationClosureCheck(title=title, status="passed", detail=passed_detail)
        if attention:
            return InvestigationClosureCheck(
                title=title,
                status="attention",
                detail=attention_detail or missing_detail,
            )
        return InvestigationClosureCheck(title=title, status="missing", detail=missing_detail)

    @staticmethod
    def _closure_score(checks: list[InvestigationClosureCheck]) -> int:
        if not checks:
            return 0
        points = {"passed": 20, "attention": 10, "missing": 0}
        return min(100, sum(points[check.status] for check in checks))

    @staticmethod
    def _closure_headline(
        detail: InvestigationCaseDetail,
        state: str,
        readiness_score: int,
    ) -> str:
        if state == "already_closed":
            return f"Dossier déjà clos — score de complétude {readiness_score}%."
        if state == "ready":
            return f"Dossier prêt pour clôture contrôlée — score {readiness_score}%."
        return f"Dossier pas encore prêt pour clôture — score {readiness_score}%."

    @staticmethod
    def _closure_next_action(
        state: str,
        blockers: list[str],
        checks: list[InvestigationClosureCheck],
    ) -> str:
        if state == "already_closed":
            return "Relire le rapport ou rouvrir seulement si un fait nouveau apparaît."
        if state == "ready":
            return "Générer le rapport final, relire la décision, puis clôturer manuellement si conforme."
        if blockers:
            return blockers[0]
        attention = next((check.detail for check in checks if check.status == "attention"), None)
        return attention or "Compléter les éléments restants avant clôture."

    @staticmethod
    def _add_sign_in_events(
        user_id: str,
        case_id: str,
        detail: InvestigationCaseDetail,
        sign_ins: list[EntraSignIn],
    ) -> int:
        existing_event_keys = {(item.occurred_at, item.title) for item in detail.events}
        added = 0
        for sign_in in sign_ins:
            if sign_in.created_at is None:
                continue
            title = f"Connexion Entra ID — {sign_in.user_principal_name or 'utilisateur inconnu'}"
            event_key = (sign_in.created_at, title)
            if event_key in existing_event_keys:
                continue
            description_parts = [
                f"Application : {sign_in.app_display_name}" if sign_in.app_display_name else None,
                f"IP : {sign_in.ip_address}" if sign_in.ip_address else None,
                f"Localisation : {InvestigationEnrichmentService._location(sign_in)}"
                if InvestigationEnrichmentService._location(sign_in)
                else None,
                f"Client : {sign_in.client_app_used}" if sign_in.client_app_used else None,
                f"Statut CA : {sign_in.conditional_access_status}"
                if sign_in.conditional_access_status
                else None,
                f"Risque agrégé : {sign_in.risk_level_aggregated}"
                if sign_in.risk_level_aggregated
                else None,
                f"Échec : {sign_in.failure_reason}" if sign_in.failure_reason else None,
            ]
            investigation_case_store.add_event(
                user_id,
                case_id,
                InvestigationCaseEventCreateRequest(
                    occurred_at=sign_in.created_at,
                    title=title,
                    description=" | ".join(part for part in description_parts if part),
                ),
            )
            existing_event_keys.add(event_key)
            added += 1
        return added

    @staticmethod
    def _add_evidence(
        user_id: str,
        case_id: str,
        detail: InvestigationCaseDetail,
        user_principal_name: str,
        sign_ins: list[EntraSignIn],
        risky_users: list[EntraRiskyUser],
    ) -> int:
        existing_titles = {item.title for item in detail.evidence}
        added = 0
        sign_in_title = f"Entra ID — {len(sign_ins)} connexion(s) examinée(s) pour {user_principal_name}"
        if sign_ins and sign_in_title not in existing_titles:
            latest = sign_ins[0]
            investigation_case_store.add_evidence(
                user_id,
                case_id,
                InvestigationCaseEvidenceCreateRequest(
                    title=sign_in_title,
                    description=(
                        "Synthèse issue des journaux de connexion Entra ID. "
                        f"Dernière connexion observée : {latest.created_at or 'inconnue'}."
                    ),
                    source="microsoft_entra_id.sign_ins",
                ),
            )
            existing_titles.add(sign_in_title)
            added += 1

        risky_title = f"Entra ID — utilisateur à risque : {user_principal_name}"
        if risky_users and risky_title not in existing_titles:
            strongest = risky_users[0]
            investigation_case_store.add_evidence(
                user_id,
                case_id,
                InvestigationCaseEvidenceCreateRequest(
                    title=risky_title,
                    description=(
                        f"Niveau de risque : {strongest.risk_level or 'inconnu'} ; "
                        f"état : {strongest.risk_state or 'inconnu'} ; "
                        f"détail : {strongest.risk_detail or 'non fourni'}."
                    ),
                    source="microsoft_entra_id.risky_users",
                ),
            )
            added += 1
        return added

    @staticmethod
    def _add_defender_alert_events(
        user_id: str,
        case_id: str,
        detail: InvestigationCaseDetail,
        alerts: list[DefenderAlert],
    ) -> int:
        existing_event_keys = {(item.occurred_at, item.title) for item in detail.events}
        added = 0
        for alert in alerts:
            occurred_at = alert.first_activity_at or alert.created_at
            if occurred_at is None:
                continue
            title = f"Alerte Defender — {alert.title or alert.alert_id}"
            event_key = (occurred_at, title)
            if event_key in existing_event_keys:
                continue
            investigation_case_store.add_event(
                user_id,
                case_id,
                InvestigationCaseEventCreateRequest(
                    occurred_at=occurred_at,
                    title=title,
                    description=(
                        f"Sévérité : {alert.severity or 'inconnue'} | "
                        f"Source : {alert.service_source or 'inconnue'} | "
                        f"Détection : {alert.detection_source or 'inconnue'} | "
                        f"Incident : {alert.incident_id or 'non lié'}"
                    ),
                ),
            )
            existing_event_keys.add(event_key)
            added += 1
        return added

    @staticmethod
    def _add_defender_evidence(
        user_id: str,
        case_id: str,
        detail: InvestigationCaseDetail,
        incidents: list[DefenderIncident],
        alerts: list[DefenderAlert],
    ) -> int:
        existing_titles = {item.title for item in detail.evidence}
        added = 0
        for incident in incidents:
            title = f"Defender — incident {incident.incident_id}: {incident.display_name or 'sans titre'}"
            if title in existing_titles:
                continue
            investigation_case_store.add_evidence(
                user_id,
                case_id,
                InvestigationCaseEvidenceCreateRequest(
                    title=title,
                    description=(
                        f"Statut : {incident.status or 'inconnu'} ; "
                        f"sévérité : {incident.severity or 'inconnue'} ; "
                        f"classification : {incident.classification or 'inconnue'}."
                    ),
                    source="microsoft_defender.incidents",
                ),
            )
            existing_titles.add(title)
            added += 1

        for alert in alerts:
            title = f"Defender — alerte {alert.alert_id}: {alert.title or 'sans titre'}"
            if title in existing_titles:
                continue
            investigation_case_store.add_evidence(
                user_id,
                case_id,
                InvestigationCaseEvidenceCreateRequest(
                    title=title,
                    description=(
                        f"Statut : {alert.status or 'inconnu'} ; "
                        f"sévérité : {alert.severity or 'inconnue'} ; "
                        f"source : {alert.service_source or 'inconnue'} ; "
                        f"preuves associées : {alert.evidence_count}."
                    ),
                    source="microsoft_defender.alerts_v2",
                ),
            )
            existing_titles.add(title)
            added += 1
        return added

    @staticmethod
    def _filter_incidents(
        incidents: list[DefenderIncident],
        query: str | None,
    ) -> list[DefenderIncident]:
        if not query:
            return incidents
        normalized_query = query.casefold()
        return [
            incident
            for incident in incidents
            if normalized_query
            in " ".join(
                value or ""
                for value in (
                    incident.incident_id,
                    incident.display_name,
                    incident.status,
                    incident.severity,
                    incident.classification,
                    incident.determination,
                    incident.assigned_to,
                )
            ).casefold()
        ]

    @staticmethod
    def _filter_alerts(alerts: list[DefenderAlert], query: str | None) -> list[DefenderAlert]:
        if not query:
            return alerts
        normalized_query = query.casefold()
        return [
            alert
            for alert in alerts
            if normalized_query
            in " ".join(
                value or ""
                for value in (
                    alert.alert_id,
                    alert.provider_alert_id,
                    alert.incident_id,
                    alert.title,
                    alert.description,
                    alert.status,
                    alert.severity,
                    alert.service_source,
                    alert.detection_source,
                )
            ).casefold()
        ]

    @staticmethod
    def _add_sentinel_events(
        user_id: str,
        case_id: str,
        detail: InvestigationCaseDetail,
        query_result: SentinelQueryResult,
        max_events: int,
    ) -> int:
        existing_event_keys = {(item.occurred_at, item.title) for item in detail.events}
        added = 0
        for row in query_result.rows[:max_events]:
            occurred_at = InvestigationEnrichmentService._first_value(
                row,
                ("TimeGenerated", "Timestamp", "CreatedTime", "StartTime", "EventTime"),
            )
            if occurred_at is None:
                continue
            title_value = InvestigationEnrichmentService._first_value(
                row,
                ("AlertName", "Title", "OperationName", "Activity", "Computer", "Account", "UserPrincipalName"),
            )
            title = f"Résultat Sentinel — {title_value or 'événement KQL'}"
            event_key = (str(occurred_at), title)
            if event_key in existing_event_keys:
                continue
            investigation_case_store.add_event(
                user_id,
                case_id,
                InvestigationCaseEventCreateRequest(
                    occurred_at=str(occurred_at),
                    title=title,
                    description=InvestigationEnrichmentService._compact_row(row),
                ),
            )
            existing_event_keys.add(event_key)
            added += 1
        return added

    @staticmethod
    def _add_sentinel_evidence(
        user_id: str,
        case_id: str,
        detail: InvestigationCaseDetail,
        query_result: SentinelQueryResult,
        payload: InvestigationCaseSentinelEnrichmentRequest,
    ) -> int:
        title = payload.evidence_title or "Sentinel — résultat de requête KQL"
        if title in {item.title for item in detail.evidence}:
            return 0
        preview_rows = query_result.rows[:3]
        preview = "\n".join(
            f"- {InvestigationEnrichmentService._compact_row(row)}" for row in preview_rows
        )
        description = (
            f"Requête KQL exécutée en lecture seule. Lignes retournées : {query_result.row_count}. "
            f"Colonnes : {', '.join(query_result.columns) or 'aucune'}."
        )
        if preview:
            description = f"{description}\nAperçu limité :\n{preview}"
        investigation_case_store.add_evidence(
            user_id,
            case_id,
            InvestigationCaseEvidenceCreateRequest(
                title=title,
                description=description,
                source="microsoft_sentinel.kql",
            ),
        )
        return 1

    @staticmethod
    def _first_value(row: dict[str, object | None], keys: tuple[str, ...]) -> object | None:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _compact_row(row: dict[str, object | None]) -> str:
        preferred_keys = (
            "TimeGenerated",
            "AlertName",
            "Title",
            "Computer",
            "Account",
            "UserPrincipalName",
            "IPAddress",
            "IP",
            "ResultType",
            "Activity",
        )
        items = [(key, row.get(key)) for key in preferred_keys if row.get(key) not in (None, "")]
        if not items:
            items = [(key, value) for key, value in list(row.items())[:6] if value not in (None, "")]
        return " | ".join(f"{key}: {value}" for key, value in items)

    @staticmethod
    def _location(sign_in: EntraSignIn) -> str | None:
        parts = [part for part in (sign_in.city, sign_in.country_or_region) if part]
        return ", ".join(parts) if parts else None


investigation_enrichment_service = InvestigationEnrichmentService()
