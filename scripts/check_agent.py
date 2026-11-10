#!/usr/bin/env python3
"""Vérifie l'agent réel : /chat → Ollama → décision d'outil → serveur MCP système → réponse.

Nécessite un Ollama en marche avec le modèle configuré (JARVIS_OLLAMA_MODEL).
Aucune simulation : le modèle doit décider lui-même d'appeler l'outil de calcul.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="jarvis-agent-check-"))
os.environ["JARVIS_DATA_DIR"] = str(_tmp)
os.environ["JARVIS_DATABASE_PATH"] = str(_tmp / "check.db")
os.environ["JARVIS_MCP_SERVERS_FILE"] = str(_tmp / "mcp_servers.json")
(_tmp / "mcp_servers.json").write_text(
    json.dumps(
        {
            "mcpServers": {
                "systeme": {
                    "command": "python",
                    "args": ["-m", "jarvis_cyber.mcp_builtin.system_server"],
                }
            }
        }
    ),
    encoding="utf-8",
)

from fastapi.testclient import TestClient

from jarvis_cyber.api.main import app
from jarvis_cyber.services.brain import brain_status

QUESTION = "Utilise ton outil de calcul pour me dire combien font (21*2)+8."


def main() -> int:
    brain = brain_status()
    print("cerveau :", brain)
    if brain["engine"] != "ollama":
        print("AGENT RÉEL: ÉCHEC (Ollama ou le modèle n'est pas disponible)")
        return 1

    client = TestClient(app)
    for attempt in range(1, 4):
        started = time.monotonic()
        response = client.post("/chat", json={"session_id": f"check-{attempt}", "message": QUESTION})
        body = response.json()
        elapsed = time.monotonic() - started
        print(f"\nessai {attempt} — {elapsed:.1f} s — modèle {body.get('model')}")
        print("  outils :", body.get("tools_used"))
        print("  réponse:", (body.get("answer") or "")[:400])
        used_calc = "systeme.calcul" in (body.get("tools_used") or [])
        if response.status_code == 200 and used_calc and "50" in (body.get("answer") or ""):
            print("AGENT RÉEL: OK")
            return 0
    print("AGENT RÉEL: ÉCHEC (le modèle n'a pas appelé l'outil ou n'a pas rendu 50)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
