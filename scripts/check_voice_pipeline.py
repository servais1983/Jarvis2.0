#!/usr/bin/env python3
"""Vérifie la chaîne vocale réelle sur un fichier audio.

    python scripts/check_voice_pipeline.py commande.wav heure

Le fichier (WAV 16 kHz mono 16 bits) traverse le vrai moteur : découpage en
phrases, transcription Whisper, détection du mot d'éveil. Le script réussit
si une commande contenant le mot attendu est émise.
"""

from __future__ import annotations

import sys

from jarvis_cyber.config import settings
from jarvis_cyber.voice_native.audio import WavFileSource
from jarvis_cyber.voice_native.engine import NativeVoiceEngine
from jarvis_cyber.voice_native.stt import WhisperTranscriber
from jarvis_cyber.voice_native.wake import normalize


class SilentSpeaker:
    speaking = False

    def speak(self, _text, on_done=None) -> bool:
        if on_done:
            on_done()
        return True

    def stop(self) -> None:
        pass


def main() -> int:
    path, expected = sys.argv[1], sys.argv[2]
    transcriber = WhisperTranscriber(
            settings.stt_model, settings.stt_language, settings.wake_word, settings.stt_prompt
        )
    engine = NativeVoiceEngine(
        transcriber, SilentSpeaker(), lambda: WavFileSource(path), wake_word=settings.wake_word
    )
    subscriber = engine.subscribe()
    engine.run_blocking()

    events = []
    while not subscriber.empty():
        event = subscriber.get()
        if event["type"] not in ("level", "state"):
            events.append(event)
    print(f"modèle={settings.stt_model} langue={settings.stt_language} entendu={engine.last_heard!r}")
    for event in events:
        print("  ", event)

    commands = [e["text"] for e in events if e["type"] == "command"]
    ok = any(normalize(expected) in normalize(c) for c in commands)
    print("CHAÎNE VOCALE:", "OK" if ok else f"ÉCHEC (attendu « {expected} » dans une commande)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
