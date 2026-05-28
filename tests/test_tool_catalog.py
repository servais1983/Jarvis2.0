from jarvis_cyber.services.tool_catalog import ToolCatalogService


def test_tool_catalog_injects_user_scope(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.realtime_tool_service.search_knowledge",
        lambda query, limit, user_id: seen.update(
            {"query": query, "limit": limit, "user_id": user_id}
        )
        or {"results": []},
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.tool_guardrail_service.evaluate",
        lambda **kwargs: type("Decision", (), {"decision": "allow", "reason": "allowed"})(),
    )

    result = ToolCatalogService().execute(
        "search_knowledge",
        {"query": "phishing", "limit": 2},
        "analyst-1",
    )

    assert result == {"results": []}
    assert seen == {"query": "phishing", "limit": 2, "user_id": "analyst-1"}


def test_tool_catalog_injects_user_scope_for_investigation(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        "jarvis_cyber.services.realtime_tools.realtime_tool_service.investigate_alert",
        lambda **kwargs: seen.update(kwargs) or {"result": {}},
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.tool_guardrail_service.evaluate",
        lambda **kwargs: type("Decision", (), {"decision": "allow", "reason": "allowed"})(),
    )

    result = ToolCatalogService().execute(
        "investigate_alert",
        {"title": "Impossible travel", "raw_alert": "Suspicious login"},
        "analyst-1",
    )

    assert result == {"result": {}}
    assert seen["user_id"] == "analyst-1"


def test_tool_catalog_returns_approval_required(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.tool_guardrail_service.evaluate",
        lambda **kwargs: type("Decision", (), {"decision": "approval_required", "reason": "always_ask_profile"})(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.tool_approval_store.create",
        lambda user_id, **kwargs: type("Approval", (), {"approval_id": "approval-1"})(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.inbox_store.add",
        lambda user_id, **kwargs: None,
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.auth_service.record_audit_event",
        lambda **kwargs: None,
    )

    result = ToolCatalogService().execute(
        "search_jira_issues",
        {"jql": "project = SEC"},
        "analyst-1",
        role="analyst",
    )

    assert result == {
        "error": "approval_required",
        "tool": "search_jira_issues",
        "reason": "always_ask_profile",
        "approval_id": "approval-1",
    }


def test_tool_catalog_creates_approval_request(monkeypatch) -> None:
    created = []
    inbox = []
    audits = []
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.tool_guardrail_service.evaluate",
        lambda **kwargs: type("Decision", (), {"decision": "approval_required", "reason": "sensitive_tool"})(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.tool_approval_store.create",
        lambda user_id, **kwargs: created.append((user_id, kwargs))
        or type("Approval", (), {"approval_id": "approval-1"})(),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.inbox_store.add",
        lambda user_id, **kwargs: inbox.append((user_id, kwargs)),
    )
    monkeypatch.setattr(
        "jarvis_cyber.services.tool_catalog.auth_service.record_audit_event",
        lambda **kwargs: audits.append(kwargs),
    )

    result = ToolCatalogService().execute(
        "create_watchlist",
        {"title": "Microsoft 365", "keywords": "Microsoft Outlook"},
        "analyst-1",
        role="analyst",
    )

    assert result["approval_id"] == "approval-1"
    assert created[0][0] == "analyst-1"
    assert inbox[0][1]["item_type"] == "tool_approval_required"
    assert audits[0]["event_type"] == "tool.approval_requested"

