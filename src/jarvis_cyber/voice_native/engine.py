"""Boucle vocale native : écoute permanente → mot d'éveil → commande → réponse parlée.

Le moteur n'interprète pas les commandes : il les publie (événement
`command`) et l'interface les route, exactement comme une phrase tapée.
Jarvis ne doit jamais se répondre à lui-même. Par défaut le micro est ignoré
pendant qu'il parle et un court instant après (réverbération de la pièce).
Avec l'interruption vocale activée, le micro reste ouvert mais toute phrase
qui a chevauché sa voix doit contenir le mot d'éveil et ne pas ressembler à
ce qu'il est en train de dire.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from jarvis_cyber.voice_native.vad import UtteranceSegmenter
from jarvis_cyber.voice_native.wake import extract_command

logger = logging.getLogger(__name__)

_STOP_WORDS = {"stop", "silence", "chut", "tais-toi", "tais toi", "arrête", "arrete", "ça suffit"}
# Dans une conversation ouverte, ces mots la referment sans rien déclencher
_CLOSERS = {
    "merci",
    "merci beaucoup",
    "merci jarvis",
    "ok",
    "ok merci",
    "d'accord",
    "c'est bon",
    "c'est tout",
    "rien",
    "non merci",
    "au revoir",
    "parfait",
}
_ECHO_TAIL_FRAMES = 27          # ~0,8 s de réverbération après la fin de sa phrase (trames de 30 ms)
_ECHO_MEMORY_SECONDS = 12.0     # durée pendant laquelle on reconnaît encore sa dernière réponse


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zà-ÿ0-9]+", text.lower())


class AudioSource(Protocol):
    def frames(self): ...
    def close(self) -> None: ...


class Transcriber(Protocol):
    def load(self) -> None: ...
    def transcribe(self, audio) -> str: ...


class NativeVoiceEngine:
    def __init__(
        self,
        transcriber: Transcriber,
        speaker,
        source_factory: Callable[[], AudioSource],
        wake_word: str = "jarvis",
        followup_seconds: float = 8.0,
        barge_in: bool = False,
    ) -> None:
        self._transcriber = transcriber
        self._speaker = speaker
        self._source_factory = source_factory
        self._wake_word = wake_word
        self._followup = followup_seconds
        self._barge_in = barge_in
        self._subscribers: list[queue.Queue] = []
        self._subscribers_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._source: AudioSource | None = None
        self._engaged_until = 0.0
        self._last_level_at = 0.0
        self._spoken_text = ""
        self._speech_seen_at = float("-inf")
        self.state = "stopped"
        self.last_error: str | None = None
        self.last_heard: str | None = None

    # ── Abonnés (interface) ──────────────────────────────────────

    def subscribe(self) -> queue.Queue:
        subscriber: queue.Queue = queue.Queue(maxsize=200)
        with self._subscribers_lock:
            self._subscribers.append(subscriber)
        subscriber.put({"type": "state", "state": self.state})
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._subscribers_lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def _emit(self, event: dict[str, Any]) -> None:
        with self._subscribers_lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                pass  # abonné trop lent : il rattrapera sur l'événement suivant

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self._emit({"type": "state", "state": state})

    # ── Cycle de vie ─────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self.last_error = None
        self._thread = threading.Thread(target=self._run, name="jarvis-voice", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        source = self._source
        if source is not None:
            source.close()
        self._speaker.stop()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        self._thread = None
        self._set_state("stopped")

    def run_blocking(self) -> None:
        """Exécute la boucle dans le fil courant jusqu'à épuisement de la source (tests)."""
        self._run()

    # ── Parole ───────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        self._spoken_text = text
        self._set_state("speaking")

        def done() -> None:
            # Après une réponse, la conversation reste ouverte quelques secondes
            self._engaged_until = time.monotonic() + self._followup
            if self.state == "speaking":
                self._set_state("listening" if self.running else "stopped")

        self._speaker.speak(text, on_done=done)

    def silence(self) -> None:
        self._speaker.stop()

    def _is_echo(self, text: str) -> bool:
        """Vrai si la phrase entendue est surtout faite des mots que Jarvis est en train de dire."""
        heard = _words(text)
        if not heard:
            return True
        spoken = set(_words(self._spoken_text))
        overlap = sum(1 for word in heard if word in spoken) / len(heard)
        return overlap >= 0.6

    # ── Boucle d'écoute ──────────────────────────────────────────

    def _run(self) -> None:
        try:
            self._set_state("loading")
            self._transcriber.load()
            self._source = self._source_factory()
            segmenter = UtteranceSegmenter()
            self._set_state("listening")
            self._emit({"type": "ready"})
            tainted = False  # la phrase en cours a-t-elle chevauché la voix de Jarvis ?
            frames_since_voice = _ECHO_TAIL_FRAMES
            for frame in self._source.frames():
                if self._speaker.speaking:
                    self._speech_seen_at = time.monotonic()
                    frames_since_voice = 0
                else:
                    frames_since_voice += 1
                own_voice = frames_since_voice < _ECHO_TAIL_FRAMES
                if own_voice and not self._barge_in:
                    segmenter.reset()
                    continue
                tainted = tainted or own_voice
                utterance = segmenter.feed(frame)
                self._publish_level(segmenter)
                if utterance is None:
                    if not segmenter.in_speech and not own_voice:
                        tainted = False
                    continue
                during_speech, tainted = tainted, False
                if not during_speech:
                    self._set_state("thinking")
                text = self._transcriber.transcribe(utterance)
                self._handle(text, during_speech=during_speech)
                if self.state == "thinking":
                    self._set_state("listening")
        except Exception as exc:  # micro absent, permission refusée, modèle introuvable…
            logger.exception("Boucle vocale arrêtée")
            self.last_error = str(exc)
            self._emit({"type": "error", "message": str(exc)})
        finally:
            self._source = None
            if self.state != "speaking":
                self._set_state("stopped")

    def _publish_level(self, segmenter: UtteranceSegmenter) -> None:
        now = time.monotonic()
        if now - self._last_level_at < 0.08:
            return
        self._last_level_at = now
        if self.state in ("listening", "hearing"):
            self._set_state("hearing" if segmenter.in_speech else "listening")
        self._emit({"type": "level", "level": round(min(1.0, segmenter.level * 12), 3)})

    def _handle(self, text: str, during_speech: bool = False) -> None:
        text = (text or "").strip()
        if not text:
            return
        result = extract_command(text, self._wake_word)
        if during_speech and (not result.heard or self._is_echo(text)):
            logger.info("Écarté (pendant sa propre voix) : %r", text)
            return
        recently_spoke = time.monotonic() - self._speech_seen_at < _ECHO_MEMORY_SECONDS
        if not result.heard and recently_spoke and self._is_echo(text):
            logger.info("Écarté (écho de sa dernière réponse) : %r", text)
            return
        self.last_heard = text
        engaged = time.monotonic() < self._engaged_until
        if not (result.heard or engaged):
            logger.info("Ignoré (sans mot d'éveil) : %r", text)
            self._emit({"type": "heard", "text": text, "addressed": False})
            return

        command = result.command
        if not result.heard and command.lower().strip(" .!") in _CLOSERS:
            logger.info("Conversation refermée : %r", text)
            self._engaged_until = 0.0
            return
        logger.info("Compris : %r → commande %r", text, command)
        if command.lower().strip(" .!") in _STOP_WORDS:
            self._speaker.stop()
            self._engaged_until = 0.0
            self._emit({"type": "stop"})
            return
        if self._speaker.speaking:
            self._speaker.stop()
        self._engaged_until = time.monotonic() + self._followup
        if command:
            self._emit({"type": "command", "text": command})
        else:
            self._emit({"type": "wake"})
