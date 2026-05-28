from jarvis_cyber.core.schemas import UserProfileResponse
from jarvis_cyber.services.tool_guardrails import ToolGuardrailService


def _profile(approval_preference: str) -> UserProfileResponse:
    return UserProfileResponse(
        user_id="analyst-1",
        preferred_language="fr",
        response_style="balanced",
        approval_preference=approval_preference,
        created_at="now",
        updated_at="now",
    )


def test_tool_guardrails_allow_low_risk_tools(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.profile_store.get",
        lambda user_id: _profile("ask_before_sensitive_actions"),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.auth_service.record_audit_event",
        lambda **kwargs: events.append(kwargs),
    )

    result = ToolGuardrailService().evaluate(
        user_id="analyst-1",
        role="analyst",
        tool_name="search_jira_issues",
        source="text_chat",
    )

    assert result.decision == "allow"
    assert events[0]["event_type"] == "tool.allow"


def test_tool_guardrails_require_approval_when_profile_always_asks(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.profile_store.get",
        lambda user_id: _profile("always_ask"),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.auth_service.record_audit_event",
        lambda **kwargs: None,
    )

    result = ToolGuardrailService().evaluate(
        user_id="analyst-1",
        role="analyst",
        tool_name="search_jira_issues",
        source="text_chat",
    )

    assert result.decision == "approval_required"
    assert result.reason == "always_ask_profile"


def test_tool_guardrails_block_when_profile_is_suggest_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.profile_store.get",
        lambda user_id: _profile("suggest_only"),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.auth_service.record_audit_event",
        lambda **kwargs: None,
    )

    result = ToolGuardrailService().evaluate(
        user_id="analyst-1",
        role="analyst",
        tool_name="search_jira_issues",
        source="realtime",
    )

    assert result.decision == "blocked"
    assert result.reason == "suggest_only_profile"


def test_tool_guardrails_require_approval_for_sensitive_tools(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.profile_store.get",
        lambda user_id: _profile("ask_before_sensitive_actions"),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.auth_service.record_audit_event",
        lambda **kwargs: None,
    )

    result = ToolGuardrailService().evaluate(
        user_id="analyst-1",
        role="analyst",
        tool_name="create_watchlist",
        source="text_chat",
    )

    assert result.decision == "approval_required"
    assert result.reason == "sensitive_tool"


def test_tool_guardrails_require_approval_for_entra_authentication_methods(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.profile_store.get",
        lambda user_id: _profile("ask_before_sensitive_actions"),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.auth_service.record_audit_event",
        lambda **kwargs: None,
    )

    result = ToolGuardrailService().evaluate(
        user_id="analyst-1",
        role="analyst",
        tool_name="list_entra_authentication_methods",
        source="text_chat",
    )

    assert result.decision == "approval_required"
    assert result.reason == "sensitive_tool"


def test_tool_guardrails_require_approval_for_sentinel_queries(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.profile_store.get",
        lambda user_id: _profile("ask_before_sensitive_actions"),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_guardrails.auth_service.record_audit_event",
        lambda **kwargs: None,
    )

    result = ToolGuardrailService().evaluate(
        user_id="analyst-1",
        role="analyst",
        tool_name="run_sentinel_query",
        source="text_chat",
    )

    assert result.decision == "approval_required"
    assert result.reason == "sensitive_tool"
