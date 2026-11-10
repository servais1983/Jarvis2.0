"""Endpoints de la voix native : état, démarrage, flux d'événements, parole."""

from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from jarvis_cyber.auth import require_permissions
from jarvis_cyber.config import settings
from jarvis_cyber.services.brain import brain_status, pull_model_in_background
from jarvis_cyber.services.native_voice import (
    get_native_voice,
    missing_components,
    native_voice_available,
)

router = APIRouter(prefix="/voice/native", tags=["voix native"])
system_router = APIRouter(prefix="/system", tags=["système"])


@system_router.get("/brain")
def brain(_user=Depends(require_permissions("chat.use"))) -> dict:
    """Quel moteur de langage est disponible (Ollama, OpenAI ou aucun)."""
    return brain_status()


@system_router.post("/brain/pull")
def brain_pull(_user=Depends(require_permissions("chat.use"))) -> dict:
    status = brain_status()
    if status["ollama_running"] and not status["model_present"]:
        pull_model_in_background()
    return brain_status()


class NativeVoiceStatus(BaseModel):
    available: bool
    missing: list[str] = Field(default_factory=list)
    running: bool
    state: str
    wake_word: str
    stt_model: str
    tts_available: bool
    tts_voice: str | None = None
    last_error: str | None = None


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _status() -> NativeVoiceStatus:
    engine = get_native_voice()
    speaker = engine._speaker
    return NativeVoiceStatus(
        available=native_voice_available(),
        missing=missing_components(),
        running=engine.running,
        state=engine.state,
        wake_word=settings.wake_word,
        stt_model=settings.stt_model,
        tts_available=speaker.available,
        tts_voice=speaker.voice if speaker.available else None,
        last_error=engine.last_error,
    )


@router.get("/status", response_model=NativeVoiceStatus)
def status(_user=Depends(require_permissions("voice.use"))) -> NativeVoiceStatus:
    return _status()


@router.post("/start", response_model=NativeVoiceStatus)
def start(_user=Depends(require_permissions("voice.use"))) -> NativeVoiceStatus:
    if native_voice_available():
        get_native_voice().start()
    return _status()


@router.post("/stop", response_model=NativeVoiceStatus)
def stop(_user=Depends(require_permissions("voice.use"))) -> NativeVoiceStatus:
    get_native_voice().stop()
    return _status()


@router.post("/speak", response_model=NativeVoiceStatus)
def speak(payload: SpeakRequest, _user=Depends(require_permissions("voice.use"))) -> NativeVoiceStatus:
    get_native_voice().speak(payload.text)
    return _status()


@router.post("/silence", response_model=NativeVoiceStatus)
def silence(_user=Depends(require_permissions("voice.use"))) -> NativeVoiceStatus:
    get_native_voice().silence()
    return _status()


@router.get("/events")
async def events(request: Request, _user=Depends(require_permissions("voice.use"))) -> StreamingResponse:
    engine = get_native_voice()
    subscriber = engine.subscribe()

    async def stream():
        try:
            yield "retry: 2000\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.to_thread(subscriber.get, True, 1.0)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            engine.unsubscribe(subscriber)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
