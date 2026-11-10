"""Actions locales sur la machine : applications, web, volume, état.

Séparé du serveur MCP pour être testable sans le SDK. Aucune commande
arbitraire n'est exécutée : chaque action construit une ligne de commande
fixe (jamais de shell) à partir d'arguments validés.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote_plus, urlparse

Runner = Callable[[list[str]], subprocess.CompletedProcess]

_APP_NAME = re.compile(r"^[\w .+\-&']{1,60}$", re.UNICODE)

# Noms parlés → nom réel de l'application macOS
_MAC_ALIASES = {
    "navigateur": "Safari",
    "safari": "Safari",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "firefox": "Firefox",
    "terminal": "Terminal",
    "finder": "Finder",
    "fichiers": "Finder",
    "musique": "Music",
    "spotify": "Spotify",
    "notes": "Notes",
    "calendrier": "Calendar",
    "mail": "Mail",
    "messages": "Messages",
    "calculatrice": "Calculator",
    "reglages": "System Settings",
    "réglages": "System Settings",
    "preferences": "System Settings",
    "préférences": "System Settings",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "photos": "Photos",
    "plans": "Maps",
}


class ActionError(Exception):
    """Action refusée ou impossible ; le message est destiné à être lu à voix haute."""


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)


class SystemActions:
    def __init__(self, system: str | None = None, runner: Runner | None = None) -> None:
        self.system = system or platform.system()
        self._run = runner or _default_runner

    # ── Applications ─────────────────────────────────────────────

    def open_application(self, name: str) -> str:
        name = name.strip()
        if not _APP_NAME.match(name):
            raise ActionError("Nom d'application invalide.")
        if self.system == "Darwin":
            target = _MAC_ALIASES.get(name.lower(), name)
            result = self._run(["open", "-a", target])
            if result.returncode != 0:
                raise ActionError(f"Je ne trouve pas l'application {name} sur ce Mac.")
            return f"{target} est ouvert."
        if self.system == "Windows":
            result = self._run(["cmd", "/c", "start", "", name])
        else:
            binary = shutil.which(name.lower().replace(" ", "-")) or shutil.which(name.lower())
            if binary is None:
                raise ActionError(f"Je ne trouve pas l'application {name}.")
            result = self._run([binary])
        if result.returncode != 0:
            raise ActionError(f"Impossible d'ouvrir {name}.")
        return f"{name} est ouvert."

    def quit_application(self, name: str) -> str:
        name = name.strip()
        if not _APP_NAME.match(name):
            raise ActionError("Nom d'application invalide.")
        if self.system != "Darwin":
            raise ActionError("Fermer une application n'est disponible que sur Mac.")
        target = _MAC_ALIASES.get(name.lower(), name)
        result = self._run(["osascript", "-e", f'tell application "{target}" to quit'])
        if result.returncode != 0:
            raise ActionError(f"Je n'ai pas pu fermer {name}.")
        return f"{target} est fermé."

    # ── Web ──────────────────────────────────────────────────────

    def open_url(self, url: str) -> str:
        url = url.strip()
        if "://" not in url:
            # « mailto:… », « javascript:… » : un autre schéma, pas une adresse web
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:(?!\d)", url):
                raise ActionError("Je n'ouvre que des adresses web http ou https.")
            url = f"https://{url}"
        parsed = urlparse(url)
        host_ok = re.fullmatch(r"[A-Za-z0-9.\-]+(:\d{1,5})?", parsed.netloc or "")
        if parsed.scheme not in ("http", "https") or not host_ok:
            raise ActionError("Je n'ouvre que des adresses web http ou https.")
        self._open_external(url)
        return f"J'ai ouvert {parsed.netloc}."

    def web_search(self, query: str) -> str:
        query = query.strip()
        if not query:
            raise ActionError("Il me faut un sujet de recherche.")
        self._open_external(f"https://www.google.com/search?q={quote_plus(query)}")
        return f"Recherche lancée pour « {query} »."

    def youtube_search(self, query: str) -> str:
        query = query.strip()
        if not query:
            raise ActionError("Il me faut un sujet de recherche.")
        self._open_external(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
        return f"Recherche YouTube lancée pour « {query} »."

    def _open_external(self, url: str) -> None:
        if self.system == "Darwin":
            cmd = ["open", url]
        elif self.system == "Windows":
            cmd = ["cmd", "/c", "start", "", url]
        else:
            cmd = ["xdg-open", url]
        result = self._run(cmd)
        if result.returncode != 0:
            raise ActionError("Je n'ai pas pu ouvrir le navigateur.")

    # ── Son ──────────────────────────────────────────────────────

    def set_volume(self, percent: int) -> str:
        if not 0 <= int(percent) <= 100:
            raise ActionError("Le volume doit être entre 0 et 100.")
        if self.system != "Darwin":
            raise ActionError("Le réglage du volume n'est disponible que sur Mac.")
        result = self._run(["osascript", "-e", f"set volume output volume {int(percent)}"])
        if result.returncode != 0:
            raise ActionError("Je n'ai pas pu régler le volume.")
        return f"Volume réglé à {int(percent)} pour cent."

    def music_control(self, action: str) -> str:
        commands = {
            "lecture": "play",
            "pause": "pause",
            "suivant": "next track",
            "precedent": "previous track",
            "précédent": "previous track",
        }
        verb = commands.get(action.strip().lower())
        if verb is None:
            raise ActionError("Action musique inconnue : lecture, pause, suivant ou précédent.")
        if self.system != "Darwin":
            raise ActionError("Le contrôle de la musique n'est disponible que sur Mac.")
        result = self._run(["osascript", "-e", f'tell application "Music" to {verb}'])
        if result.returncode != 0:
            raise ActionError("Je n'ai pas pu piloter l'application Musique.")
        return f"Musique : {action.strip().lower()}."

    # ── Informations ─────────────────────────────────────────────

    def now(self) -> str:
        return datetime.now().strftime("Nous sommes le %d/%m/%Y, il est %H heures %M.")

    def machine_status(self) -> str:
        parts = [f"Système {self.system} {platform.release()}"]
        usage = shutil.disk_usage(os.path.expanduser("~"))
        parts.append(f"disque libre {usage.free // 1024**3} Go sur {usage.total // 1024**3}")
        if hasattr(os, "getloadavg"):
            parts.append(f"charge processeur {os.getloadavg()[0]:.1f}")
        if self.system == "Darwin":
            battery = self._run(["pmset", "-g", "batt"])
            match = re.search(r"(\d+)%", battery.stdout or "")
            if match:
                parts.append(f"batterie {match.group(1)} pour cent")
        return ", ".join(parts) + "."

    def notify(self, message: str) -> str:
        message = message.strip().replace('"', "'").replace("\\", "")[:200]
        if not message:
            raise ActionError("Notification vide.")
        if self.system != "Darwin":
            raise ActionError("Les notifications ne sont disponibles que sur Mac.")
        self._run(
            ["osascript", "-e", f'display notification "{message}" with title "J.A.R.V.I.S."']
        )
        return "Notification affichée."
