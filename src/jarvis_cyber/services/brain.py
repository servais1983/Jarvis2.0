"""État du « cerveau » de Jarvis : quel moteur de langage répondra aux questions libres."""

from __future__ import annotations

import logging
import threading

import httpx

from jarvis_cyber.config import settings

logger = logging.getLogger(__name__)

_pull_lock = threading.Lock()
_pull_state: dict[str, str | None] = {"status": "idle", "error": None}


def _base() -> str:
    return settings.ollama_base_url.rstrip("/")


def model_matches(installed: str, wanted: str) -> bool:
    """« llama3.1 » correspond à « llama3.1:latest » ; « llama3.2:3b » doit correspondre exactement."""
    if ":" in wanted:
        return installed == wanted
    return installed == wanted or installed.split(":", 1)[0] == wanted


def brain_status() -> dict:
    status = {
        "engine": "aucun",
        "ollama_running": False,
        "model": settings.ollama_model,
        "model_present": False,
        "pull": _pull_state["status"],
        "pull_error": _pull_state["error"],
        "openai_configured": settings.openai_api_key is not None,
    }
    try:
        response = httpx.get(f"{_base()}/api/tags", timeout=1.5)
        response.raise_for_status()
        status["ollama_running"] = True
        names = [m.get("name", "") for m in response.json().get("models", [])]
        status["model_present"] = any(model_matches(n, settings.ollama_model) for n in names)
    except (httpx.HTTPError, ValueError):
        pass
    from jarvis_cyber.services.claude_agent import claude_agent_service

    status["claude_configured"] = claude_agent_service.enabled
    status["claude_model"] = settings.claude_model
    status["claude_error"] = claude_agent_service.last_error
    if status["claude_configured"]:
        status["engine"] = "claude"
    elif status["ollama_running"] and status["model_present"]:
        status["engine"] = "ollama"
    elif status["openai_configured"]:
        status["engine"] = "openai"
    return status


def pull_model_in_background() -> bool:
    """Télécharge le modèle configuré si Ollama tourne et qu'il manque. Rend True si lancé."""
    with _pull_lock:
        if _pull_state["status"] == "running":
            return False
        _pull_state.update(status="running", error=None)

    def run() -> None:
        try:
            response = httpx.post(
                f"{_base()}/api/pull",
                json={"model": settings.ollama_model, "stream": False},
                timeout=None,
            )
            response.raise_for_status()
            _pull_state.update(status="done", error=None)
            logger.info("Modèle %s téléchargé.", settings.ollama_model)
        except httpx.HTTPError as exc:
            _pull_state.update(status="failed", error=str(exc))
            logger.warning("Téléchargement du modèle %s impossible : %s", settings.ollama_model, exc)

    threading.Thread(target=run, name="jarvis-model-pull", daemon=True).start()
    return True
