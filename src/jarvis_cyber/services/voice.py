from __future__ import annotations

from io import BytesIO

from openai import OpenAI

from jarvis_cyber.config import settings


class VoiceServiceUnavailableError(RuntimeError):
    """Raised when voice features are requested without API credentials."""


class VoiceService:
    """Speech transcription and synthesis for the voice MVP."""

    def __init__(self) -> None:
        self._client = (
            OpenAI(api_key=settings.openai_api_key.get_secret_value())
            if settings.openai_api_key
            else None
        )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def transcribe(self, filename: str, content: bytes) -> str:
        client = self._require_client()
        audio_file = BytesIO(content)
        audio_file.name = filename
        transcription = client.audio.transcriptions.create(
            model=settings.transcription_model,
            file=audio_file,
        )
        return transcription.text

    def synthesize(self, text: str) -> bytes:
        client = self._require_client()
        response = client.audio.speech.create(
            model=settings.tts_model,
            voice=settings.tts_voice,
            input=text,
        )
        return response.read()

    def _require_client(self) -> OpenAI:
        if self._client is None:
            raise VoiceServiceUnavailableError
        return self._client


voice_service = VoiceService()
