"""Transcription locale avec faster-whisper (hors ligne après le premier téléchargement du modèle)."""

from __future__ import annotations

import importlib.util
import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

# Phrases que Whisper invente sur du silence ou du bruit
_HALLUCINATIONS = (
    "sous-titres",
    "sous titres",
    "amara.org",
    "merci d'avoir regardé",
    "abonnez-vous",
    "sous-titrage",
)


def stt_available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


class WhisperTranscriber:
    def __init__(self, model_size: str = "small", language: str = "fr", wake_word: str = "Jarvis") -> None:
        self.model_size = model_size
        self.language = language
        self._prompt = f"{wake_word.capitalize()},"
        self._model = None
        self._lock = threading.Lock()

    def load(self) -> None:
        """Charge le modèle (télécharge ~500 Mo pour « small » à la première utilisation)."""
        with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel

            logger.info("Chargement du modèle de transcription « %s »…", self.model_size)
            self._model = WhisperModel(self.model_size, device="auto", compute_type="int8")
            logger.info("Modèle de transcription prêt.")

    def transcribe(self, audio: np.ndarray) -> str:
        self.load()
        segments, _info = self._model.transcribe(
            np.asarray(audio, dtype=np.float32),
            language=self.language,
            beam_size=3,
            vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt=self._prompt,
        )
        parts = [s.text.strip() for s in segments if s.no_speech_prob < 0.6]
        text = " ".join(p for p in parts if p).strip()
        lowered = text.lower()
        if any(marker in lowered for marker in _HALLUCINATIONS):
            return ""
        return text
