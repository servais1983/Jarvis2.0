import asyncio
import json
import subprocess
import sys

import pytest

from jarvis_cyber.mcp_builtin.system_actions import ActionError, SystemActions
from jarvis_cyber.services.mcp_client import MCP_AVAILABLE, MCPService


class Recorder:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.calls: list[list[str]] = []
        self._returncode = returncode
        self._stdout = stdout

    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, self._returncode, stdout=self._stdout, stderr="")


def test_open_application_on_mac_uses_aliases() -> None:
    runner = Recorder()
    actions = SystemActions(system="Darwin", runner=runner)
    assert actions.open_application("navigateur") == "Safari est ouvert."
    assert actions.open_application("Spotify") == "Spotify est ouvert."
    assert runner.calls == [["open", "-a", "Safari"], ["open", "-a", "Spotify"]]


def test_open_application_reports_missing_app() -> None:
    actions = SystemActions(system="Darwin", runner=Recorder(returncode=1))
    with pytest.raises(ActionError, match="ne trouve pas"):
        actions.open_application("Inexistante")


@pytest.mark.parametrize("name", ['Safari"; do shell script "rm -rf ~', "a/b", "x\\y", "$(reboot)", ""])
def test_application_names_cannot_inject_commands(name: str) -> None:
    runner = Recorder()
    actions = SystemActions(system="Darwin", runner=runner)
    with pytest.raises(ActionError):
        actions.open_application(name)
    with pytest.raises(ActionError):
        actions.quit_application(name)
    assert runner.calls == []


def test_web_actions_build_urls_without_a_shell() -> None:
    runner = Recorder()
    actions = SystemActions(system="Darwin", runner=runner)
    actions.open_url("apple.com")
    actions.web_search("météo Bruxelles & demain")
    actions.youtube_search("iron man jarvis")
    assert runner.calls[0] == ["open", "https://apple.com"]
    assert runner.calls[1] == ["open", "https://www.google.com/search?q=m%C3%A9t%C3%A9o+Bruxelles+%26+demain"]
    assert runner.calls[2][1].startswith("https://www.youtube.com/results?search_query=iron+man")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "ftp://x.y", "https://"])
def test_only_web_urls_are_opened(url: str) -> None:
    runner = Recorder()
    with pytest.raises(ActionError):
        SystemActions(system="Darwin", runner=runner).open_url(url)
    assert runner.calls == []


def test_volume_and_music_on_mac() -> None:
    runner = Recorder()
    actions = SystemActions(system="Darwin", runner=runner)
    assert "40" in actions.set_volume(40)
    actions.music_control("Pause")
    assert runner.calls[0] == ["osascript", "-e", "set volume output volume 40"]
    assert runner.calls[1] == ["osascript", "-e", 'tell application "Music" to pause']
    with pytest.raises(ActionError):
        actions.set_volume(140)
    with pytest.raises(ActionError):
        actions.music_control("explose")


def test_mac_only_actions_say_so_elsewhere() -> None:
    actions = SystemActions(system="Linux", runner=Recorder())
    with pytest.raises(ActionError, match="Mac"):
        actions.set_volume(10)
    with pytest.raises(ActionError, match="Mac"):
        actions.notify("bonjour")


def test_machine_status_reads_battery_on_mac() -> None:
    runner = Recorder(stdout="Now drawing from 'Battery Power'\n -InternalBattery-0\t87%; discharging")
    status = SystemActions(system="Darwin", runner=runner).machine_status()
    assert "batterie 87 pour cent" in status
    assert "disque libre" in status


def test_notification_text_cannot_break_out_of_the_script() -> None:
    runner = Recorder()
    SystemActions(system="Darwin", runner=runner).notify('fin" & do shell script "id\\')
    script = runner.calls[0][2]
    assert script.count('"') == 4  # uniquement les guillemets du message et du titre
    assert "\\" not in script


def test_packaged_app_replays_python_servers(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/Jarvis.app/Contents/MacOS/Jarvis")
    launch = MCPService._resolve_launch
    assert launch("python", ["-m", "jarvis_cyber.mcp_builtin.system_server"]) == (
        "/Applications/Jarvis.app/Contents/MacOS/Jarvis",
        ["--run-module", "jarvis_cyber.mcp_builtin.system_server"],
    )
    assert launch("python", ["examples/mcp_demo_server.py"])[1] == [
        "--run-script",
        "examples/mcp_demo_server.py",
    ]
    assert launch("npx", ["-y", "paquet"]) == ("npx", ["-y", "paquet"])


@pytest.mark.skipif(not MCP_AVAILABLE, reason="SDK MCP non installé")
def test_system_server_exposes_its_tools_over_mcp(tmp_path) -> None:
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "systeme": {
                        "command": "python",
                        "args": ["-m", "jarvis_cyber.mcp_builtin.system_server"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    service = MCPService(config_path=str(config))
    names = {tool["name"] for tool in asyncio.run(service.list_tools("systeme"))}
    assert {"ouvrir_application", "recherche_web", "regler_volume", "etat_machine", "calcul"} <= names
    result = asyncio.run(service.call_tool("systeme", "calcul", {"expression": "(21*2)+8"}))
    assert result["content"] == "(21*2)+8 = 50"
    huge = asyncio.run(service.call_tool("systeme", "calcul", {"expression": "9**9**9"}))
    assert "Impossible" in huge["content"]
