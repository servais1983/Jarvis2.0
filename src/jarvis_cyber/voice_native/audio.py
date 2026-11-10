"""Sources audio : micro réel (sounddevice) ou fichier WAV (tests et vérifications)."""

from __future__ import annotations

import importlib.util
import queue
import wave
from collections.abc import Iterator
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 480  # 30 ms


def microphone_available() -> bool:
    return importlib.util.find_spec("sounddevice") is not None


class MicrophoneSource:
    """Flux continu du micro par trames de 30 ms."""

    def __init__(self, device: str | int | None = None) -> None:
        self._device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)
        self._stream = None
        self._closed = False

    def _callback(self, indata, _frames, _time, _status) -> None:
        try:
            self._queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # on préfère perdre une trame que bloquer le pilote audio

    def frames(self) -> Iterator[np.ndarray]:
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=FRAME_SAMPLES,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        try:
            while not self._closed:
                try:
                    yield self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
        finally:
            self._stream.stop()
            self._stream.close()

    def close(self) -> None:
        self._closed = True


class WavFileSource:
    """Rejoue un fichier WAV 16 kHz mono 16 bits comme s'il venait du micro."""

    def __init__(self, path: str | Path, trailing_silence_s: float = 1.5) -> None:
        self._path = Path(path)
        self._trailing = trailing_silence_s
        self._closed = False

    def frames(self) -> Iterator[np.ndarray]:
        with wave.open(str(self._path), "rb") as wav:
            if wav.getframerate() != SAMPLE_RATE or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise ValueError("WAV attendu : 16 kHz, mono, 16 bits.")
            raw = wav.readframes(wav.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        silence = np.zeros(int(self._trailing * SAMPLE_RATE), dtype=np.float32)
        audio = np.concatenate([silence[: SAMPLE_RATE // 2], audio, silence])
        for start in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            if self._closed:
                return
            yield audio[start : start + FRAME_SAMPLES]

    def close(self) -> None:
        self._closed = True
