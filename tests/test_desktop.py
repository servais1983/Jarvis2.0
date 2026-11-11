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


def test_api_key_is_saved_privately_and_replaced_not_duplicated(tmp_path) -> None:
    (tmp_path / ".env").write_text("JARVIS_USER_NAME=Steve\nANTHROPIC_API_KEY=ancienne\n", encoding="utf-8")
    env_file = desktop.save_env_value(tmp_path, "ANTHROPIC_API_KEY", "nouvelle")
    assert env_file.read_text(encoding="utf-8") == "JARVIS_USER_NAME=Steve\nANTHROPIC_API_KEY=nouvelle\n"
    assert env_file.stat().st_mode & 0o777 == 0o600


def test_configure_claude_refuses_an_empty_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "  ")
    assert desktop.configure_claude(tmp_path) == 1
    assert not (tmp_path / ".env").exists()
    monkeypatch.setattr("getpass.getpass", lambda _prompt: " sk-ant-test ")
    monkeypatch.setattr(desktop, "check_claude", lambda: 0)   # pas d'appel réel dans les tests
    from jarvis_cyber.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert desktop.configure_claude(tmp_path) == 0
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test"
    assert "ANTHROPIC_API_KEY=sk-ant-test" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_check_claude_reports_when_no_key_is_configured(monkeypatch, capsys) -> None:
    from jarvis_cyber.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert desktop.check_claude() == 1
    assert "--configure-claude" in capsys.readouterr().out
