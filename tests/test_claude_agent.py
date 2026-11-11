"""Cerveau Claude : le vrai SDK Anthropic construit les requêtes, seul le réseau est simulé."""

import asyncio
import json

import pytest
from pydantic import SecretStr

anthropic = pytest.importorskip("anthropic")
httpx2 = pytest.importorskip("httpx2")

from jarvis_cyber.config import settings
from jarvis_cyber.services import assistant as assistant_module
from jarvis_cyber.services import claude_agent as claude_module
from jarvis_cyber.services.assistant import AssistantService
from jarvis_cyber.services.claude_agent import (
    ClaudeAgentService,
    ClaudeUnavailableError,
    _alternating_history,
)
from jarvis_cyber.services.local_agent import LocalAgentResult
from jarvis_cyber.services.mcp_client import MCPService


def _message(content: list[dict], stop_reason: str) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 7},
    }


def _service(handler) -> ClaudeAgentService:
    client = anthropic.AsyncAnthropic(
        api_key="clef-de-test",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return ClaudeAgentService(client=client)


class OneToolMCP(MCPService):
    def __init__(self) -> None:
        super().__init__(config_path="/inexistant.json")
        self.calls: list[tuple] = []

    async def list_all_tools(self):
        return [
            {
                "server": "systeme",
                "name": "calcul",
                "description": "Évalue une expression",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            }
        ]

    async def call_tool(self, server, tool, arguments=None):
        self.calls.append((server, tool, arguments))
        return {"server": server, "tool": tool, "is_error": False, "content": "6*7 = 42"}


def test_claude_is_disabled_without_a_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert ClaudeAgentService().enabled is False
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("sk-test"))
    assert ClaudeAgentService().enabled is True


def test_history_sent_to_claude_starts_with_the_user() -> None:
    history = [
        {"role": "assistant", "content": "Bonjour."},
        {"role": "user", "content": "Salut"},
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": "Oui ?"},
    ]
    assert _alternating_history(history) == [
        {"role": "user", "content": "Salut"},
        {"role": "assistant", "content": "Oui ?"},
    ]


def test_tool_round_trip_through_the_real_sdk(monkeypatch) -> None:
    mcp = OneToolMCP()
    monkeypatch.setattr(claude_module, "mcp_service", mcp)
    requests: list[tuple[dict, str]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        requests.append((body, request.headers.get("anthropic-beta", "")))
        if len(requests) == 1:
            return httpx2.Response(
                200,
                json=_message(
                    [
                        {
                            "type": "tool_use",
                            "id": "toolu_01",
                            "name": "systeme__calcul",
                            "input": {"expression": "6*7"},
                        }
                    ],
                    "tool_use",
                ),
            )
        return httpx2.Response(200, json=_message([{"type": "text", "text": "Cela fait 42."}], "end_turn"))

    result = asyncio.run(
        _service(handler).chat(
            message="Combien font 6 fois 7 ?",
            history=[{"role": "user", "content": "Combien font 6 fois 7 ?"}],
            system_prompt="Tu es Jarvis.",
        )
    )
    assert result == LocalAgentResult("Cela fait 42.", "claude/claude-opus-5-5", ["systeme.calcul"])
    assert mcp.calls == [("systeme", "calcul", {"expression": "6*7"})]

    first, beta_header = requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in beta_header
    assert first["output_config"] == {"effort": "low"}
    assert first["system"] == "Tu es Jarvis."
    assert [tool["name"] for tool in first["tools"]] == ["systeme__calcul"]
    assert "thinking" not in first and "temperature" not in first
    assert first["messages"] == [{"role": "user", "content": "Combien font 6 fois 7 ?"}]

    second, _ = requests[1]
    assert second["messages"][1]["role"] == "assistant"
    assert second["messages"][1]["content"][0]["type"] == "tool_use"
    assert second["messages"][2] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_01",
                "content": "6*7 = 42",
                "is_error": False,
            }
        ],
    }


def test_refusal_is_answered_politely(monkeypatch) -> None:
    monkeypatch.setattr(claude_module, "mcp_service", MCPService(config_path="/inexistant.json"))

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_message([], "refusal"))

    result = asyncio.run(_service(handler).chat(message="x", history=[], system_prompt="Jarvis"))
    assert result.answer == "Je ne peux pas t'aider sur cette demande."


@pytest.mark.parametrize(
    ("status", "error_type", "expected"),
    [
        (401, "authentication_error", "clé API Anthropic est refusée"),
        (429, "rate_limit_error", "Limite de débit"),
        (529, "overloaded_error", "Erreur Anthropic 529"),
    ],
)
def test_api_errors_become_a_reason_jarvis_can_say(monkeypatch, status, error_type, expected) -> None:
    monkeypatch.setattr(claude_module, "mcp_service", MCPService(config_path="/inexistant.json"))

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status, json={"type": "error", "error": {"type": error_type, "message": "non"}}
        )

    service = _service(handler)
    with pytest.raises(ClaudeUnavailableError, match=expected):
        asyncio.run(service.chat(message="x", history=[], system_prompt="Jarvis"))
    assert expected in service.last_error


def test_claude_answers_first_and_local_model_takes_over_when_it_fails(monkeypatch) -> None:
    order: list[str] = []

    class Claude:
        enabled = True
        last_error = None

        def __init__(self, fail: bool) -> None:
            self._fail = fail

        async def chat(self, **_kwargs):
            order.append("claude")
            if self._fail:
                raise ClaudeUnavailableError("réseau")
            return LocalAgentResult("Réponse de Claude.", "claude/claude-opus-5-5", [])

    def local(message, history, system_prompt):
        order.append("local")
        return LocalAgentResult("Réponse locale.", "ollama/llama3.1", [])

    monkeypatch.setattr(AssistantService, "_try_local_agent", staticmethod(local))

    monkeypatch.setattr(assistant_module, "claude_agent_service", Claude(fail=False))
    answer, model, remote, *_ = AssistantService().respond("ordre-user", "a", "Bonjour")
    assert (answer, model, remote) == ("Réponse de Claude.", "claude/claude-opus-5-5", True)
    assert order == ["claude"]

    order.clear()
    monkeypatch.setattr(assistant_module, "claude_agent_service", Claude(fail=True))
    answer, model, remote, *_ = AssistantService().respond("ordre-user", "b", "Bonjour")
    assert (answer, model, remote) == ("Réponse locale.", "ollama/llama3.1", False)
    assert order == ["claude", "local"]
