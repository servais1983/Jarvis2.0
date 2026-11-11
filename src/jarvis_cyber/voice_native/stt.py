"""Transcription locale avec faster-whisper (hors ligne après le premier téléchargement du modèle)."""

from __future__ import annotations

import importlib.util
import logging
import re
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


DEFAULT_VOCABULARY = (
    "Safari, Spotify, Chrome, Finder, Terminal, Notes, Mail, YouTube, Google, Ollama."
)


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-zà-ÿ0-9]+", text.lower())


class WhisperTranscriber:
    def __init__(
        self,
        model_size: str = "small",
        language: str = "fr",
        wake_word: str = "Jarvis",
        prompt: str = "",
    ) -> None:
        self.model_size = model_size
        self.language = language
        # L'amorce donne à Whisper l'orthographe du mot d'éveil et des noms propres.
        # Elle se termine par un point : une amorce ouverte (« Jarvis, ») lui fait
        # parfois croire que le mot a déjà été dit, et il ne le transcrit plus.
        self.prompt = prompt or f"{wake_word.capitalize()}. {DEFAULT_VOCABULARY}"
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

    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> str:
        self.load()
        used_prompt = self.prompt if prompt is None else prompt
        segments, _info = self._model.transcribe(
            np.asarray(audio, dtype=np.float32),
            language=self.language,
            beam_size=5,
            vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt=used_prompt or None,
        )
        parts = []
        for segment in segments:
            # Silence, transcription peu sûre ou texte qui boucle : on n'en fait pas une demande
            if segment.no_speech_prob >= 0.6:
                continue
            if segment.avg_logprob < -1.0 or segment.compression_ratio > 2.4:
                logger.info("Transcription écartée (peu fiable) : %r", segment.text)
                continue
            parts.append(segment.text.strip())
        text = " ".join(p for p in parts if p).strip()
        return "" if self.is_hallucination(text, used_prompt) else text

    @staticmethod
    def is_hallucination(text: str, prompt: str = "") -> bool:
        lowered = text.lower()
        if any(marker in lowered for marker in _HALLUCINATIONS):
            return True
        # Sur un son indistinct, Whisper peut réciter l'amorce elle-même
        words, prompt_words = _normalized_words(text), _normalized_words(prompt)
        if len(words) >= 3 and prompt_words:
            joined, prompt_joined = " ".join(words), " ".join(prompt_words)
            return joined in prompt_joined
        return False
