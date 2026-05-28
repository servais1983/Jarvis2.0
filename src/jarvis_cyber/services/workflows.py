from jarvis_cyber.core.prompts import (
    ALERT_INVESTIGATION_PROMPT,
    ALERT_TRIAGE_PROMPT,
    CVE_SUMMARY_PROMPT,
    INCIDENT_REPORT_PROMPT,
    INVESTIGATION_PROGRESS_PROMPT,
)
from jarvis_cyber.core.schemas import (
    AlertInvestigationRequest,
    AlertInvestigationResult,
    AlertTriageRequest,
    AlertTriageResult,
    ConnectorDigestAutomationPayload,
    ConnectorDigestResponse,
    CVEEnrichmentRequest,
    CVERecord,
    CVESummaryRequest,
    CVESummaryResult,
    InvestigationProfile,
    InvestigationCaseDetail,
    InvestigationProgressSummaryResult,
    IncidentReportRequest,
    IncidentReportResult,
)
from jarvis_cyber.integrations.nvd import nvd_client
from jarvis_cyber.investigation_profiles.store import investigation_profile_store
from jarvis_cyber.knowledge.store import knowledge_store
from jarvis_cyber.playbooks.store import playbook_store
from jarvis_cyber.services.assistant import assistant_service
from jarvis_cyber.services.connector_digest import connector_digest_service


class CyberWorkflowService:
    """First cyber-specific workflows for the MVP."""

    def summarize_cve(self, payload: CVESummaryRequest) -> tuple[CVESummaryResult, str, bool]:
        label = payload.cve_id or "CVE non précisée"
        input_text = f"Identifiant : {label}\n\nSource :\n{payload.source_text}"
        return assistant_service.complete_structured(
            CVE_SUMMARY_PROMPT,
            input_text,
            CVESummaryResult,
            lambda: CVESummaryResult(
                cve_id=payload.cve_id,
                executive_summary="Analyse prête mais modèle distant non configuré.",
                affected_products=[],
                technical_impact="À déterminer à partir de la source fournie.",
                urgency="unknown",
                exploitation_signals=[],
                recommended_actions=[
                    "Configurer OPENAI_API_KEY pour générer une analyse complète.",
                    "Vérifier manuellement les produits et versions affectés.",
                ],
                uncertainties=["Le mode local ne produit pas encore d'analyse sémantique complète."],
                confidence="low",
            ),
        )

    def enrich_cve(
        self,
        payload: CVEEnrichmentRequest,
    ) -> tuple[CVERecord, CVESummaryResult, str, bool]:
        record = nvd_client.fetch_cve(payload.cve_id)
        source_text = self._build_cve_source(record)
        analysis, model, used_remote_model = self.summarize_cve(
            CVESummaryRequest(cve_id=record.cve_id, source_text=source_text)
        )
        return record, analysis, model, used_remote_model

    def triage_alert(self, payload: AlertTriageRequest) -> tuple[AlertTriageResult, str, bool]:
        context = payload.environment_context or "Aucun contexte d'environnement fourni."
        input_text = (
            f"Titre : {payload.title}\n\n"
            f"Alerte brute :\n{payload.raw_alert}\n\n"
            f"Contexte d'environnement :\n{context}"
        )
        return assistant_service.complete_structured(
            ALERT_TRIAGE_PROMPT,
            input_text,
            AlertTriageResult,
            lambda: AlertTriageResult(
                classification="unknown",
                observed_facts=[f"Alerte reçue : {payload.title}"],
                hypotheses=[],
                priority_checks=["Configurer OPENAI_API_KEY pour obtenir un triage complet."],
                severity="unknown",
                decision="investigate",
                rationale="Le mode local conserve la structure mais n'infère pas encore le fond.",
                confidence="low",
            ),
        )

    def investigate_alert(
        self,
        user_id: str,
        payload: AlertInvestigationRequest,
    ) -> tuple[
        AlertInvestigationResult,
        str,
        bool,
        list,
        list,
        ConnectorDigestResponse,
        InvestigationProfile | None,
    ]:
        base_query = " ".join(
            part
            for part in [
                payload.title,
                payload.raw_alert,
                payload.environment_context or "",
                payload.goal or "",
            ]
            if part
        )
        explicit_profile = (
            investigation_profile_store.get(user_id, payload.investigation_profile_id)
            if payload.investigation_profile_id
            else None
        )
        profile_matches = (
            investigation_profile_store.search(user_id, base_query, limit=1)
            if explicit_profile is None
            else []
        )
        inferred_profile = profile_matches[0].profile if profile_matches else None
        applied_profile = explicit_profile or inferred_profile
        effective_goal = payload.goal or (applied_profile.default_goal if applied_profile else None)
        effective_include_recent_github = (
            payload.include_recent_github
            or (applied_profile.include_recent_github if applied_profile else False)
        )
        effective_drive_query = payload.drive_query or (applied_profile.drive_query if applied_profile else None)
        effective_jira_jql = payload.jira_jql or (applied_profile.jira_jql if applied_profile else None)
        effective_query = " ".join(
            part
            for part in [
                payload.title,
                payload.raw_alert,
                payload.environment_context or "",
                effective_goal or "",
            ]
            if part
        )

        knowledge_hits = knowledge_store.search(user_id, effective_query, limit=3)
        knowledge_chunks = knowledge_store.chunks_for_results(user_id, knowledge_hits)
        playbook_hits = playbook_store.search_playbooks(user_id, effective_query, limit=3)
        external_context = connector_digest_service.build(
            ConnectorDigestAutomationPayload(
                include_github=effective_include_recent_github,
                include_google_drive=effective_drive_query is not None,
                include_jira=effective_jira_jql is not None,
                drive_query=effective_drive_query,
                jira_jql=effective_jira_jql,
            )
        )
        triage, _, _ = self.triage_alert(
            AlertTriageRequest(
                title=payload.title,
                raw_alert=payload.raw_alert,
                environment_context=payload.environment_context,
            )
        )
        context_block = (
            "\n\n".join(f"- {chunk.title}: {chunk.content}" for chunk in knowledge_chunks)
            if knowledge_chunks
            else "Aucun contexte documentaire pertinent."
        )
        playbook_block = (
            "\n\n".join(f"- {hit.playbook.title}: {hit.playbook.steps}" for hit in playbook_hits)
            if playbook_hits
            else "Aucun playbook pertinent."
        )
        external_context_block = self._format_external_context(external_context)
        recommended_checks_block = (
            applied_profile.recommended_checks
            if applied_profile and applied_profile.recommended_checks
            else "Aucune checklist spécifique."
        )
        input_text = (
            f"Titre : {payload.title}\n\n"
            f"Alerte brute :\n{payload.raw_alert}\n\n"
            f"Contexte d'environnement :\n{payload.environment_context or 'Non fourni.'}\n\n"
            f"Profil d'investigation appliqué :\n{applied_profile.name if applied_profile else 'Aucun.'}\n\n"
            f"Objectif de l'analyste :\n{effective_goal or 'Non précisé.'}\n\n"
            f"Checklist recommandée par le profil :\n{recommended_checks_block}\n\n"
            f"Triage initial déjà établi :\n{triage.model_dump_json()}\n\n"
            f"Contexte documentaire interne :\n{context_block}\n\n"
            f"Playbooks personnels pertinents :\n{playbook_block}\n\n"
            f"Contexte externe fourni par les connecteurs :\n{external_context_block}"
        )
        result, model, used_remote_model = assistant_service.complete_structured(
            ALERT_INVESTIGATION_PROMPT,
            input_text,
            AlertInvestigationResult,
            lambda: AlertInvestigationResult(
                executive_summary="Investigation structurée prête mais modèle distant non configuré.",
                triage=triage,
                context_findings=[
                    f"{len(knowledge_hits)} extrait(s) documentaire(s) pertinent(s) retrouvé(s).",
                    self._external_context_summary(external_context),
                ],
                matched_playbooks=[hit.playbook.title for hit in playbook_hits],
                priority_checks=triage.priority_checks,
                recommended_actions=[
                    "Configurer OPENAI_API_KEY pour produire une investigation enrichie.",
                    "Valider manuellement les vérifications prioritaires proposées.",
                ],
                suggested_watchlist=None,
                uncertainties=["Le mode local n'infère pas encore les corrélations avancées."],
                confidence="low",
            ),
        )
        return (
            result,
            model,
            used_remote_model,
            knowledge_hits,
            playbook_hits,
            external_context,
            applied_profile,
        )

    def draft_incident_report(
        self,
        payload: IncidentReportRequest,
    ) -> tuple[IncidentReportResult, str, bool]:
        input_text = (
            f"Résumé :\n{payload.incident_summary}\n\n"
            f"Chronologie :\n{payload.timeline or 'Non fournie.'}\n\n"
            f"Impact :\n{payload.impact or 'Non fourni.'}\n\n"
            f"Actions réalisées :\n{payload.actions_taken or 'Non fournies.'}\n\n"
            f"Questions ouvertes :\n{payload.open_questions or 'Aucune précisée.'}"
        )
        return assistant_service.complete_structured(
            INCIDENT_REPORT_PROMPT,
            input_text,
            IncidentReportResult,
            lambda: IncidentReportResult(
                executive_summary="Brouillon prêt mais modèle distant non configuré.",
                timeline=[payload.timeline] if payload.timeline else [],
                scope_and_impact=payload.impact or "Impact non fourni.",
                probable_cause="À déterminer.",
                actions_taken=[payload.actions_taken] if payload.actions_taken else [],
                recommended_actions=["Configurer OPENAI_API_KEY pour produire un brouillon complet."],
                open_questions=[payload.open_questions] if payload.open_questions else [],
                confidence="low",
            ),
        )

    def summarize_investigation_progress(
        self,
        detail: InvestigationCaseDetail,
    ) -> tuple[InvestigationProgressSummaryResult, str, bool]:
        input_text = (
            f"Dossier : {detail.case.title}\n"
            f"Statut : {detail.case.status}\n"
            f"Objectif : {detail.case.goal or 'Non précisé.'}\n\n"
            f"Checklist :\n"
            + "\n".join(
                f"- {item.status}: {item.title}"
                + (f" | note: {item.notes}" if item.notes else "")
                for item in detail.checklist_items
            )
            + "\n\nTimeline :\n"
            + ("\n".join(f"- {event.occurred_at}: {event.title}" for event in detail.events) or "- Aucune")
            + "\n\nPreuves :\n"
            + ("\n".join(f"- {item.title}" for item in detail.evidence) or "- Aucune")
            + "\n\nHypothèses :\n"
            + (
                "\n".join(f"- {item.status}: {item.statement}" for item in detail.hypotheses)
                or "- Aucune"
            )
            + "\n\nNotes :\n"
            + ("\n".join(f"- {note.body}" for note in detail.notes) or "- Aucune")
        )
        return assistant_service.complete_structured(
            INVESTIGATION_PROGRESS_PROMPT,
            input_text,
            InvestigationProgressSummaryResult,
            lambda: InvestigationProgressSummaryResult(
                executive_summary=(
                    "Synthèse d'avancement prête mais modèle distant non configuré."
                ),
                established_facts=[event.title for event in detail.events],
                supported_hypotheses=[
                    item.statement for item in detail.hypotheses if item.status == "supported"
                ],
                rejected_hypotheses=[
                    item.statement for item in detail.hypotheses if item.status == "rejected"
                ],
                next_actions=detail.summary.next_open_checks,
                uncertainties=[
                    item.statement for item in detail.hypotheses if item.status == "open"
                ],
                confidence="low",
            ),
        )

    def draft_incident_report_from_case(
        self,
        detail: InvestigationCaseDetail,
    ) -> tuple[IncidentReportResult, str, bool]:
        incident_summary = (
            detail.notes[0].body
            if detail.notes
            else f"Dossier d'investigation : {detail.case.title}"
        )
        timeline = "\n".join(
            f"{event.occurred_at} — {event.title}" for event in detail.events
        ) or None
        impact = (
            "\n".join(item.title for item in detail.evidence)
            if detail.evidence
            else None
        )
        actions_taken = "\n".join(
            item.title for item in detail.checklist_items if item.status == "done"
        ) or None
        open_questions = "\n".join(
            item.statement for item in detail.hypotheses if item.status == "open"
        ) or None
        return self.draft_incident_report(
            IncidentReportRequest(
                incident_summary=incident_summary,
                timeline=timeline,
                impact=impact,
                actions_taken=actions_taken,
                open_questions=open_questions,
            )
        )
    @staticmethod
    def _build_cve_source(record: CVERecord) -> str:
        affected = "\n".join(record.affected_criteria) or "Non fourni."
        references = "\n".join(reference.url for reference in record.references[:5]) or "Non fournies."
        return (
            f"Description : {record.description}\n"
            f"Statut : {record.status or 'Non fourni'}\n"
            f"Publié : {record.published or 'Non fourni'}\n"
            f"Modifié : {record.last_modified or 'Non fourni'}\n"
            f"Score CVSS : {record.cvss_score if record.cvss_score is not None else 'Non fourni'}\n"
            f"Sévérité CVSS : {record.cvss_severity or 'Non fournie'}\n"
            f"Connu comme exploité : {'oui' if record.known_exploited else 'non'}\n"
            f"Action requise : {record.required_action or 'Non fournie'}\n"
            f"Critères affectés :\n{affected}\n"
            f"Références :\n{references}"
        )

    @staticmethod
    def _format_external_context(context: ConnectorDigestResponse) -> str:
        sections: list[str] = []
        if context.repositories:
            sections.append(
                "Dépôts GitHub récents :\n"
                + "\n".join(f"- {item.full_name}" for item in context.repositories)
            )
        if context.drive_files:
            sections.append(
                "Fichiers Drive :\n"
                + "\n".join(f"- {item.name}" for item in context.drive_files)
            )
        if context.jira_issues:
            sections.append(
                "Tickets Jira :\n"
                + "\n".join(f"- {item.key}: {item.summary}" for item in context.jira_issues)
            )
        return "\n\n".join(sections) if sections else "Aucun contexte externe demandé ou disponible."

    @staticmethod
    def _external_context_summary(context: ConnectorDigestResponse) -> str:
        return (
            "Contexte externe : "
            f"{len(context.repositories)} dépôt(s), "
            f"{len(context.drive_files)} fichier(s) Drive, "
            f"{len(context.jira_issues)} ticket(s) Jira."
        )


cyber_workflow_service = CyberWorkflowService()
