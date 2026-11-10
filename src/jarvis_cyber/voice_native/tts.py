"""Synthèse vocale par la voix du système : `say` sur macOS, espeak-ng sur Linux, SAPI sur Windows."""

from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

_VOICE_LINE = re.compile(r"^(.+?)\s{2,}([a-z]{2}[_-][A-Z]{2})\b")
# Du plus naturel au plus basique parmi les voix françaises de macOS
_PREFERRED_FR = ("Thomas (Premium)", "Thomas (Enhanced)", "Thomas", "Jacques")


def clean_for_speech(text: str) -> str:
    text = re.sub(r"[*_#`>|•]", " ", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text.lstrip("-")[:900]


def pick_french_voice(listing: str) -> str | None:
    """Choisit la meilleure voix française dans la sortie de `say -v ?`."""
    french = []
    for line in listing.splitlines():
        match = _VOICE_LINE.match(line)
        if match and match.group(2).replace("-", "_").startswith("fr"):
            french.append(match.group(1).strip())
    for name in _PREFERRED_FR:
        if name in french:
            return name
    return french[0] if french else None


class Speaker:
    def __init__(self, voice: str = "", rate: int = 185, system: str | None = None) -> None:
        self.system = system or platform.system()
        self.rate = rate
        self._voice = voice or None
        self._voice_resolved = bool(voice)
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        if self.system == "Darwin":
            return shutil.which("say") is not None
        if self.system == "Windows":
            return shutil.which("powershell") is not None
        return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None

    @property
    def speaking(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None

    @property
    def voice(self) -> str | None:
        if not self._voice_resolved and self.system == "Darwin":
            self._voice_resolved = True
            try:
                listing = subprocess.run(
                    ["say", "-v", "?"], capture_output=True, text=True, timeout=10, check=False
                ).stdout
                self._voice = pick_french_voice(listing)
            except (OSError, subprocess.SubprocessError):
                self._voice = None
        return self._voice

    def command(self, text: str) -> list[str]:
        if self.system == "Darwin":
            cmd = ["say", "-r", str(self.rate)]
            if self.voice:
                cmd += ["-v", self.voice]
            return [*cmd, text]
        if self.system == "Windows":
            escaped = text.replace("'", "''")
            script = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{escaped}')"
            )
            return ["powershell", "-NoProfile", "-Command", script]
        binary = shutil.which("espeak-ng") or shutil.which("espeak") or "espeak-ng"
        return [binary, "-v", "fr", "-s", str(min(self.rate, 175)), text]

    def speak(self, text: str, on_done: Callable[[], None] | None = None) -> bool:
        """Parle sans bloquer ; `on_done` est appelé à la fin (ou à l'interruption)."""
        spoken = clean_for_speech(text)
        if not spoken or not self.available:
            if on_done:
                on_done()
            return False
        self.stop()
        with self._lock:
            try:
                self._process = subprocess.Popen(
                    self.command(spoken), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except OSError as exc:
                logger.warning("Synthèse vocale indisponible : %s", exc)
                self._process = None
                if on_done:
                    on_done()
                return False
            process = self._process

        def wait() -> None:
            process.wait()
            if on_done:
                on_done()

        threading.Thread(target=wait, name="jarvis-tts", daemon=True).start()
        return True

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process is not None and process.poll() is None:
            process.terminate()
