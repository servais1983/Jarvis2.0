from __future__ import annotations

from datetime import UTC, datetime

from jarvis_cyber.automations.store import automation_store
from jarvis_cyber.core.schemas import Automation, AutomationRun
from jarvis_cyber.inbox.store import inbox_store
from jarvis_cyber.services.briefings import briefing_service
from jarvis_cyber.services.connector_digest import connector_digest_service


class AutomationService:
    """Execute native automations and retain audit-friendly run history."""

    def run(self, user_id: str, automation: Automation, *, now: datetime | None = None) -> AutomationRun:
        started_at = now or datetime.now(UTC)
        if automation.requires_approval:
            run = automation_store.record_run(
                user_id,
                automation.automation_id,
                status="approval_required",
                started_at=started_at,
                finished_at=started_at,
                output_json=None,
                error_message=None,
            )
            inbox_store.add(
                user_id,
                item_type="approval_required",
                title=f"{automation.name} attend ton approbation",
                body="La routine est arrivée à échéance, mais son exécution exige une validation humaine.",
                related_run_id=run.run_id,
            )
            automation_store.mark_scheduled(user_id, automation, ran_at=started_at)
            return run

        try:
            output_json = self._execute(automation, user_id)
        except Exception as error:
            run = automation_store.record_run(
                user_id,
                automation.automation_id,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                output_json=None,
                error_message=str(error),
            )
            inbox_store.add(
                user_id,
                item_type="automation_failed",
                title=f"{automation.name} a échoué",
                body=str(error),
                related_run_id=run.run_id,
            )
        else:
            run = automation_store.record_run(
                user_id,
                automation.automation_id,
                status="succeeded",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                output_json=output_json,
                error_message=None,
            )
            payload = run.output
            body = self._success_body(payload)
            inbox_store.add(
                user_id,
                item_type="automation_succeeded",
                title=f"{automation.name} est prêt",
                body=body,
                related_run_id=run.run_id,
                payload_json=output_json,
            )
        automation_store.mark_scheduled(user_id, automation, ran_at=started_at)
        return run

    def run_due(self, user_id: str, *, now: datetime | None = None) -> list[AutomationRun]:
        current = now or datetime.now(UTC)
        return [self.run(user_id, automation, now=current) for automation in automation_store.due(user_id, current)]

    @staticmethod
    def _execute(automation: Automation, user_id: str) -> str:
        if automation.automation_type != "daily_brief":
            if automation.automation_type != "connector_digest":
                raise ValueError(f"Unsupported automation type: {automation.automation_type}")
            digest = connector_digest_service.build(automation.payload)
            return digest.model_dump_json()
        brief = briefing_service.daily_brief(
            user_id,
            days=automation.payload.days,
            per_watchlist_limit=automation.payload.per_watchlist_limit,
        )
        return brief.model_dump_json()

    @staticmethod
    def _success_body(payload) -> str:
        if payload is None:
            return "Livrable généré."
        if hasattr(payload, "items"):
            return f"{len(payload.items)} watchlist(s) traitée(s)."
        repositories = len(getattr(payload, "repositories", []))
        drive_files = len(getattr(payload, "drive_files", []))
        jira_issues = len(getattr(payload, "jira_issues", []))
        return (
            "Digest connecteurs prêt : "
            f"{repositories} dépôt(s), {drive_files} fichier(s) Drive, {jira_issues} ticket(s) Jira."
        )


automation_service = AutomationService()
