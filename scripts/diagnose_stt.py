#!/usr/bin/env python3
"""Compare ce que Whisper entend dans des fichiers audio selon l'amorce utilisée.

    python scripts/diagnose_stt.py enregistrement.wav [autre.wav …]

Utile pour régler JARVIS_STT_MODEL ou JARVIS_STT_PROMPT sur votre voix et votre micro.
"""

from __future__ import annotations

import sys

from jarvis_cyber.config import settings
from jarvis_cyber.voice_native.audio import WavFileSource
from jarvis_cyber.voice_native.stt import WhisperTranscriber
from jarvis_cyber.voice_native.vad import UtteranceSegmenter
from jarvis_cyber.voice_native.wake import extract_command


def utterances(path: str):
    segmenter = UtteranceSegmenter()
    for frame in WavFileSource(path).frames():
        utterance = segmenter.feed(frame)
        if utterance is not None:
            yield utterance


def main() -> int:
    transcriber = WhisperTranscriber(
        settings.stt_model, settings.stt_language, settings.wake_word, settings.stt_prompt
    )
    prompts = {"sans amorce": "", "amorce ouverte": "Jarvis,", "amorce par défaut": transcriber.prompt}
    print(f"modèle={settings.stt_model} langue={settings.stt_language}")
    for path in sys.argv[1:]:
        print(f"\n{path}")
        for index, audio in enumerate(utterances(path), start=1):
            print(f"  phrase {index} ({len(audio) / 16000:.1f} s)")
            for label, prompt in prompts.items():
                text = transcriber.transcribe(audio, prompt=prompt)
                result = extract_command(text, settings.wake_word)
                print(f"    {label:<18} → {text!r}  éveil={result.heard} commande={result.command!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
