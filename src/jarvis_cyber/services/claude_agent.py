"""Cerveau Claude : l'API Messages d'Anthropic avec les outils MCP de Jarvis.

Activé seulement si une clé `ANTHROPIC_API_KEY` est configurée. Le texte des
demandes (jamais l'audio) est alors envoyé à Anthropic ; le micro, la
transcription et la voix restent sur la machine.

La boucle est écrite à la main parce que les outils viennent des serveurs MCP
connectés, découverts à l'exécution, et non de fonctions Python décorées.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re

from jarvis_cyber.config import settings
from jarvis_cyber.services.local_agent import LocalAgentResult
from jarvis_cyber.services.mcp_client import MCPError, mcp_service

logger = logging.getLogger(__name__)

_TOOL_NAME_SEPARATOR = "__"
_MAX_TOOL_ROUNDS = 6
# Si les classifieurs de sécurité déclinent une demande, l'API la rejoue sur le
# modèle de repli recommandé au lieu de renvoyer un refus sec.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeUnavailableError(Exception):
    """Claude n'a pas pu répondre : passer au moteur suivant."""


def claude_sdk_available() -> bool:
    return importlib.util.find_spec("anthropic") is not None


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)[:60]


def _alternating_history(history: list[dict]) -> list[dict]:
    """La conversation envoyée doit commencer par un message de l'utilisateur."""
    turns = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in history
        if turn.get("role") in ("user", "assistant") and turn.get("content")
    ]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


class ClaudeAgentService:
    def __init__(self, client=None) -> None:
        self._client = client          # injectable pour les tests
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return settings.anthropic_api_key is not None and claude_sdk_available()

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=settings.claude_timeout_seconds,
            )
        return self._client

    async def _tool_definitions(self) -> tuple[list[dict], dict[str, tuple[str, str]]]:
        definitions: list[dict] = []
        index: dict[str, tuple[str, str]] = {}
        try:
            tools = await mcp_service.list_all_tools()
        except MCPError:
            tools = []
        for tool in tools:
            exposed = f"{_sanitize(tool['server'])}{_TOOL_NAME_SEPARATOR}{_sanitize(tool['name'])}"
            index[exposed] = (tool["server"], tool["name"])
            definitions.append(
                {
                    "name": exposed,
                    "description": tool["description"] or tool["name"],
                    "input_schema": tool["input_schema"] or {"type": "object", "properties": {}},
                }
            )
        return definitions, index

    @staticmethod
    async def _run_tool(index: dict, block) -> dict:
        target = index.get(block.name)
        if target is None:
            return {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": f"Outil inconnu : {block.name}",
                "is_error": True,
            }
        server, tool = target
        arguments = block.input if isinstance(block.input, dict) else {}
        try:
            result = await mcp_service.call_tool(server, tool, arguments)
        except MCPError as exc:
            logger.warning("Appel MCP %s.%s en échec : %s", server, tool, exc)
            return {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(exc),
                "is_error": True,
            }
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result["content"] or "(réponse vide)",
            "is_error": bool(result["is_error"]),
        }

    async def chat(self, message: str, history: list[dict], system_prompt: str) -> LocalAgentResult:
        import anthropic

        client = self._get_client()
        definitions, index = await self._tool_definitions()
        messages = _alternating_history(history)
        if not messages or messages[-1] != {"role": "user", "content": message}:
            messages.append({"role": "user", "content": message})

        request: dict = {
            "model": settings.claude_model,
            "max_tokens": 8000,
            "system": system_prompt,
            "messages": messages,
            "output_config": {"effort": settings.claude_effort},
            "betas": [_FALLBACK_BETA],
            "fallbacks": "default",
        }
        if definitions:
            request["tools"] = definitions

        tools_used: list[str] = []
        try:
            for _ in range(_MAX_TOOL_ROUNDS + 1):
                response = await client.beta.messages.create(**request)

                if response.stop_reason == "refusal":
                    return self._result(
                        response, "Je ne peux pas t'aider sur cette demande.", tools_used
                    )
                if response.stop_reason == "pause_turn":
                    messages.append({"role": "assistant", "content": response.content})
                    continue
                if response.stop_reason != "tool_use":
                    text = " ".join(
                        block.text.strip() for block in response.content if block.type == "text"
                    ).strip()
                    if not text:
                        raise ClaudeUnavailableError(
                            f"Réponse sans texte (arrêt : {response.stop_reason})."
                        )
                    return self._result(response, text, tools_used)

                # Tous les résultats d'outils repartent dans un seul message utilisateur
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    tools_used.append(block.name.replace(_TOOL_NAME_SEPARATOR, "."))
                    results.append(await self._run_tool(index, block))
                messages.append({"role": "user", "content": results})
            raise ClaudeUnavailableError("Trop d'allers-retours d'outils sans réponse finale.")
        except anthropic.AuthenticationError as exc:
            raise self._unavailable("La clé API Anthropic est refusée.", exc) from exc
        except anthropic.PermissionDeniedError as exc:
            raise self._unavailable("La clé API Anthropic n'a pas accès à ce modèle.", exc) from exc
        except anthropic.NotFoundError as exc:
            raise self._unavailable(f"Modèle {settings.claude_model} introuvable.", exc) from exc
        except anthropic.RateLimitError as exc:
            raise self._unavailable("Limite de débit Anthropic atteinte.", exc) from exc
        except anthropic.APIStatusError as exc:
            raise self._unavailable(f"Erreur Anthropic {exc.status_code}.", exc) from exc
        except anthropic.APIConnectionError as exc:
            raise self._unavailable("Anthropic est injoignable (réseau).", exc) from exc

    def _result(self, response, text: str, tools_used: list[str]) -> LocalAgentResult:
        self.last_error = None
        return LocalAgentResult(answer=text, model=f"claude/{response.model}", tools_used=tools_used)

    def _unavailable(self, reason: str, exc: Exception) -> ClaudeUnavailableError:
        self.last_error = reason
        logger.warning("%s (%s)", reason, json.dumps(str(exc))[:300])
        return ClaudeUnavailableError(reason)


claude_agent_service = ClaudeAgentService()
