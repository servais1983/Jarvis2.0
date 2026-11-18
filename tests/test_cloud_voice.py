"""Voix et écoute en ligne : requêtes envoyées, repli local, confidentialité."""

import io
import json
import threading
import wave

import httpx
import numpy as np

from jarvis_cyber.desktop.app import first_launch_setup, parse_dialog_answer
from jarvis_cyber.voice_native.cloud import CloudSpeaker, CloudTranscriber, wav_bytes
from jarvis_cyber.voice_native.engine import NativeVoiceEngine


class LocalStub:
    prompt = "Jarvis. Safari, Spotify."

    def __init__(self, text: str = "") -> None:
        self.text = text

    def load(self) -> None:
        pass

    def transcribe(self, _audio) -> str:
        return self.text


class FakeSpeaker:
    speaking = False

    def speak(self, text, on_done=None) -> bool:
        if on_done:
            on_done()
        return True

    def stop(self) -> None:
        pass


def test_wav_encoding_is_mono_16_bits() -> None:
    data = wav_bytes(np.zeros(1600, dtype=np.float32))
    with wave.open(io.BytesIO(data)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        assert wav.getnframes() == 1600


def test_refine_sends_audio_and_returns_the_better_text() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        return httpx.Response(200, json={"text": "Jarvis, ouvre Spotify."})

    transcriber = CloudTranscriber(
        LocalStub(), "sk-test", transport=httpx.MockTransport(handler)
    )
    text = transcriber.refine(np.zeros(1600, dtype=np.float32), "Jarvis, ouvre Spoti fait")
    assert text == "Jarvis, ouvre Spotify."
    assert seen["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer sk-test"
    assert b"gpt-4o-transcribe" in seen["body"] and b"RIFF" in seen["body"]


def test_refine_keeps_local_text_when_the_service_fails() -> None:
    transcriber = CloudTranscriber(
        LocalStub(), "sk-test", transport=httpx.MockTransport(lambda r: httpx.Response(500))
    )
    assert transcriber.refine(np.zeros(160, dtype=np.float32), "texte local") == "texte local"


def test_only_sentences_addressed_to_jarvis_go_online() -> None:
    sent = []

    class Spy(LocalStub):
        def refine(self, _audio, text):
            sent.append(text)
            return "Jarvis, ouvre Spotify"

    engine = NativeVoiceEngine(Spy(), FakeSpeaker(), lambda: None, followup_seconds=0.0)
    subscriber = engine.subscribe()
    audio = np.zeros(160, dtype=np.float32)
    engine._handle("on mange quoi ce soir", audio=audio)       # conversation ambiante
    engine._handle("Jarvis, ouvre Spoti fait", audio=audio)   # adressée à Jarvis
    assert sent == ["Jarvis, ouvre Spoti fait"]
    events = [subscriber.get_nowait() for _ in range(subscriber.qsize())]
    assert {"type": "command", "text": "ouvre Spotify"} in events


def test_cloud_speaker_asks_for_the_jarvis_voice_and_plays_it(tmp_path) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=b"ID3fake-mp3")

    speaker = CloudSpeaker(
        "sk-test", transport=httpx.MockTransport(handler), player="/usr/bin/true"
    )
    done = threading.Event()
    assert speaker.speak("**Bonjour** Steve.", on_done=done.set)
    assert done.wait(5)
    assert seen["model"] == "gpt-4o-mini-tts" and seen["voice"] == "onyx"
    assert seen["input"] == "Bonjour Steve."
    assert "majordome" in seen["instructions"]
    assert not speaker.speaking


def test_cloud_speaker_falls_back_to_the_system_voice() -> None:
    spoken = []

    class Fallback(FakeSpeaker):
        available = True

        def speak(self, text, on_done=None):
            spoken.append(text)
            return super().speak(text, on_done)

    speaker = CloudSpeaker(
        "sk-test",
        fallback=Fallback(),
        transport=httpx.MockTransport(lambda r: httpx.Response(401)),
        player="/usr/bin/true",
    )
    done = threading.Event()
    speaker.speak("Bonjour.", on_done=done.set)
    assert done.wait(5)
    assert spoken == ["Bonjour."]


def test_first_launch_asks_once_for_missing_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    asked = []

    def asker(prompt: str) -> str:
        asked.append(prompt)
        return "sk-ant-x" if "Anthropic" in prompt else ""

    assert first_launch_setup(tmp_path, asker) == ["ANTHROPIC_API_KEY"]
    assert len(asked) == 2
    env = (tmp_path / ".env").read_text()
    assert "ANTHROPIC_API_KEY=sk-ant-x" in env and "OPENAI_API_KEY" not in env
    assert oct((tmp_path / ".env").stat().st_mode)[-3:] == "600"
    assert first_launch_setup(tmp_path, asker) == []   # jamais redemandé
    assert len(asked) == 2


def test_dialog_answer_parsing() -> None:
    assert parse_dialog_answer("button returned:Enregistrer, text returned:sk-ant-123\n") == "sk-ant-123"
    assert parse_dialog_answer("button returned:Plus tard") == ""
