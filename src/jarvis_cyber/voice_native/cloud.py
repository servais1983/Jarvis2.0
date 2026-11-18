"""Voix et écoute en ligne (OpenAI), en option, quand une clé `OPENAI_API_KEY` est configurée.

- Voix : synthèse neuronale (`gpt-4o-mini-tts`), à qui l'on décrit le ton voulu.
  Beaucoup plus naturelle que les voix système ; en cas d'échec, la voix système prend le relais.
- Écoute : le micro reste transcrit sur le Mac. Seules les phrases adressées à Jarvis
  (mot d'éveil entendu, ou conversation en cours) sont retranscrites en ligne
  (`gpt-4o-transcribe`) pour corriger les erreurs de la transcription locale.
  Le reste de ce que capte le micro ne quitte jamais la machine.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from collections.abc import Callable

import httpx
import numpy as np

from jarvis_cyber.voice_native.tts import Speaker, clean_for_speech

logger = logging.getLogger(__name__)

OPENAI_URL = "https://api.openai.com/v1"

JARVIS_VOICE_STYLE = (
    "Tu parles en français. Voix d'homme grave, posée et chaleureuse, diction impeccable "
    "et raffinée, comme un majordome britannique devenu intelligence artificielle. "
    "Débit fluide et assuré, jamais monotone ; une pointe d'ironie bienveillante quand "
    "le texte s'y prête. Aucune hésitation."
)


def wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Encode un signal mono float32 [-1, 1] en WAV 16 bits."""
    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


class CloudTranscriber:
    """Transcription locale pour tout, retranscription en ligne des seules phrases adressées."""

    def __init__(
        self,
        local,
        api_key: str,
        model: str = "gpt-4o-transcribe",
        language: str = "fr",
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._local = local
        self._api_key = api_key
        self.model = model
        self.language = language
        self._client = httpx.Client(base_url=OPENAI_URL, timeout=timeout, transport=transport)

    def load(self) -> None:
        self._local.load()

    def transcribe(self, audio: np.ndarray) -> str:
        return self._local.transcribe(audio)

    def refine(self, audio: np.ndarray, local_text: str) -> str:
        """Retranscrit en ligne ; garde le texte local si le service ne répond pas."""
        try:
            response = self._client.post(
                "/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": ("phrase.wav", wav_bytes(audio), "audio/wav")},
                data={
                    "model": self.model,
                    "language": self.language,
                    "prompt": getattr(self._local, "prompt", "") or "",
                },
            )
            response.raise_for_status()
            text = str(response.json().get("text", "")).strip()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Transcription en ligne indisponible, texte local conservé : %s", exc)
            return local_text
        if text and text != local_text:
            logger.info("Transcription corrigée en ligne : %r → %r", local_text, text)
        return text or local_text


class CloudSpeaker(Speaker):
    """Voix neuronale en ligne, lue avec `afplay` ; voix système si le service échoue."""

    def __init__(
        self,
        api_key: str,
        voice: str = "onyx",
        model: str = "gpt-4o-mini-tts",
        style: str = JARVIS_VOICE_STYLE,
        fallback: Speaker | None = None,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        player: str | None = None,
    ) -> None:
        super().__init__()
        self._api_key = api_key
        self.cloud_voice = voice
        self.model = model
        self.style = style
        self._fallback = fallback or Speaker()
        self._client = httpx.Client(base_url=OPENAI_URL, timeout=timeout, transport=transport)
        self._player = player or shutil.which("afplay")
        self._generation = 0
        self._busy = False  # vrai dès la demande, avant même que le son commence

    @property
    def available(self) -> bool:
        return self._player is not None or self._fallback.available

    @property
    def speaking(self) -> bool:
        return self._busy or super().speaking or self._fallback.speaking

    @property
    def voice(self) -> str | None:
        return f"{self.model} / {self.cloud_voice}" if self._player else self._fallback.voice

    def synthesize(self, text: str) -> bytes:
        response = self._client.post(
            "/audio/speech",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model,
                "voice": self.cloud_voice,
                "input": text,
                "instructions": self.style,
                "response_format": "mp3",
            },
        )
        response.raise_for_status()
        return response.content

    def speak(self, text: str, on_done: Callable[[], None] | None = None) -> bool:
        spoken = clean_for_speech(text)
        if not spoken:
            if on_done:
                on_done()
            return False
        self.stop()
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._busy = True

        def run() -> None:
            path = None
            try:
                try:
                    audio = self.synthesize(spoken) if self._player else b""
                except httpx.HTTPError as exc:
                    logger.warning("Voix en ligne indisponible, voix système utilisée : %s", exc)
                    audio = b""
                if generation != self._generation:
                    return  # interrompu pendant la synthèse
                if not audio:
                    done = threading.Event()
                    self._fallback.speak(spoken, on_done=done.set)
                    self._busy = False
                    done.wait()
                    return
                handle, path = tempfile.mkstemp(suffix=".mp3", prefix="jarvis-")
                with os.fdopen(handle, "wb") as out:
                    out.write(audio)
                with self._lock:
                    if generation != self._generation:
                        return
                    self._process = subprocess.Popen(
                        [self._player, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    process = self._process
                    self._busy = False
                process.wait()
            except OSError as exc:
                logger.warning("Lecture audio impossible : %s", exc)
            finally:
                if generation == self._generation:
                    self._busy = False
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                if on_done:
                    on_done()

        threading.Thread(target=run, name="jarvis-tts-cloud", daemon=True).start()
        return True

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            self._busy = False
        self._fallback.stop()
        super().stop()
