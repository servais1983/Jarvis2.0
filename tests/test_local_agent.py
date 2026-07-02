import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from jarvis_cyber.api.main import app
from jarvis_cyber.services import local_agent as local_agent_module
from jarvis_cyber.services.local_agent import (
    LocalAgentResult,
    LocalAgentService,
    LocalAgentUnavailableError,
)
from jarvis_cyber.services.mcp_client import MCP_AVAILABLE, MCPService

client = TestClient(app)

DEMO_SERVER = Path(__file__).resolve().parent.parent / "examples" / "mcp_demo_server.py"


def make_agent(handler) -> LocalAgentService:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="http://ollama.test")
    return LocalAgentService(client=http)


def no_mcp(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        local_agent_module, "mcp_service", MCPService(config_path=str(tmp_path / "absent.json"))
    )


def test_available_true_and_false(monkeypatch, tmp_path) -> None:
    no_mcp(monkeypatch, tmp_path)

    def up(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"version": "0.5.0"})

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé")

    assert asyncio.run(make_agent(up).available()) is True
    assert asyncio.run(make_agent(down).available()) is False


def test_chat_simple_answer(monkeypatch, tmp_path) -> None:
    no_mcp(monkeypatch, tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["messages"][0]["role"] == "system"
        assert "tools" not in body  # aucun serveur MCP configuré
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "Bonjour Steve."}}
        )

    result = asyncio.run(
        make_agent(handler).chat(
            message="Salut", history=[{"role": "user", "content": "Salut"}], system_prompt="Tu es Jarvis."
        )
    )
    assert result.answer == "Bonjour Steve."
    assert result.tools_used == []
    assert result.model.startswith("ollama/")


def test_chat_empty_answer_raises(monkeypatch, tmp_path) -> None:
    no_mcp(monkeypatch, tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": ""}})

    with pytest.raises(LocalAgentUnavailableError):
        asyncio.run(
            make_agent(handler).chat(message="Salut", history=[], system_prompt="Jarvis")
        )


@pytest.mark.skipif(not MCP_AVAILABLE, reason="SDK MCP non installé")
def test_chat_runs_mcp_tool_round_trip(monkeypatch, tmp_path) -> None:
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {"command": sys.executable, "args": [str(DEMO_SERVER)]}
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(local_agent_module, "mcp_service", MCPService(config_path=str(config)))

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls["count"] += 1
        if calls["count"] == 1:
            # Le modèle voit les outils MCP et demande un calcul
            names = [tool["function"]["name"] for tool in body["tools"]]
            assert "demo__calcul" in names
            return httpx.Response(
                200,
                json={
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "demo__calcul",
                                    "arguments": {"expression": "6*7"},
                                }
                            }
                        ],
                    }
                },
            )
        # Deuxième tour : le résultat de l'outil doit être dans l'historique
        tool_messages = [m for m in body["messages"] if m["role"] == "tool"]
        assert tool_messages and "42" in tool_messages[0]["content"]
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "Le résultat est 42."}},
        )

    result = asyncio.run(
        make_agent(handler).chat(
            message="Combien font 6 fois 7 ?", history=[], system_prompt="Tu es Jarvis."
        )
    )
    assert result.answer == "Le résultat est 42."
    assert result.tools_used == ["demo.calcul"]
    assert calls["count"] == 2


def test_chat_endpoint_uses_local_agent(monkeypatch) -> None:
    class StubAgent:
        async def available(self) -> bool:
            return True

        async def chat(self, **kwargs) -> LocalAgentResult:
            return LocalAgentResult(
                answer="Réponse locale outillée.",
                model="ollama/test",
                tools_used=["demo.calcul"],
            )

    monkeypatch.setattr("jarvis_cyber.services.assistant.local_agent_service", StubAgent())

    response = client.post("/chat", json={"session_id": "agent", "message": "6*7 ?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Réponse locale outillée."
    assert body["model"] == "ollama/test"
    assert body["used_remote_model"] is False
    assert body["tools_used"] == ["demo.calcul"]
