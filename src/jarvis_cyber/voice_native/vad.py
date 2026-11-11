"""Découpage du flux micro en phrases, par énergie avec seuil adaptatif."""

from __future__ import annotations

from collections import deque

import numpy as np


class UtteranceSegmenter:
    """Reçoit des trames audio (float32, mono) et rend une phrase complète quand elle se termine."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        start_ms: int = 90,
        end_silence_ms: int = 750,
        min_speech_ms: int = 350,
        max_utterance_s: float = 15.0,
        pre_roll_ms: int = 300,
        threshold_ratio: float = 3.0,
        min_threshold: float = 0.008,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self._start_frames = max(1, start_ms // frame_ms)
        self._end_frames = max(1, end_silence_ms // frame_ms)
        self._min_speech_frames = max(1, min_speech_ms // frame_ms)
        self._max_frames = int(max_utterance_s * 1000 / frame_ms)
        self._pre_roll: deque[np.ndarray] = deque(maxlen=max(1, pre_roll_ms // frame_ms))
        self._ratio = threshold_ratio
        self._min_threshold = min_threshold
        self._noise = min_threshold / threshold_ratio
        self.level = 0.0
        self.reset()

    def reset(self) -> None:
        self._frames: list[np.ndarray] = []
        self._in_speech = False
        self._above = 0
        self._silence = 0
        self._speech_frames = 0
        self._pre_roll.clear()

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        rms = float(np.sqrt(np.mean(frame * frame))) if frame.size else 0.0
        self.level = rms
        threshold = max(self._min_threshold, self._noise * self._ratio)
        loud = rms > threshold

        if not self._in_speech:
            if loud:
                self._above += 1
            else:
                self._above = 0
                # Le bruit de fond n'est appris que sur le silence
                self._noise = 0.95 * self._noise + 0.05 * rms
            self._pre_roll.append(frame)
            if self._above >= self._start_frames:
                self._in_speech = True
                self._frames = list(self._pre_roll)
                self._speech_frames = self._above
                self._silence = 0
            return None

        self._frames.append(frame)
        if loud:
            self._speech_frames += 1
            self._silence = 0
        else:
            self._silence += 1

        ended = self._silence >= self._end_frames
        too_long = len(self._frames) >= self._max_frames
        if not (ended or too_long):
            return None

        audio = np.concatenate(self._frames)
        enough = self._speech_frames >= self._min_speech_frames
        self.reset()
        return audio if enough else None
