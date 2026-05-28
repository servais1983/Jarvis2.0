from __future__ import annotations

from jarvis_cyber.core.schemas import (
    AlertInvestigationRequest,
    AlertTriageRequest,
    CVEEnrichmentRequest,
    WatchlistCreateRequest,
)
from jarvis_cyber.knowledge.store import knowledge_store
from jarvis_cyber.inbox.store import inbox_store
from jarvis_cyber.playbooks.store import playbook_store
from jarvis_cyber.watchlists.store import watchlist_store
from jarvis_cyber.services.workflows import cyber_workflow_service
from jarvis_cyber.integrations.github import github_connector
from jarvis_cyber.integrations.google_drive import google_drive_connector
from jarvis_cyber.integrations.jira import jira_connector
from jarvis_cyber.integrations.entra_id import entra_id_connector
from jarvis_cyber.integrations.microsoft_defender import microsoft_defender_connector
from jarvis_cyber.integrations.microsoft_sentinel import microsoft_sentinel_connector


class RealtimeToolService:
    """Server-side execution surface for Realtime-capable tools."""

    def search_knowledge(self, query: str, limit: int = 3, user_id: str = "local-dev") -> dict:
        results = knowledge_store.search(user_id, query, limit=limit)
        return {"results": [result.model_dump() for result in results]}

    def summarize_cve(self, cve_id: str) -> dict:
        record, analysis, model, used_remote_model = cyber_workflow_service.enrich_cve(
            CVEEnrichmentRequest(cve_id=cve_id)
        )
        return {
            "record": record.model_dump(),
            "analysis": analysis.model_dump(),
            "model": model,
            "used_remote_model": used_remote_model,
        }

    def triage_alert(
        self,
        title: str,
        raw_alert: str,
        environment_context: str | None = None,
    ) -> dict:
        result, model, used_remote_model = cyber_workflow_service.triage_alert(
            AlertTriageRequest(
                title=title,
                raw_alert=raw_alert,
                environment_context=environment_context,
            )
        )
        return {
            "result": result.model_dump(),
            "model": model,
            "used_remote_model": used_remote_model,
        }

    def investigate_alert(
        self,
        title: str,
        raw_alert: str,
        environment_context: str | None = None,
        goal: str | None = None,
        investigation_profile_id: str | None = None,
        include_recent_github: bool = False,
        drive_query: str | None = None,
        jira_jql: str | None = None,
        user_id: str = "local-dev",
    ) -> dict:
        result, model, used_remote_model, knowledge_hits, playbook_hits, external_context, applied_profile = (
            cyber_workflow_service.investigate_alert(
                user_id,
                AlertInvestigationRequest(
                    title=title,
                    raw_alert=raw_alert,
                    environment_context=environment_context,
                    goal=goal,
                    investigation_profile_id=investigation_profile_id,
                    include_recent_github=include_recent_github,
                    drive_query=drive_query,
                    jira_jql=jira_jql,
                ),
            )
        )
        return {
            "result": result.model_dump(),
            "knowledge_hits": [hit.model_dump() for hit in knowledge_hits],
            "playbook_hits": [hit.model_dump() for hit in playbook_hits],
            "applied_profile": applied_profile.model_dump() if applied_profile else None,
            "external_context": external_context.model_dump(),
            "model": model,
            "used_remote_model": used_remote_model,
        }

    def search_playbooks(self, query: str, limit: int = 3, user_id: str = "local-dev") -> dict:
        results = playbook_store.search_playbooks(user_id, query, limit=limit)
        return {"results": [result.model_dump() for result in results]}

    def list_inbox(self, unread_only: bool = True, limit: int = 5, user_id: str = "local-dev") -> dict:
        items = inbox_store.list(user_id, unread_only=unread_only)[:limit]
        return {"items": [item.model_dump() for item in items]}

    def list_github_repositories(self, limit: int = 5) -> dict:
        if not github_connector.configured:
            return {"error": "github_not_configured"}
        return {"repositories": [item.model_dump() for item in github_connector.list_repositories(limit)]}

    def list_google_drive_files(self, query: str | None = None, limit: int = 5) -> dict:
        if not google_drive_connector.configured:
            return {"error": "google_drive_not_configured"}
        return {"files": [item.model_dump() for item in google_drive_connector.list_files(query, limit)]}

    def search_jira_issues(self, jql: str, limit: int = 5) -> dict:
        if not jira_connector.configured:
            return {"error": "jira_not_configured"}
        return {"issues": [item.model_dump() for item in jira_connector.search_issues(jql, limit)]}

    def list_entra_sign_ins(
        self,
        user_principal_name: str | None = None,
        limit: int = 5,
    ) -> dict:
        if not entra_id_connector.configured:
            return {"error": "entra_id_not_configured"}
        return {
            "sign_ins": [
                item.model_dump()
                for item in entra_id_connector.list_sign_ins(
                    limit=limit,
                    user_principal_name=user_principal_name,
                )
            ]
        }

    def list_entra_risky_users(self, limit: int = 5) -> dict:
        if not entra_id_connector.configured:
            return {"error": "entra_id_not_configured"}
        return {
            "risky_users": [
                item.model_dump() for item in entra_id_connector.list_risky_users(limit=limit)
            ]
        }

    def list_entra_authentication_methods(self, user_id: str) -> dict:
        if not entra_id_connector.configured:
            return {"error": "entra_id_not_configured"}
        return {
            "methods": [
                item.model_dump()
                for item in entra_id_connector.list_authentication_methods(user_id)
            ]
        }

    def list_defender_incidents(
        self,
        limit: int = 5,
        status: str | None = None,
        severity: str | None = None,
    ) -> dict:
        if not microsoft_defender_connector.configured:
            return {"error": "microsoft_defender_not_configured"}
        return {
            "incidents": [
                item.model_dump()
                for item in microsoft_defender_connector.list_incidents(
                    limit=limit,
                    status=status,
                    severity=severity,
                )
            ]
        }

    def list_defender_alerts(
        self,
        limit: int = 5,
        status: str | None = None,
        severity: str | None = None,
        service_source: str | None = None,
    ) -> dict:
        if not microsoft_defender_connector.configured:
            return {"error": "microsoft_defender_not_configured"}
        return {
            "alerts": [
                item.model_dump()
                for item in microsoft_defender_connector.list_alerts(
                    limit=limit,
                    status=status,
                    severity=severity,
                    service_source=service_source,
                )
            ]
        }

    def run_sentinel_query(self, query: str, timespan: str | None = None) -> dict:
        if not microsoft_sentinel_connector.configured:
            return {"error": "microsoft_sentinel_not_configured"}
        return {"result": microsoft_sentinel_connector.query(query, timespan=timespan, max_rows=25).model_dump()}

    def create_watchlist(
        self,
        title: str,
        keywords: str,
        exact_match: bool = False,
        kev_only: bool = False,
        user_id: str = "local-dev",
    ) -> dict:
        watchlist = watchlist_store.add(
            user_id,
            WatchlistCreateRequest(
                title=title,
                keywords=keywords,
                exact_match=exact_match,
                kev_only=kev_only,
            ),
        )
        return {"watchlist": watchlist.model_dump()}


realtime_tool_service = RealtimeToolService()
