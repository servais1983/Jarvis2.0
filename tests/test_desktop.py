import json
import socket

from fastapi.testclient import TestClient

from jarvis_cyber.api.main import app
from jarvis_cyber.desktop import app as desktop
from jarvis_cyber.services.brain import brain_status, model_matches

client = TestClient(app)


def test_model_matching_follows_ollama_tags() -> None:
    assert model_matches("llama3.1:latest", "llama3.1")
    assert model_matches("llama3.2:3b", "llama3.2:3b")
    assert not model_matches("llama3.2:1b", "llama3.2:3b")
    assert not model_matches("llama3.1:latest", "llama3")


def test_brain_reports_no_engine_when_nothing_is_available() -> None:
    status = brain_status()
    assert status["ollama_running"] is False
    assert status["engine"] in ("aucun", "openai")
    assert client.get("/system/brain").json()["model"] == status["model"]


def test_configure_environment_isolates_user_data(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "JARVIS_DATA_DIR",
        "JARVIS_DATABASE_PATH",
        "JARVIS_MCP_SERVERS_FILE",
        "JARVIS_NATIVE_VOICE_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", "/usr/bin")
    base = desktop.configure_environment(tmp_path / "Jarvis", native_voice=True)

    import os

    assert os.environ["JARVIS_DATABASE_PATH"] == str(base / "jarvis.db")
    assert os.environ["JARVIS_NATIVE_VOICE_ENABLED"] == "true"
    config = json.loads((base / "mcp_servers.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["systeme"]["args"] == ["-m", "jarvis_cyber.mcp_builtin.system_server"]
    assert (base / "logs").is_dir()


def test_configure_environment_keeps_existing_mcp_config(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "Jarvis"
    base.mkdir()
    custom = base / "mcp_servers.json"
    custom.write_text('{"mcpServers": {}}', encoding="utf-8")
    monkeypatch.setenv("JARVIS_MCP_SERVERS_FILE", str(custom))
    desktop.configure_environment(base)
    assert custom.read_text(encoding="utf-8") == '{"mcpServers": {}}'


def test_find_free_port_falls_back_when_preferred_is_taken() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        taken = busy.getsockname()[1]
        port = desktop.find_free_port(taken)
        assert port != taken and port > 0


def test_chat_fallback_is_a_sentence_jarvis_can_say() -> None:
    answer = client.post("/chat", json={"session_id": "voix", "message": "Raconte-moi une blague"}).json()["answer"]
    assert "Ollama" in answer
    assert "extrait(s)" not in answer and "Demande reçue" not in answer
