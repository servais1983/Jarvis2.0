import pytest

from jarvis_cyber.services.voice import VoiceService, VoiceServiceUnavailableError


def test_voice_service_requires_client() -> None:
    service = VoiceService()
    service._client = None

    with pytest.raises(VoiceServiceUnavailableError):
        service.synthesize("Bonjour")
