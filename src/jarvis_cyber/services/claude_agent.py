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
from collections.abc import Callable

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


class _ModelNotUsableError(Exception):
    """Ce modèle précis est refusé (accès, compte, requête) : un autre modèle peut répondre."""

    def __init__(self, reason: str, cause: Exception) -> None:
        super().__init__(f"{reason} ({str(cause)[:300]})")
        self.reason = reason


def _echoable(content: list) -> list:
    """Contenu d'une réponse tel qu'il peut être renvoyé dans la suite de la boucle.

    Après un repli en cours de flux, un bloc `fallback` marque la frontière : les blocs
    de réflexion et d'appel d'outil produits avant elle par le modèle refusé ne doivent
    pas être renvoyés. Le texte, et tout ce qui suit la frontière, est gardé tel quel.
    """
    boundary = max(
        (i for i, block in enumerate(content) if getattr(block, "type", None) == "fallback"),
        default=-1,
    )
    if boundary < 0:
        return content
    internal = {"thinking", "redacted_thinking", "tool_use", "server_tool_use"}
    return [
        block
        for i, block in enumerate(content)
        if i >= boundary or getattr(block, "type", None) not in internal
    ]


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

    async def chat(
        self,
        message: str,
        history: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> LocalAgentResult:
        """Répond avec le modèle configuré ; s'il est refusé au compte, avec le modèle de secours.

        Avec `on_text`, la réponse arrive en flux : chaque morceau de texte est transmis
        dès sa génération, pour que la voix commence avant la fin de la réponse.
        """
        try:
            return await self._chat_with(
                settings.claude_model, message, history, system_prompt, on_text
            )
        except _ModelNotUsableError as exc:
            fallback = settings.claude_fallback_model
            if not fallback or fallback == settings.claude_model:
                raise self._unavailable(exc.reason, exc) from exc
            logger.warning("%s Nouvel essai avec %s.", exc.reason, fallback)
            try:
                result = await self._chat_with(fallback, message, history, system_prompt, on_text)
            except _ModelNotUsableError as second:
                raise self._unavailable(second.reason, second) from second
            # Le secours a répondu, mais l'utilisateur doit savoir que le premier modèle est refusé
            self.last_error = f"{exc.reason} J'utilise {fallback} à la place."
            return result

    async def _chat_with(
        self,
        model: str,
        message: str,
        history: list[dict],
        system_prompt: str,
        on_text: Callable[[str], None] | None = None,
    ) -> LocalAgentResult:
        import anthropic

        client = self._get_client()
        definitions, index = await self._tool_definitions()
        messages = _alternating_history(history)
        if not messages or messages[-1] != {"role": "user", "content": message}:
            messages.append({"role": "user", "content": message})

        # Pas de paramètre `thinking` : sur ces modèles la réflexion est toujours active et
        # se règle par l'effort. Pendant la boucle d'outils, `system` et `tools` ne changent
        # pas et l'historique est seulement complété, ce qu'exige le contrôle d'historique.
        request: dict = {
            "model": model,
            "max_tokens": 8000,
            "system": system_prompt,
            "messages": messages,
            "output_config": {"effort": settings.claude_effort},
            "betas": [_FALLBACK_BETA],
            "fallbacks": "default",
        }
        if definitions:
            request["tools"] = definitions
        if settings.claude_fast:
            request["speed"] = "fast"

        tools_used: list[str] = []
        try:
            for _ in range(_MAX_TOOL_ROUNDS + 1):
                response = await self._call(client, request, on_text)

                if response.stop_reason == "refusal":
                    return self._result(
                        response, "Je ne peux pas t'aider sur cette demande.", tools_used
                    )
                if response.stop_reason == "pause_turn":
                    messages.append({"role": "assistant", "content": _echoable(response.content)})
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
                messages.append({"role": "assistant", "content": _echoable(response.content)})
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
            raise _ModelNotUsableError(f"Ce compte n'a pas accès à {model}.", exc) from exc
        except anthropic.NotFoundError as exc:
            raise _ModelNotUsableError(f"Le modèle {model} est introuvable.", exc) from exc
        except anthropic.BadRequestError as exc:
            # Par exemple : compte sans conservation des données 30 jours, exigée par Fable
            raise _ModelNotUsableError(f"L'API refuse la requête pour {model}.", exc) from exc
        except anthropic.RateLimitError as exc:
            raise self._unavailable("Limite de débit Anthropic atteinte.", exc) from exc
        except anthropic.APIStatusError as exc:
            raise self._unavailable(f"Erreur Anthropic {exc.status_code}.", exc) from exc
        except anthropic.APIConnectionError as exc:
            raise self._unavailable("Anthropic est injoignable (réseau).", exc) from exc

    @staticmethod
    async def _call(client, request: dict, on_text: Callable[[str], None] | None):
        if on_text is None:
            return await client.beta.messages.create(**request)
        async with client.beta.messages.stream(**request) as stream:
            async for chunk in stream.text_stream:
                on_text(chunk)
            return await stream.get_final_message()

    def _result(self, response, text: str, tools_used: list[str]) -> LocalAgentResult:
        self.last_error = None
        return LocalAgentResult(answer=text, model=f"claude/{response.model}", tools_used=tools_used)

    def _unavailable(self, reason: str, exc: Exception) -> ClaudeUnavailableError:
        self.last_error = reason
        logger.warning("%s (%s)", reason, json.dumps(str(exc))[:300])
        return ClaudeUnavailableError(reason)


claude_agent_service = ClaudeAgentService()
