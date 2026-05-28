import pytest

from jarvis_cyber.services.realtime import RealtimeService, RealtimeServiceUnavailableError


@pytest.mark.anyio
async def test_realtime_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr("jarvis_cyber.services.realtime.settings.openai_api_key", None)

    with pytest.raises(RealtimeServiceUnavailableError):
        await RealtimeService().mint_client_secret("local-dev")


def test_realtime_declares_core_tools() -> None:
    tools = RealtimeService._tools()
    assert {tool["name"] for tool in tools} == {
        "search_knowledge",
        "search_playbooks",
        "list_inbox",
        "list_github_repositories",
        "list_google_drive_files",
        "search_jira_issues",
        "list_entra_sign_ins",
        "list_entra_risky_users",
        "list_entra_authentication_methods",
        "list_defender_incidents",
        "list_defender_alerts",
        "run_sentinel_query",
        "summarize_cve",
        "triage_alert",
        "investigate_alert",
        "create_watchlist",
    }
