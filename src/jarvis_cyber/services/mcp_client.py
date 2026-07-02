"""Client MCP (Model Context Protocol) pour Jarvis.

Connecte Jarvis à des serveurs MCP externes déclarés dans un fichier de
configuration (format compatible Claude Desktop) et expose leurs outils :

    {
      "mcpServers": {
        "demo": {
          "command": "python",
          "args": ["examples/mcp_demo_server.py"],
          "env": {},
          "enabled": true
        }
      }
    }

Les sessions sont ouvertes à la demande (stdio) puis refermées : pas de
processus persistant, pas d'état à réconcilier. La liste des outils est
mise en cache brièvement pour garder l'interface réactive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis_cyber.config import settings

logger = logging.getLogger(__name__)

try:  # dépendance optionnelle : pip install "jarvis-cyber[mcp]"
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercé seulement sans l'extra [mcp]
    MCP_AVAILABLE = False


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


class MCPError(Exception):
    """Erreur d'accès à un serveur MCP."""


class MCPService:
    """Passerelle entre Jarvis et les serveurs MCP configurés."""

    _TOOLS_CACHE_TTL_SECONDS = 60

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = Path(config_path or settings.mcp_servers_file)
        self._tools_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    # ── Configuration ────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """Le SDK MCP est-il installé ?"""
        return MCP_AVAILABLE

    def servers(self) -> list[MCPServerConfig]:
        """Serveurs actifs déclarés dans le fichier de configuration."""
        if not self._config_path.exists():
            return []
        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Configuration MCP illisible (%s) : %s", self._config_path, exc)
            return []
        entries = raw.get("mcpServers", {})
        configs: list[MCPServerConfig] = []
        for name, entry in entries.items():
            if not isinstance(entry, dict) or not entry.get("command"):
                logger.warning("Serveur MCP « %s » ignoré : entrée invalide.", name)
                continue
            configs.append(
                MCPServerConfig(
                    name=name,
                    command=str(entry["command"]),
                    args=[str(a) for a in entry.get("args", [])],
                    env={str(k): str(v) for k, v in (entry.get("env") or {}).items()},
                    enabled=bool(entry.get("enabled", True)),
                )
            )
        return [c for c in configs if c.enabled]

    def _server(self, name: str) -> MCPServerConfig:
        for config in self.servers():
            if config.name == name:
                return config
        raise MCPError(f"Serveur MCP inconnu : {name}")

    # ── Opérations ───────────────────────────────────────────────

    @staticmethod
    def _resolve_command(command: str) -> str:
        """« python » dans la config = l'interpréteur qui exécute Jarvis.

        Permet à mcp_servers.json.example de fonctionner tel quel : le serveur
        MCP est lancé avec le Python du venv (où le SDK mcp est installé),
        sur toutes les plateformes.
        """
        if command in ("python", "python3"):
            return sys.executable
        return command

    async def _with_session(self, config: MCPServerConfig, operation):
        params = StdioServerParameters(
            command=self._resolve_command(config.command),
            args=config.args,
            env=config.env or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await operation(session)

    async def list_tools(self, server_name: str, use_cache: bool = True) -> list[dict[str, Any]]:
        """Outils exposés par un serveur, sous forme sérialisable."""
        if not MCP_AVAILABLE:
            raise MCPError("Le SDK MCP n'est pas installé (pip install 'jarvis-cyber[mcp]').")
        cached = self._tools_cache.get(server_name)
        if use_cache and cached and time.monotonic() - cached[0] < self._TOOLS_CACHE_TTL_SECONDS:
            return cached[1]
        config = self._server(server_name)

        async def op(session: ClientSession):
            result = await session.list_tools()
            return [
                {
                    "server": server_name,
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema or {},
                }
                for tool in result.tools
            ]

        try:
            tools = await asyncio.wait_for(
                self._with_session(config, op),
                timeout=settings.mcp_call_timeout_seconds,
            )
        except MCPError:
            raise
        except TimeoutError as exc:
            raise MCPError(f"Le serveur MCP « {server_name} » ne répond pas.") from exc
        except Exception as exc:
            raise MCPError(f"Connexion au serveur MCP « {server_name} » impossible : {exc}") from exc
        self._tools_cache[server_name] = (time.monotonic(), tools)
        return tools

    async def list_all_tools(self) -> list[dict[str, Any]]:
        """Outils de tous les serveurs actifs ; les serveurs en panne sont ignorés."""
        tools: list[dict[str, Any]] = []
        for config in self.servers():
            try:
                tools.extend(await self.list_tools(config.name))
            except MCPError as exc:
                logger.warning("MCP « %s » indisponible : %s", config.name, exc)
        return tools

    async def status(self) -> list[dict[str, Any]]:
        """État de chaque serveur configuré (connexion réellement testée)."""
        statuses: list[dict[str, Any]] = []
        for config in self.servers():
            entry: dict[str, Any] = {
                "name": config.name,
                "command": config.command,
                "connected": False,
                "tools_count": 0,
                "error": None,
            }
            if not MCP_AVAILABLE:
                entry["error"] = "SDK MCP non installé"
            else:
                try:
                    tools = await self.list_tools(config.name)
                    entry["connected"] = True
                    entry["tools_count"] = len(tools)
                except MCPError as exc:
                    entry["error"] = str(exc)
            statuses.append(entry)
        return statuses

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Appelle un outil MCP et renvoie son contenu texte agrégé."""
        if not MCP_AVAILABLE:
            raise MCPError("Le SDK MCP n'est pas installé (pip install 'jarvis-cyber[mcp]').")
        config = self._server(server_name)

        async def op(session: ClientSession):
            return await session.call_tool(tool_name, arguments or {})

        try:
            result = await asyncio.wait_for(
                self._with_session(config, op),
                timeout=settings.mcp_call_timeout_seconds,
            )
        except MCPError:
            raise
        except TimeoutError as exc:
            raise MCPError(
                f"L'outil « {tool_name} » de « {server_name} » n'a pas répondu à temps."
            ) from exc
        except Exception as exc:
            raise MCPError(f"Appel de « {tool_name} » sur « {server_name} » impossible : {exc}") from exc

        chunks: list[str] = []
        for item in result.content:
            text = getattr(item, "text", None)
            if text is not None:
                chunks.append(text)
            else:  # contenu non textuel (image, ressource…) : on le décrit
                chunks.append(f"[contenu {getattr(item, 'type', 'inconnu')}]")
        return {
            "server": server_name,
            "tool": tool_name,
            "is_error": bool(getattr(result, "isError", False)),
            "content": "\n".join(chunks),
        }


mcp_service = MCPService()
