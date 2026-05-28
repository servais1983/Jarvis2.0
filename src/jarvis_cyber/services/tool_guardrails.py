from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jarvis_cyber.auth import ROLE_PERMISSIONS, auth_service
from jarvis_cyber.profile.store import profile_store


ToolRisk = Literal["low", "sensitive"]
ToolDecision = Literal["allow", "approval_required", "blocked"]


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    permission: str
    risk: ToolRisk
    access_mode: Literal["internal_read", "external_read", "internal_write", "analysis"]


@dataclass(frozen=True)
class ToolPolicyResult:
    decision: ToolDecision
    policy: ToolPolicy
    reason: str


class ToolGuardrailService:
    """Decide whether Jarvis may execute a tool for a user and audit the decision."""

    _policies: dict[str, ToolPolicy] = {
        "search_knowledge": ToolPolicy(
            name="search_knowledge",
            permission="knowledge.read",
            risk="low",
            access_mode="internal_read",
        ),
        "search_playbooks": ToolPolicy(
            name="search_playbooks",
            permission="playbooks.read",
            risk="low",
            access_mode="internal_read",
        ),
        "list_inbox": ToolPolicy(
            name="list_inbox",
            permission="inbox.read",
            risk="low",
            access_mode="internal_read",
        ),
        "list_github_repositories": ToolPolicy(
            name="list_github_repositories",
            permission="connectors.read",
            risk="low",
            access_mode="external_read",
        ),
        "list_google_drive_files": ToolPolicy(
            name="list_google_drive_files",
            permission="connectors.read",
            risk="low",
            access_mode="external_read",
        ),
        "search_jira_issues": ToolPolicy(
            name="search_jira_issues",
            permission="connectors.read",
            risk="low",
            access_mode="external_read",
        ),
        "list_entra_sign_ins": ToolPolicy(
            name="list_entra_sign_ins",
            permission="connectors.read",
            risk="low",
            access_mode="external_read",
        ),
        "list_entra_risky_users": ToolPolicy(
            name="list_entra_risky_users",
            permission="connectors.read",
            risk="low",
            access_mode="external_read",
        ),
        "list_entra_authentication_methods": ToolPolicy(
            name="list_entra_authentication_methods",
            permission="connectors.read",
            risk="sensitive",
            access_mode="external_read",
        ),
        "list_defender_incidents": ToolPolicy(
            name="list_defender_incidents",
            permission="connectors.read",
            risk="low",
            access_mode="external_read",
        ),
        "list_defender_alerts": ToolPolicy(
            name="list_defender_alerts",
            permission="connectors.read",
            risk="low",
            access_mode="external_read",
        ),
        "run_sentinel_query": ToolPolicy(
            name="run_sentinel_query",
            permission="connectors.read",
            risk="sensitive",
            access_mode="external_read",
        ),
        "summarize_cve": ToolPolicy(
            name="summarize_cve",
            permission="workflow.cve_enrichment",
            risk="low",
            access_mode="analysis",
        ),
        "triage_alert": ToolPolicy(
            name="triage_alert",
            permission="workflow.alert_triage",
            risk="low",
            access_mode="analysis",
        ),
        "investigate_alert": ToolPolicy(
            name="investigate_alert",
            permission="workflow.alert_investigation",
            risk="low",
            access_mode="analysis",
        ),
        "create_watchlist": ToolPolicy(
            name="create_watchlist",
            permission="watchlists.write",
            risk="sensitive",
            access_mode="internal_write",
        ),
    }

    def policy_for(self, tool_name: str) -> ToolPolicy | None:
        return self._policies.get(tool_name)

    def evaluate(
        self,
        *,
        user_id: str,
        role: str,
        tool_name: str,
        source: str,
    ) -> ToolPolicyResult:
        policy = self.policy_for(tool_name)
        if policy is None:
            fallback = ToolPolicy(
                name=tool_name,
                permission="unknown",
                risk="sensitive",
                access_mode="analysis",
            )
            result = ToolPolicyResult("blocked", fallback, "unknown_tool")
            self._audit(user_id, source, result)
            return result

        if policy.permission not in ROLE_PERMISSIONS.get(role, set()):
            result = ToolPolicyResult("blocked", policy, "missing_permission")
            self._audit(user_id, source, result)
            return result

        approval_preference = profile_store.get(user_id).approval_preference
        if approval_preference == "suggest_only":
            result = ToolPolicyResult("blocked", policy, "suggest_only_profile")
        elif approval_preference == "always_ask":
            result = ToolPolicyResult("approval_required", policy, "always_ask_profile")
        elif policy.risk == "sensitive":
            result = ToolPolicyResult("approval_required", policy, "sensitive_tool")
        else:
            result = ToolPolicyResult("allow", policy, "allowed")
        self._audit(user_id, source, result)
        return result

    @staticmethod
    def _audit(user_id: str, source: str, result: ToolPolicyResult) -> None:
        auth_service.record_audit_event(
            event_type=f"tool.{result.decision}",
            actor_user_id=user_id,
            metadata={
                "tool_name": result.policy.name,
                "permission": result.policy.permission,
                "risk": result.policy.risk,
                "access_mode": result.policy.access_mode,
                "source": source,
                "reason": result.reason,
            },
        )


tool_guardrail_service = ToolGuardrailService()
