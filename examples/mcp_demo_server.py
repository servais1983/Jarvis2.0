#!/usr/bin/env python3
"""Serveur MCP de démonstration pour Jarvis.

Trois outils sûrs pour valider la chaîne complète orb → API → MCP :
  - heure_locale : l'heure du système qui héberge le serveur MCP
  - calcul       : évaluation d'une expression arithmétique simple
  - infos_systeme: plateforme, version Python et charge machine

Lancement autonome (pour test) :
    python examples/mcp_demo_server.py

Déclaration côté Jarvis (mcp_servers.json) :
    {
      "mcpServers": {
        "demo": {"command": "python", "args": ["examples/mcp_demo_server.py"]}
      }
    }
"""

from __future__ import annotations

import ast
import operator
import platform
from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("jarvis-demo")

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.expr) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Expression non autorisée : uniquement + - * / ** % et nombres.")


@mcp.tool()
def heure_locale() -> str:
    """Heure et date locales de la machine qui héberge ce serveur MCP."""
    return datetime.now().strftime("Nous sommes le %d/%m/%Y et il est %H:%M:%S.")


@mcp.tool()
def calcul(expression: str) -> str:
    """Évalue une expression arithmétique simple (ex. « (12 + 8) * 3 »)."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
    except (ValueError, SyntaxError, ZeroDivisionError) as exc:
        return f"Impossible de calculer « {expression} » : {exc}"
    rendered = f"{result:g}"
    return f"{expression} = {rendered}"


@mcp.tool()
def infos_systeme() -> str:
    """Plateforme et version Python de la machine hôte."""
    return (
        f"Système : {platform.system()} {platform.release()} ({platform.machine()}) · "
        f"Python {platform.python_version()}"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
