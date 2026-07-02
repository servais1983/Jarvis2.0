"""Isolation des tests.

Positionne les chemins de données AVANT tout import de jarvis_cyber pour que
la suite de tests écrive dans un répertoire temporaire et ne pollue jamais la
vraie base locale (./data/jarvis.db) : pas de faux dossiers, de profils ou de
playbooks de test dans l'application réelle.
"""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="jarvis-tests-"))
os.environ["JARVIS_DATA_DIR"] = str(_tmp)
os.environ["JARVIS_DATABASE_PATH"] = str(_tmp / "jarvis-tests.db")

# Un Ollama réel qui tourne sur la machine ne doit pas changer le résultat des
# tests : on pointe l'agent local vers un port toujours fermé.
os.environ["JARVIS_OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
