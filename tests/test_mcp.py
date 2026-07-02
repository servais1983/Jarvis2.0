import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jarvis_cyber.api.main import app
from jarvis_cyber.services.mcp_client import MCP_AVAILABLE, MCPError, MCPService

client = TestClient(app)

DEMO_SERVER = Path(__file__).resolve().parent.parent / "examples" / "mcp_demo_server.py"


def write_config(tmp_path: Path, enabled: bool = True) -> Path:
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "command": sys.executable,
                        "args": [str(DEMO_SERVER)],
                        "enabled": enabled,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return config


def test_servers_empty_without_config(tmp_path) -> None:
    service = MCPService(config_path=str(tmp_path / "absent.json"))
    assert service.servers() == []


def test_servers_ignores_disabled_and_invalid(tmp_path) -> None:
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "off": {"command": "python", "enabled": False},
                    "broken": {"args": ["sans-commande"]},
                    "on": {"command": "python", "args": ["serveur.py"]},
                }
            }
        ),
        encoding="utf-8",
    )
    service = MCPService(config_path=str(config))
    names = [server.name for server in service.servers()]
    assert names == ["on"]


def test_unknown_server_raises(tmp_path) -> None:
    service = MCPService(config_path=str(tmp_path / "absent.json"))
    with pytest.raises(MCPError):
        service._server("fantome")


def test_mcp_status_endpoint_without_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.api.main.mcp_service",
        MCPService(config_path=str(tmp_path / "absent.json")),
    )
    response = client.get("/mcp/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["servers"] == []


@pytest.mark.skipif(not MCP_AVAILABLE, reason="SDK MCP non installé")
def test_mcp_end_to_end_with_demo_server(monkeypatch, tmp_path) -> None:
    config = write_config(tmp_path)
    service = MCPService(config_path=str(config))
    monkeypatch.setattr("jarvis_cyber.api.main.mcp_service", service)

    status = client.get("/mcp/status")
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["servers"][0]["connected"] is True
    assert body["servers"][0]["tools_count"] == 3

    tools = client.get("/mcp/tools")
    assert tools.status_code == 200
    names = {tool["name"] for tool in tools.json()}
    assert {"heure_locale", "calcul", "infos_systeme"} <= names

    call = client.post(
        "/mcp/call",
        json={"server": "demo", "tool": "calcul", "arguments": {"expression": "(12+8)*3"}},
    )
    assert call.status_code == 200
    assert call.json()["is_error"] is False
    assert "60" in call.json()["content"]


@pytest.mark.skipif(not MCP_AVAILABLE, reason="SDK MCP non installé")
def test_mcp_call_unknown_server_returns_502(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "jarvis_cyber.api.main.mcp_service",
        MCPService(config_path=str(tmp_path / "absent.json")),
    )
    response = client.post(
        "/mcp/call",
        json={"server": "fantome", "tool": "calcul", "arguments": {}},
    )
    assert response.status_code == 502
