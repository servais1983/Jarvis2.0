"""Point d'entrée de l'application de bureau J.A.R.V.I.S.

    python -m jarvis_cyber.desktop              fenêtre + voix native
    python -m jarvis_cyber.desktop --headless   serveur seul (sans fenêtre)
    python -m jarvis_cyber.desktop --smoke-test vérifie que tout démarre, puis quitte

Ce module ne doit importer la configuration de Jarvis qu'APRÈS avoir fixé les
chemins de données : dans une application empaquetée, le dossier de l'app est
en lecture seule et tout s'écrit dans le dossier utilisateur.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import runpy
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

APP_NAME = "Jarvis"
DEFAULT_PORT = 8765
_OLLAMA_CANDIDATES = (
    "/opt/homebrew/bin/ollama",
    "/usr/local/bin/ollama",
    "/Applications/Ollama.app/Contents/Resources/ollama",
)
_DEFAULT_MCP = {
    "mcpServers": {
        "systeme": {
            "command": "python",
            "args": ["-m", "jarvis_cyber.mcp_builtin.system_server"],
            "enabled": True,
        }
    }
}


def user_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if system == "Windows":
        return Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME.lower()


def configure_environment(base: Path | None = None, native_voice: bool = True) -> Path:
    """Fixe les chemins de données et la configuration par défaut de l'application."""
    base = base or user_data_dir()
    base.mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(exist_ok=True)
    os.environ.setdefault("JARVIS_DATA_DIR", str(base))
    os.environ.setdefault("JARVIS_DATABASE_PATH", str(base / "jarvis.db"))
    os.environ.setdefault("JARVIS_MCP_SERVERS_FILE", str(base / "mcp_servers.json"))
    os.environ.setdefault("JARVIS_NATIVE_VOICE_ENABLED", "true" if native_voice else "false")

    mcp_file = Path(os.environ["JARVIS_MCP_SERVERS_FILE"])
    if not mcp_file.exists():
        mcp_file.write_text(json.dumps(_DEFAULT_MCP, indent=2), encoding="utf-8")

    # Une app lancée depuis le Finder n'hérite pas du PATH du terminal
    if platform.system() == "Darwin":
        extra = ["/opt/homebrew/bin", "/usr/local/bin"]
        current = os.environ.get("PATH", "").split(os.pathsep)
        os.environ["PATH"] = os.pathsep.join([*extra, *[p for p in current if p not in extra]])

    # Un fichier .env placé dans le dossier de données est pris en compte
    os.chdir(base)
    return base


def find_free_port(preferred: int = DEFAULT_PORT) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Aucun port local disponible.")


def find_ollama() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    return next((path for path in _OLLAMA_CANDIDATES if Path(path).exists()), None)


def ensure_brain(logger: logging.Logger) -> dict:
    """Démarre Ollama s'il est installé mais éteint, et télécharge le modèle s'il manque."""
    from jarvis_cyber.services.brain import brain_status, pull_model_in_background

    status = brain_status()
    if not status["ollama_running"]:
        binary = find_ollama()
        if binary is None:
            logger.info("Ollama n'est pas installé : pas de moteur de langage local.")
            return status
        logger.info("Démarrage d'Ollama (%s)…", binary)
        try:
            subprocess.Popen(
                [binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            logger.warning("Impossible de démarrer Ollama : %s", exc)
            return status
        for _ in range(20):
            time.sleep(0.5)
            status = brain_status()
            if status["ollama_running"]:
                break
    if status["ollama_running"] and not status["model_present"]:
        logger.info("Modèle %s absent : téléchargement en arrière-plan.", status["model"])
        pull_model_in_background()
        status = brain_status()
    elif status["engine"] == "ollama":
        warm_up_model(logger)
    return status


def warm_up_model(logger: logging.Logger) -> None:
    """Charge le modèle en mémoire dès le lancement, pour que la première réponse soit rapide."""
    import httpx

    from jarvis_cyber.config import settings

    try:
        httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={"model": settings.ollama_model, "keep_alive": "30m"},
            timeout=180,
        )
        logger.info("Modèle %s chargé en mémoire.", settings.ollama_model)
    except httpx.HTTPError as exc:
        logger.info("Préchargement du modèle impossible : %s", exc)


class ServerThread:
    def __init__(self, port: int) -> None:
        import uvicorn

        from jarvis_cyber.api.main import app

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="jarvis-server", daemon=True)

    def start(self, timeout: float = 30.0) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Le serveur Jarvis n'a pas démarré.")
            time.sleep(0.1)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def smoke_test(port: int, require_voice: bool = False) -> int:
    """Vérifie que l'application installée démarre réellement tous ses composants."""
    import httpx

    base = f"http://127.0.0.1:{port}"
    report: dict = {}
    with httpx.Client(base_url=base, timeout=60) as client:
        report["health"] = client.get("/health").json()["status"]
        report["interface"] = "J.A.R.V.I.S." in client.get("/").text
        report["styles"] = client.get("/static/styles.css").status_code
        mcp = client.get("/mcp/status").json()
        report["mcp"] = [(s["name"], s["connected"], s["tools_count"], s["error"]) for s in mcp["servers"]]
        call = client.post(
            "/mcp/call",
            json={"server": "systeme", "tool": "calcul", "arguments": {"expression": "(21*2)+8"}},
        )
        report["outil_calcul"] = call.json().get("content") if call.status_code == 200 else call.text
        voice = client.get("/voice/native/status").json()
        report["voix"] = {k: voice[k] for k in ("available", "missing", "tts_available", "tts_voice")}
        report["cerveau"] = client.get("/system/brain").json()
    try:
        import webview  # noqa: F401  (la fenêtre native doit être embarquée)

        report["fenetre"] = True
    except ImportError as exc:
        report["fenetre"] = f"indisponible : {exc}"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = (
        report["health"] == "ok"
        and report["interface"]
        and report["styles"] == 200
        and report["mcp"]
        and report["mcp"][0][1] is True
        and report["outil_calcul"] == "(21*2)+8 = 50"
        and (report["voix"]["available"] or not require_voice)
        and (report["fenetre"] is True or not require_voice)
    )
    print("SMOKE TEST:", "OK" if ok else "ÉCHEC")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME, add_help=True)
    parser.add_argument("--headless", action="store_true", help="serveur seul, sans fenêtre")
    parser.add_argument("--smoke-test", action="store_true", help="vérifie le démarrage puis quitte")
    parser.add_argument("--require-voice", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--transcribe", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--run-module", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--run-script", default=None, help=argparse.SUPPRESS)
    args, rest = parser.parse_known_args(argv)

    # L'app empaquetée se relance elle-même pour héberger un serveur MCP Python
    if args.run_module:
        sys.argv = [args.run_module, *rest]
        runpy.run_module(args.run_module, run_name="__main__", alter_sys=True)
        return 0
    if args.run_script:
        sys.argv = [args.run_script, *rest]
        runpy.run_path(args.run_script, run_name="__main__")
        return 0

    base = configure_environment(
        args.data_dir, native_voice=not (args.smoke_test or args.transcribe)
    )

    # Vérification de la transcription depuis l'application installée
    if args.transcribe:
        from jarvis_cyber.config import settings
        from jarvis_cyber.voice_native.audio import WavFileSource
        from jarvis_cyber.voice_native.stt import WhisperTranscriber
        from jarvis_cyber.voice_native.vad import UtteranceSegmenter

        transcriber = WhisperTranscriber(
            settings.stt_model, settings.stt_language, settings.wake_word, settings.stt_prompt
        )
        segmenter = UtteranceSegmenter()
        heard = []
        for frame in WavFileSource(args.transcribe).frames():
            utterance = segmenter.feed(frame)
            if utterance is not None:
                heard.append(transcriber.transcribe(utterance))
        print("TRANSCRIPTION:", " | ".join(heard))
        return 0 if any(heard) else 1
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(base / "logs" / "jarvis.log", encoding="utf-8"),
            # Une app lancée depuis le Finder peut ne pas avoir de sortie d'erreur
            *([logging.StreamHandler()] if sys.stderr is not None else []),
        ],
    )
    logger = logging.getLogger("jarvis.desktop")
    logger.info("Dossier de données : %s", base)

    port = find_free_port(args.port)
    server = ServerThread(port)
    server.start()
    url = f"http://127.0.0.1:{port}"
    logger.info("Jarvis en ligne sur %s", url)

    if args.smoke_test:
        try:
            return smoke_test(port, require_voice=args.require_voice)
        finally:
            server.stop()

    threading.Thread(target=ensure_brain, args=(logger,), name="jarvis-brain", daemon=True).start()

    try:
        if args.headless:
            while server.thread.is_alive():
                time.sleep(0.5)
        else:
            import webview

            webview.create_window(
                "J.A.R.V.I.S.",
                url,
                width=1440,
                height=900,
                min_size=(1024, 700),
                background_color="#010204",
            )
            webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0
