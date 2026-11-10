import queue
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from jarvis_cyber.api.main import app
from jarvis_cyber.voice_native.audio import FRAME_SAMPLES, SAMPLE_RATE, WavFileSource
from jarvis_cyber.voice_native.engine import NativeVoiceEngine
from jarvis_cyber.voice_native.tts import Speaker, clean_for_speech, pick_french_voice
from jarvis_cyber.voice_native.vad import UtteranceSegmenter
from jarvis_cyber.voice_native.wake import extract_command

client = TestClient(app)


# ── Mot d'éveil ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "heard",
    ["Jarvis", "jarvis,", "Jarvi", "Jervis", "Javis", "Djarvis", "Charvis", "Jarvisse", "JARVIS!"],
)
def test_wake_word_variants_are_recognised(heard: str) -> None:
    result = extract_command(f"{heard} ouvre Safari")
    assert result.heard is True
    assert result.command == "ouvre Safari"


@pytest.mark.parametrize("text", ["le service est en panne", "je vais à Paris", "gervais arrive", "travis"])
def test_similar_words_do_not_wake(text: str) -> None:
    assert extract_command(text).heard is False


def test_wake_word_alone_and_at_the_end() -> None:
    assert extract_command("Jarvis ?") == extract_command("Jarvis ?").__class__(True, "")
    assert extract_command("Ouvre les dossiers, Jarvis.").command == "Ouvre les dossiers"
    assert extract_command("Ok Jarvis, quelle heure est-il ?").command == "quelle heure est-il"


def test_custom_wake_word() -> None:
    assert extract_command("Friday lance la musique", wake_word="friday").command == "lance la musique"
    assert extract_command("Jarvis lance la musique", wake_word="friday").heard is False


# ── Découpage en phrases ─────────────────────────────────────────


def _tone(seconds: float, amplitude: float = 0.2) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _feed_all(segmenter: UtteranceSegmenter, audio: np.ndarray) -> list[np.ndarray]:
    found = []
    for start in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        utterance = segmenter.feed(audio[start : start + FRAME_SAMPLES])
        if utterance is not None:
            found.append(utterance)
    return found


def test_segmenter_isolates_one_utterance() -> None:
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    audio = np.concatenate([silence, _tone(1.0), silence])
    found = _feed_all(UtteranceSegmenter(), audio)
    assert len(found) == 1
    assert 0.9 * SAMPLE_RATE < len(found[0]) < 2.2 * SAMPLE_RATE


def test_segmenter_ignores_clicks_and_steady_noise() -> None:
    rng = np.random.default_rng(1)
    noise = (0.004 * rng.standard_normal(3 * SAMPLE_RATE)).astype(np.float32)
    noise[SAMPLE_RATE : SAMPLE_RATE + 400] += 0.5  # clic de 25 ms
    assert _feed_all(UtteranceSegmenter(), noise) == []


def test_segmenter_splits_two_utterances() -> None:
    gap = np.zeros(int(1.2 * SAMPLE_RATE), dtype=np.float32)
    audio = np.concatenate([gap, _tone(0.8), gap, _tone(0.6), gap])
    assert len(_feed_all(UtteranceSegmenter(), audio)) == 2


# ── Synthèse ─────────────────────────────────────────────────────


def test_pick_french_voice_prefers_best_quality() -> None:
    listing = (
        "Alex                en_US    # Most people recognize me by my voice.\n"
        "Amélie              fr_CA    # Bonjour, je m'appelle Amélie.\n"
        "Thomas              fr_FR    # Bonjour, je m'appelle Thomas.\n"
        "Thomas (Enhanced)   fr_FR    # Bonjour, je m'appelle Thomas.\n"
    )
    assert pick_french_voice(listing) == "Thomas (Enhanced)"
    assert pick_french_voice("Alex   en_US   # hello\n") is None


def test_speaker_builds_safe_commands() -> None:
    mac = Speaker(voice="Thomas", rate=190, system="Darwin")
    assert mac.command("Bonjour Steve") == ["say", "-r", "190", "-v", "Thomas", "Bonjour Steve"]
    assert clean_for_speech("--version **gras** `code`") == "version gras code"


# ── Moteur complet avec transcription simulée ────────────────────


class FakeSpeaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.speaking = False
        self.stopped = 0

    def speak(self, text, on_done=None) -> bool:
        self.spoken.append(text)
        if on_done:
            on_done()
        return True

    def stop(self) -> None:
        self.stopped += 1


class ScriptedTranscriber:
    """Rend les phrases d'un script, une par segment audio détecté."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def load(self) -> None:
        pass

    def transcribe(self, _audio) -> str:
        return self._lines.pop(0) if self._lines else ""


def _write_wav(path, audio: np.ndarray) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes((audio * 32767).astype(np.int16).tobytes())


def _events(engine: NativeVoiceEngine, subscriber: queue.Queue) -> list[dict]:
    engine.run_blocking()
    collected = []
    while not subscriber.empty():
        collected.append(subscriber.get())
    return [e for e in collected if e["type"] not in ("level", "state")]


def _three_utterances(tmp_path):
    gap = np.zeros(int(1.2 * SAMPLE_RATE), dtype=np.float32)
    path = tmp_path / "voix.wav"
    _write_wav(path, np.concatenate([_tone(0.8), gap, _tone(0.8), gap, _tone(0.8)]))
    return path


def test_engine_ignores_speech_without_wake_word(tmp_path) -> None:
    path = _three_utterances(tmp_path)
    engine = NativeVoiceEngine(
        ScriptedTranscriber(["il fait beau", "Jarvis, ouvre Safari", "merci"]),
        FakeSpeaker(),
        lambda: WavFileSource(path),
        followup_seconds=0.0,
    )
    events = _events(engine, engine.subscribe())
    assert events[0] == {"type": "ready"}
    assert events[1] == {"type": "heard", "text": "il fait beau", "addressed": False}
    assert events[2] == {"type": "command", "text": "ouvre Safari"}
    assert events[3]["type"] == "heard"  # fenêtre de suivi fermée : « merci » est ignoré


def test_engine_follow_up_does_not_need_wake_word(tmp_path) -> None:
    path = _three_utterances(tmp_path)
    engine = NativeVoiceEngine(
        ScriptedTranscriber(["Jarvis", "quelle heure est-il", "et demain ?"]),
        FakeSpeaker(),
        lambda: WavFileSource(path),
        followup_seconds=60.0,
    )
    events = _events(engine, engine.subscribe())
    assert [e["type"] for e in events] == ["ready", "wake", "command", "command"]
    assert events[2]["text"] == "quelle heure est-il"


def test_engine_stop_word_silences_jarvis(tmp_path) -> None:
    path = _three_utterances(tmp_path)
    speaker = FakeSpeaker()
    engine = NativeVoiceEngine(
        ScriptedTranscriber(["Jarvis, tais-toi", "", ""]), speaker, lambda: WavFileSource(path)
    )
    events = _events(engine, engine.subscribe())
    assert {"type": "stop"} in events
    assert speaker.stopped >= 1


def test_engine_reports_errors_instead_of_crashing() -> None:
    def broken_source():
        raise OSError("aucun micro")

    engine = NativeVoiceEngine(ScriptedTranscriber([]), FakeSpeaker(), broken_source)
    events = _events(engine, engine.subscribe())
    assert events == [{"type": "error", "message": "aucun micro"}]
    assert engine.last_error == "aucun micro"
    assert engine.state == "stopped"


# ── API ──────────────────────────────────────────────────────────


def test_status_endpoint_reports_missing_components() -> None:
    body = client.get("/voice/native/status").json()
    assert body["running"] is False
    assert body["wake_word"] == "jarvis"
    assert isinstance(body["missing"], list)
    assert body["available"] is (body["missing"] == [])


# ── Garde-fous de transcription ──────────────────────────────────


def test_transcriber_prompt_is_closed_and_customisable() -> None:
    from jarvis_cyber.voice_native.stt import WhisperTranscriber

    default = WhisperTranscriber(wake_word="jarvis")
    assert default.prompt.startswith("Jarvis. ") and default.prompt.endswith(".")
    assert WhisperTranscriber(prompt="Jarvis. Figma, Xcode.").prompt == "Jarvis. Figma, Xcode."


def test_recited_prompt_and_subtitle_ghosts_are_discarded() -> None:
    from jarvis_cyber.voice_native.stt import WhisperTranscriber

    prompt = WhisperTranscriber().prompt
    is_ghost = WhisperTranscriber.is_hallucination
    assert is_ghost("Safari, Spotify, Chrome", prompt)
    assert is_ghost("Sous-titres réalisés par la communauté d'Amara.org", prompt)
    assert not is_ghost("Jarvis", prompt)                       # le mot d'éveil seul reste valable
    assert not is_ghost("Jarvis, ouvre Safari", prompt)
    assert not is_ghost("ouvre Spotify et Chrome", prompt)


# ── Interruption à la voix pendant que Jarvis parle ──────────────


def _engine_while_speaking(spoken: str) -> tuple[NativeVoiceEngine, FakeSpeaker, queue.Queue]:
    speaker = FakeSpeaker()
    engine = NativeVoiceEngine(ScriptedTranscriber([]), speaker, lambda: None)
    engine._spoken_text = spoken
    return engine, speaker, engine.subscribe()


def _drain(subscriber: queue.Queue) -> list[dict]:
    events = []
    while not subscriber.empty():
        events.append(subscriber.get())
    return [e for e in events if e["type"] != "state"]


def test_jarvis_does_not_interrupt_himself_on_his_own_echo() -> None:
    spoken = "Je suis Jarvis, ton copilote cybersécurité et assistant personnel, Steve."
    engine, speaker, subscriber = _engine_while_speaking(spoken)
    engine._handle("je suis Jarvis ton copilote cyber sécurité", during_speech=True)
    engine._handle("et assistant personnel Steve", during_speech=True)
    assert _drain(subscriber) == []
    assert speaker.stopped == 0


def test_talk_nearby_without_wake_word_does_not_interrupt() -> None:
    engine, speaker, subscriber = _engine_while_speaking("Tous les systèmes sont opérationnels.")
    engine._engaged_until = float("inf")          # même en conversation ouverte
    engine._handle("tu as vu le match hier soir", during_speech=True)
    assert _drain(subscriber) == []
    assert speaker.stopped == 0


def test_wake_word_interrupts_speech() -> None:
    engine, speaker, subscriber = _engine_while_speaking("Tous les systèmes sont opérationnels.")
    engine._handle("Jarvis, stop", during_speech=True)
    assert _drain(subscriber) == [{"type": "stop"}]
    assert speaker.stopped == 1

    engine, speaker, subscriber = _engine_while_speaking("Voici la file de travail priorisée.")
    speaker.speaking = True
    engine._handle("Jarvis, ouvre plutôt Safari", during_speech=True)
    assert _drain(subscriber) == [{"type": "command", "text": "ouvre plutôt Safari"}]
    assert speaker.stopped == 1
