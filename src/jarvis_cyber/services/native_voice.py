"""Assemblage du moteur vocal natif à partir de la configuration."""

from __future__ import annotations

from jarvis_cyber.config import settings
from jarvis_cyber.voice_native.audio import MicrophoneSource, microphone_available
from jarvis_cyber.voice_native.engine import NativeVoiceEngine
from jarvis_cyber.voice_native.stt import WhisperTranscriber, stt_available
from jarvis_cyber.voice_native.tts import Speaker

_engine: NativeVoiceEngine | None = None


def native_voice_available() -> bool:
    """Micro et transcription locale installés (extra « native »)."""
    return microphone_available() and stt_available()


def missing_components() -> list[str]:
    missing = []
    if not microphone_available():
        missing.append("sounddevice")
    if not stt_available():
        missing.append("faster-whisper")
    return missing


def get_native_voice() -> NativeVoiceEngine:
    global _engine
    if _engine is None:
        device: str | int | None = settings.mic_device or None
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        _engine = NativeVoiceEngine(
            transcriber=WhisperTranscriber(
                settings.stt_model, settings.stt_language, settings.wake_word
            ),
            speaker=Speaker(settings.native_tts_voice, settings.native_tts_rate),
            source_factory=lambda: MicrophoneSource(device),
            wake_word=settings.wake_word,
            followup_seconds=settings.voice_followup_seconds,
            barge_in=settings.voice_barge_in,
        )
    return _engine
