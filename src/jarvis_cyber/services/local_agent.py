"""Agent local Ollama avec outils MCP.

Donne un vrai cerveau local à Jarvis : le modèle Ollama reçoit les outils
des serveurs MCP connectés (format tool-calling) et décide lui-même quand
les appeler. La boucle exécute les appels demandés via le client MCP puis
renvoie la réponse finale.

Priorité du /chat : Ollama (local) → OpenAI (si configuré) → fallback local.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.services.mcp_client import MCPError, mcp_service

logger = logging.getLogger(__name__)

_TOOL_NAME_SEPARATOR = "__"
_MAX_TOOL_ROUNDS = 4
_PROBE_TIMEOUT_SECONDS = 1.5


@dataclass
class LocalAgentResult:
    answer: str
    model: str
    tools_used: list[str] = field(default_factory=list)


class LocalAgentUnavailableError(Exception):
    """Ollama injoignable ou en erreur : passer au moteur suivant."""


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


class LocalAgentService:
    """Boucle de tool-calling entre Ollama et les serveurs MCP."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        # Client injectable pour les tests ; sinon créé à chaque échange
        self._client = client

    @property
    def base_url(self) -> str:
        return settings.ollama_base_url.rstrip("/")

    def _http(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.ollama_timeout_seconds,
        )

    async def available(self) -> bool:
        """Ollama répond-il ? Sonde rapide pour ne jamais bloquer le chat."""
        try:
            client = self._http()
            try:
                response = await client.get("/api/version", timeout=_PROBE_TIMEOUT_SECONDS)
                return response.status_code == 200
            finally:
                if self._client is None:
                    await client.aclose()
        except httpx.HTTPError:
            return False

    # ── Outils MCP → format tool-calling ────────────────────────

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
                    "type": "function",
                    "function": {
                        "name": exposed,
                        "description": tool["description"] or tool["name"],
                        "parameters": tool["input_schema"]
                        or {"type": "object", "properties": {}},
                    },
                }
            )
        return definitions, index

    @staticmethod
    async def _run_tool(index: dict, exposed_name: str, arguments: dict) -> str:
        target = index.get(exposed_name)
        if target is None:
            return json.dumps({"error": f"Outil inconnu : {exposed_name}"})
        server, tool = target
        try:
            result = await mcp_service.call_tool(server, tool, arguments)
            return result["content"] or "(réponse vide)"
        except MCPError as exc:
            logger.warning("Appel MCP %s.%s en échec : %s", server, tool, exc)
            return json.dumps({"error": str(exc)})

    # ── Boucle de conversation ───────────────────────────────────

    async def chat(
        self,
        message: str,
        history: list[dict],
        system_prompt: str,
    ) -> LocalAgentResult:
        definitions, index = await self._tool_definitions()
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if not history or history[-1].get("content") != message:
            messages.append({"role": "user", "content": message})

        payload_base = {"model": settings.ollama_model, "stream": False}
        if definitions:
            payload_base["tools"] = definitions

        tools_used: list[str] = []
        client = self._http()
        try:
            for _ in range(_MAX_TOOL_ROUNDS + 1):
                try:
                    response = await client.post(
                        "/api/chat", json={**payload_base, "messages": messages}
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise LocalAgentUnavailableError(str(exc)) from exc

                reply = response.json().get("message", {})
                tool_calls = reply.get("tool_calls") or []
                if not tool_calls:
                    answer = (reply.get("content") or "").strip()
                    if not answer:
                        raise LocalAgentUnavailableError("Réponse vide du modèle local.")
                    return LocalAgentResult(
                        answer=answer,
                        model=f"ollama/{settings.ollama_model}",
                        tools_used=tools_used,
                    )

                messages.append(reply)
                for call in tool_calls:
                    function = call.get("function", {})
                    name = function.get("name", "")
                    arguments = function.get("arguments") or {}
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}
                    tools_used.append(name.replace(_TOOL_NAME_SEPARATOR, "."))
                    output = await self._run_tool(index, name, arguments)
                    messages.append(
                        {"role": "tool", "content": output, "tool_name": name}
                    )
            raise LocalAgentUnavailableError("Trop d'allers-retours d'outils sans réponse finale.")
        finally:
            if self._client is None:
                await client.aclose()


local_agent_service = LocalAgentService()
