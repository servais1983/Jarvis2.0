"""Serveur MCP « systeme » : donne à Jarvis la main sur la machine.

Lancement : python -m jarvis_cyber.mcp_builtin.system_server

Les outils ne font qu'ouvrir des applications ou des pages, régler le son et
lire l'état de la machine. Rien n'est supprimé ni modifié sur le disque.
"""

from __future__ import annotations

import ast
import operator

from mcp.server.fastmcp import FastMCP

from jarvis_cyber.mcp_builtin.system_actions import ActionError, SystemActions

mcp = FastMCP("jarvis-systeme")
actions = SystemActions()

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


def _guard(call) -> str:
    try:
        return call()
    except ActionError as exc:
        return str(exc)


def _eval(node: ast.expr) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 200:
            raise ValueError("exposant trop grand")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("uniquement des nombres et + - * / ** %")


@mcp.tool()
def ouvrir_application(nom: str) -> str:
    """Ouvre une application installée sur l'ordinateur (ex. Safari, Spotify, Notes, Terminal)."""
    return _guard(lambda: actions.open_application(nom))


@mcp.tool()
def fermer_application(nom: str) -> str:
    """Ferme une application ouverte (Mac uniquement)."""
    return _guard(lambda: actions.quit_application(nom))


@mcp.tool()
def ouvrir_site(url: str) -> str:
    """Ouvre une adresse web dans le navigateur par défaut."""
    return _guard(lambda: actions.open_url(url))


@mcp.tool()
def recherche_web(requete: str) -> str:
    """Lance une recherche Google dans le navigateur."""
    return _guard(lambda: actions.web_search(requete))


@mcp.tool()
def recherche_youtube(requete: str) -> str:
    """Lance une recherche de vidéos sur YouTube."""
    return _guard(lambda: actions.youtube_search(requete))


@mcp.tool()
def regler_volume(pourcentage: int) -> str:
    """Règle le volume de sortie de l'ordinateur, de 0 à 100 (Mac uniquement)."""
    return _guard(lambda: actions.set_volume(pourcentage))


@mcp.tool()
def controle_musique(action: str) -> str:
    """Pilote l'application Musique : lecture, pause, suivant ou précédent (Mac uniquement)."""
    return _guard(lambda: actions.music_control(action))


@mcp.tool()
def heure_et_date() -> str:
    """Donne la date et l'heure locales de l'ordinateur."""
    return actions.now()


@mcp.tool()
def etat_machine() -> str:
    """Donne l'état de l'ordinateur : système, disque libre, charge processeur, batterie."""
    return actions.machine_status()


@mcp.tool()
def notification(message: str) -> str:
    """Affiche une notification système (Mac uniquement)."""
    return _guard(lambda: actions.notify(message))


@mcp.tool()
def calcul(expression: str) -> str:
    """Évalue une expression arithmétique simple, par exemple « (12 + 8) * 3 »."""
    try:
        result = _eval(ast.parse(expression, mode="eval").body)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
        return f"Impossible de calculer « {expression} » : {exc}"
    return f"{expression} = {result:g}"


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
