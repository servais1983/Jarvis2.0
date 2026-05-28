from __future__ import annotations

from collections.abc import Callable

from jarvis_cyber.approvals.store import tool_approval_store
from jarvis_cyber.auth import auth_service
from jarvis_cyber.inbox.store import inbox_store
from jarvis_cyber.services.tool_guardrails import tool_guardrail_service


class ToolCatalogService:
    """Shared tool catalog for text chat and Realtime sessions."""

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "name": "search_knowledge",
                "description": "Recherche des informations dans la base documentaire interne de Jarvis Cyber.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "search_playbooks",
                "description": "Recherche les playbooks personnels et profils de tâches pertinents de l'utilisateur.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_inbox",
                "description": "Liste les éléments récents de l'inbox utilisateur, notamment les livrables non lus.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "unread_only": {"type": "boolean"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_github_repositories",
                "description": "Liste les dépôts GitHub récemment mis à jour accessibles à Jarvis.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_google_drive_files",
                "description": "Liste des fichiers Google Drive récents ou filtrés.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "search_jira_issues",
                "description": "Recherche des tickets Jira via une requête JQL fournie.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "jql": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": ["jql"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_entra_sign_ins",
                "description": "Liste les connexions Microsoft Entra ID récentes, éventuellement pour un utilisateur précis.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_principal_name": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_entra_risky_users",
                "description": "Liste les utilisateurs Microsoft Entra ID actuellement signalés comme à risque.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_entra_authentication_methods",
                "description": (
                    "Liste les types de méthodes d'authentification enregistrées pour un utilisateur Entra ID. "
                    "Cette lecture est sensible et peut nécessiter une approbation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                    },
                    "required": ["user_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_defender_incidents",
                "description": "Liste les incidents Microsoft Defender / Graph Security récents en lecture seule.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        "status": {"type": "string"},
                        "severity": {"type": "string"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_defender_alerts",
                "description": "Liste les alertes Microsoft Defender / Graph Security récentes en lecture seule.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        "status": {"type": "string"},
                        "severity": {"type": "string"},
                        "service_source": {"type": "string"},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "run_sentinel_query",
                "description": (
                    "Exécute une requête KQL explicite sur Microsoft Sentinel / Log Analytics. "
                    "Cette lecture peut exposer des logs sensibles et peut nécessiter une approbation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "timespan": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "summarize_cve",
                "description": "Récupère et analyse une CVE à partir de son identifiant.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cve_id": {"type": "string"},
                    },
                    "required": ["cve_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "triage_alert",
                "description": "Réalise un premier triage d'alerte SOC.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "raw_alert": {"type": "string"},
                        "environment_context": {"type": "string"},
                    },
                    "required": ["title", "raw_alert"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "investigate_alert",
                "description": (
                    "Mène une première investigation d'alerte en combinant triage, mémoire interne "
                    "et playbooks personnels."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "raw_alert": {"type": "string"},
                        "environment_context": {"type": "string"},
                        "goal": {"type": "string"},
                        "investigation_profile_id": {"type": "string"},
                        "include_recent_github": {"type": "boolean"},
                        "drive_query": {"type": "string"},
                        "jira_jql": {"type": "string"},
                    },
                    "required": ["title", "raw_alert"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "create_watchlist",
                "description": (
                    "Propose la création d'une watchlist de vulnérabilités pour une technologie "
                    "ou un sujet à surveiller. Cette action nécessite une approbation humaine."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "keywords": {"type": "string"},
                        "exact_match": {"type": "boolean"},
                        "kev_only": {"type": "boolean"},
                    },
                    "required": ["title", "keywords"],
                    "additionalProperties": False,
                },
            },
        ]

    def execute(
        self,
        name: str,
        arguments: dict,
        user_id: str,
        *,
        role: str = "admin",
        source: str = "text_chat",
    ) -> dict:
        decision = tool_guardrail_service.evaluate(
            user_id=user_id,
            role=role,
            tool_name=name,
            source=source,
        )
        if decision.decision == "blocked":
            return {
                "error": "tool_execution_blocked",
                "tool": name,
                "reason": decision.reason,
            }
        if decision.decision == "approval_required":
            approval = tool_approval_store.create(
                user_id,
                tool_name=name,
                arguments=arguments,
                reason=decision.reason,
                source=source,
            )
            inbox_store.add(
                user_id,
                item_type="tool_approval_required",
                title=f"Approbation requise pour {name}",
                body=self._approval_body(name, arguments),
            )
            auth_service.record_audit_event(
                event_type="tool.approval_requested",
                actor_user_id=user_id,
                metadata={
                    "approval_id": approval.approval_id,
                    "tool_name": name,
                    "reason": decision.reason,
                    "source": source,
                },
            )
            return {
                "error": "approval_required",
                "tool": name,
                "reason": decision.reason,
                "approval_id": approval.approval_id,
            }

        return self.execute_approved(name, arguments, user_id)

    def execute_approved(self, name: str, arguments: dict, user_id: str) -> dict:
        from jarvis_cyber.services.realtime_tools import realtime_tool_service

        handlers: dict[str, Callable[..., dict]] = {
            "search_knowledge": realtime_tool_service.search_knowledge,
            "search_playbooks": realtime_tool_service.search_playbooks,
            "list_inbox": realtime_tool_service.list_inbox,
            "list_github_repositories": realtime_tool_service.list_github_repositories,
            "list_google_drive_files": realtime_tool_service.list_google_drive_files,
            "search_jira_issues": realtime_tool_service.search_jira_issues,
            "list_entra_sign_ins": realtime_tool_service.list_entra_sign_ins,
            "list_entra_risky_users": realtime_tool_service.list_entra_risky_users,
            "list_entra_authentication_methods": realtime_tool_service.list_entra_authentication_methods,
            "list_defender_incidents": realtime_tool_service.list_defender_incidents,
            "list_defender_alerts": realtime_tool_service.list_defender_alerts,
            "run_sentinel_query": realtime_tool_service.run_sentinel_query,
            "summarize_cve": realtime_tool_service.summarize_cve,
            "triage_alert": realtime_tool_service.triage_alert,
            "investigate_alert": realtime_tool_service.investigate_alert,
            "create_watchlist": realtime_tool_service.create_watchlist,
        }
        handler = handlers.get(name)
        if handler is None:
            return {"error": "unknown_tool"}
        if name in {
            "search_knowledge",
            "search_playbooks",
            "list_inbox",
            "investigate_alert",
            "create_watchlist",
        }:
            arguments = {**arguments, "user_id": user_id}
        return handler(**arguments)

    @staticmethod
    def _approval_body(name: str, arguments: dict) -> str:
        if name == "create_watchlist":
            return (
                "Jarvis propose de créer la watchlist "
                f"« {arguments.get('title', 'sans titre')} » "
                f"pour suivre « {arguments.get('keywords', '')} »."
            )
        return f"Jarvis demande ton accord avant d'exécuter l'outil {name}."


tool_catalog_service = ToolCatalogService()
