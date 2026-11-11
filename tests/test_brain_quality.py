"""Garde-fous sur la qualité des réponses : prompt, historique, repli, commandes directes."""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from jarvis_cyber.memory.store import memory_store
from jarvis_cyber.services import assistant as assistant_module
from jarvis_cyber.services import local_agent as local_agent_module
from jarvis_cyber.services.assistant import AssistantService
from jarvis_cyber.services.local_agent import (
    LocalAgentResult,
    LocalAgentService,
    _clean_answer,
    _tool_call_written_as_text,
)
from jarvis_cyber.services.mcp_client import MCPService

ROOT = Path(__file__).resolve().parent.parent


def test_direct_commands_javascript_suite() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node n'est pas installé")
    result = subprocess.run(
        [node, str(ROOT / "tests" / "js" / "intents_test.js")],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _capture_local_call(monkeypatch, answer: LocalAgentResult | None) -> dict:
    captured: dict = {}

    def fake(message, history, system_prompt):
        captured.update(message=message, history=history, prompt=system_prompt)
        return answer

    monkeypatch.setattr(AssistantService, "_try_local_agent", staticmethod(fake))
    return captured


def test_local_model_gets_a_short_prompt_without_soc_boilerplate(monkeypatch) -> None:
    captured = _capture_local_call(monkeypatch, None)
    AssistantService().respond("prompt-user", "prompt", "Pourquoi le ciel est bleu ?")
    prompt = captured["prompt"]
    assert "assistant personnel de Steve" in prompt
    assert "Appelle un outil uniquement quand la demande l'exige" in prompt
    assert "Connecteurs disponibles" not in prompt        # six lignes « non configuré » inutiles
    assert "Aucun playbook" not in prompt and "Aucun élément" not in prompt
    assert len(prompt) < 1800


def test_only_recent_turns_are_sent_to_the_local_model(monkeypatch) -> None:
    for index in range(15):
        memory_store.append(user_id="hist-user", session_id="longue", role="user", content=f"q{index}")
        memory_store.append(user_id="hist-user", session_id="longue", role="assistant", content=f"r{index}")
    captured = _capture_local_call(monkeypatch, None)
    AssistantService().respond("hist-user", "longue", "dernière question")
    assert len(captured["history"]) <= 8
    assert captured["history"][-1] == {"role": "user", "content": "dernière question"}


def test_fallback_sentences_are_not_stored_in_the_conversation(monkeypatch) -> None:
    _capture_local_call(monkeypatch, None)
    service = AssistantService()
    service.respond("fb-user", "repli", "Raconte-moi une blague")
    service.respond("fb-user", "repli", "Et une autre ?")
    turns = memory_store.recent(user_id="fb-user", session_id="repli", limit=20)
    assert [turn.role for turn in turns] == ["user", "user"]


@pytest.mark.parametrize(
    ("brain", "expected"),
    [
        ({"engine": "ollama", "pull": "idle", "ollama_running": True, "model": "llama3.1"}, "pas répondu à temps"),
        ({"engine": "aucun", "pull": "running", "ollama_running": True, "model": "llama3.1"}, "télécharge encore"),
        ({"engine": "aucun", "pull": "idle", "ollama_running": True, "model": "llama3.1"}, "n'est pas installé"),
        ({"engine": "aucun", "pull": "idle", "ollama_running": False, "model": "llama3.1"}, "Lance Ollama"),
    ],
)
def test_fallback_names_the_real_cause(monkeypatch, brain: dict, expected: str) -> None:
    monkeypatch.setattr(assistant_module, "brain_status", lambda: brain)
    assert expected in AssistantService._local_chat_fallback("question", 0)


def test_reasoning_tags_are_removed_from_answers() -> None:
    assert _clean_answer("<think>je réfléchis…</think>\nIl est midi.") == "Il est midi."
    assert _clean_answer("Bonjour </think>Steve") == "Bonjour Steve"


def test_tool_call_written_as_text_is_recognised() -> None:
    index = {"systeme__calcul": ("systeme", "calcul")}
    written = '{"name": "systeme__calcul", "parameters": {"expression": "6*7"}}'
    assert _tool_call_written_as_text(written, index) == {
        "name": "systeme__calcul",
        "arguments": {"expression": "6*7"},
    }
    assert _tool_call_written_as_text('Voici du JSON : {"name": "inconnu"}', index) is None
    assert _tool_call_written_as_text("Le ciel est bleu à cause de la diffusion.", index) is None


def test_ollama_request_has_enough_context_and_runs_written_tool_calls(monkeypatch, tmp_path) -> None:
    class FakeMCP(MCPService):
        async def list_all_tools(self):
            return [{"server": "systeme", "name": "calcul", "description": "calcule", "input_schema": {}}]

        async def call_tool(self, server, tool, arguments=None):
            return {"server": server, "tool": tool, "is_error": False, "content": "6*7 = 42"}

    monkeypatch.setattr(local_agent_module, "mcp_service", FakeMCP(config_path=str(tmp_path / "x.json")))
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:   # le modèle écrit l'appel d'outil dans son texte
            content = '{"name": "systeme__calcul", "parameters": {"expression": "6*7"}}'
        else:
            content = "<think>42</think>Cela fait 42."
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama.test")
    result = asyncio.run(
        LocalAgentService(client=http).chat(message="6 fois 7 ?", history=[], system_prompt="Jarvis")
    )
    assert result.answer == "Cela fait 42."
    assert result.tools_used == ["systeme.calcul"]
    assert bodies[0]["options"]["num_ctx"] >= 8192
    assert bodies[0]["options"]["repeat_penalty"] > 1
    assert any(m["role"] == "tool" and "42" in m["content"] for m in bodies[1]["messages"])


def test_fallback_explanation_is_not_repeated_word_for_word(monkeypatch) -> None:
    brain = {"engine": "aucun", "pull": "idle", "ollama_running": False, "model": "llama3.1"}
    monkeypatch.setattr(assistant_module, "brain_status", lambda: brain)
    first = AssistantService._local_chat_fallback("question", 0)
    second = AssistantService._local_chat_fallback("autre question", 0)
    assert "Lance Ollama" in first
    assert second == "Je n'ai toujours pas de moteur de langage pour répondre à ça."
    brain["ollama_running"] = True                 # la cause change : il le redit en entier
    assert "n'est pas installé" in AssistantService._local_chat_fallback("encore", 0)
