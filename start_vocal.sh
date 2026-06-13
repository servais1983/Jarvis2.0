#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "============================================"
echo "  Jarvis - Assistant Vocal Local"
echo "============================================"
echo

VENV_DIR=".venv"
PYTHON="$VENV_DIR/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "Création de l'environnement virtuel .venv..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installation des dépendances vocales..."
"$PYTHON" -m pip install --disable-pip-version-check -e ".[voice]" -q

# pyaudio nécessite portaudio sur Linux/macOS
if ! python3 -c "import pyaudio" 2>/dev/null; then
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "Installation de portaudio (sudo requis)..."
        sudo apt-get install -y portaudio19-dev python3-pyaudio 2>/dev/null || \
        sudo dnf install -y portaudio-devel 2>/dev/null || true
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Installation de portaudio via brew..."
        brew install portaudio 2>/dev/null || true
    fi
    "$PYTHON" -m pip install pyaudio -q
fi

echo "Vérification d'Ollama..."
if ! curl -s http://localhost:11434 >/dev/null 2>&1; then
    echo ""
    echo "ATTENTION: Ollama n'est pas lancé."
    echo "Téléchargez Ollama sur https://ollama.com"
    echo "Puis lancez : ollama pull deepseek-r1"
    echo ""
    echo "Jarvis démarrera quand même (fallback OpenAI si configuré)."
    echo ""
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
fi

set -a
[ -f ".env" ] && source ".env"
set +a

echo ""
echo "Démarrage de Jarvis Vocal..."
echo "Dites 'Jarvis' pour activer l'assistant."
echo "Appuyez sur Ctrl+C pour quitter."
echo ""

"$PYTHON" jarvis_vocal.py
