#!/usr/bin/env bash
# J.A.R.V.I.S. — démarrage complet en une commande (Linux / macOS)
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  J.A.R.V.I.S. - Démarrage complet"
echo "============================================"
echo

VENV_DIR=".venv"
PYTHON="$VENV_DIR/bin/python"

# ── 1. Environnement virtuel ────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo "[1/5] Création de l'environnement virtuel .venv…"
    python3 -m venv "$VENV_DIR"
else
    echo "[1/5] Environnement virtuel détecté."
fi

# ── 2. Dépendances (serveur + outils MCP) ───────────────────
echo "[2/5] Installation / vérification des dépendances…"
"$PYTHON" -m pip install --disable-pip-version-check -q -e ".[dev,mcp]"
"$PYTHON" -c "import fastapi, uvicorn, jarvis_cyber; print('      Dépendances OK.')"

# ── 3. Fichiers de configuration ────────────────────────────
echo "[3/5] Configuration…"
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
    echo "      .env créé depuis .env.example"
fi
if [ ! -f "mcp_servers.json" ] && [ -f "mcp_servers.json.example" ]; then
    cp "mcp_servers.json.example" "mcp_servers.json"
    echo "      mcp_servers.json créé : serveur MCP de démonstration actif."
    echo "      Ajoutez-y vos propres serveurs MCP."
fi

# ── 4. Ollama (cerveau local) ───────────────────────────────
echo "[4/5] Vérification d'Ollama…"
if curl -s --max-time 2 http://localhost:11434/api/version >/dev/null 2>&1; then
    echo "      Ollama est déjà en ligne : agent local actif."
elif command -v ollama >/dev/null 2>&1; then
    echo "      Démarrage d'Ollama en arrière-plan…"
    nohup ollama serve >/dev/null 2>&1 &
    sleep 3
    if curl -s --max-time 2 http://localhost:11434/api/version >/dev/null 2>&1; then
        echo "      Ollama démarré : agent local actif."
    else
        echo "      Ollama n'a pas répondu à temps : il finira de démarrer seul."
    fi
else
    echo "      Ollama n'est pas installé : https://ollama.com"
    echo "      Jarvis fonctionnera avec OpenAI si configuré, sinon en mode local."
fi

# ── 5. Lancement ────────────────────────────────────────────
echo "[5/5] Démarrage de J.A.R.V.I.S. …"
echo
echo "   Interface : http://127.0.0.1:8000"
echo "   Cliquez sur l'orb et parlez. Arrêt : Ctrl+C"
echo

# Ouvre le navigateur une fois le serveur prêt
(
    sleep 3
    if command -v xdg-open >/dev/null 2>&1; then xdg-open http://127.0.0.1:8000 >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then open http://127.0.0.1:8000 || true
    fi
) &

exec "$PYTHON" -m uvicorn jarvis_cyber.api.main:app --host 127.0.0.1 --port 8000
