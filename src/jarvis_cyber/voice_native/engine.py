"""Boucle vocale native : écoute permanente → mot d'éveil → commande → réponse parlée.

Le moteur n'interprète pas les commandes : il les publie (événement
`command`) et l'interface les route, exactement comme une phrase tapée.
Fonctionnement en alternat : pendant que Jarvis parle, le micro est ignoré
(sinon il s'entendrait lui-même), sauf si l'interruption vocale est activée
— à réserver à un usage au casque.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from jarvis_cyber.voice_native.vad import UtteranceSegmenter
from jarvis_cyber.voice_native.wake import extract_command

logger = logging.getLogger(__name__)

_STOP_WORDS = {"stop", "silence", "chut", "tais-toi", "tais toi", "arrête", "arrete", "ça suffit"}


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
        self._set_state("speaking")

        def done() -> None:
            # Après une réponse, la conversation reste ouverte quelques secondes
            self._engaged_until = time.monotonic() + self._followup
            if self.state == "speaking":
                self._set_state("listening" if self.running else "stopped")

        self._speaker.speak(text, on_done=done)

    def silence(self) -> None:
        self._speaker.stop()

    # ── Boucle d'écoute ──────────────────────────────────────────

    def _run(self) -> None:
        try:
            self._set_state("loading")
            self._transcriber.load()
            self._source = self._source_factory()
            segmenter = UtteranceSegmenter()
            self._set_state("listening")
            self._emit({"type": "ready"})
            for frame in self._source.frames():
                if self._speaker.speaking and not self._barge_in:
                    segmenter.reset()
                    continue
                utterance = segmenter.feed(frame)
                self._publish_level(segmenter)
                if utterance is None:
                    continue
                self._set_state("thinking")
                text = self._transcriber.transcribe(utterance)
                self._handle(text)
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

    def _handle(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.last_heard = text
        result = extract_command(text, self._wake_word)
        engaged = time.monotonic() < self._engaged_until
        if not (result.heard or engaged):
            self._emit({"type": "heard", "text": text, "addressed": False})
            return

        command = result.command
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
