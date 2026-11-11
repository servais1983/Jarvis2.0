#!/usr/bin/env bash
# J.A.R.V.I.S. sur Mac depuis les sources : double-cliquez ce fichier dans le Finder.
# Fenêtre native, micro permanent (« Jarvis, … »), transcription locale, voix du Mac.
set -e
cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "Création de l'environnement virtuel…"
    python3 -m venv .venv
fi
echo "Installation / vérification des dépendances (la première fois prend quelques minutes)…"
"$PYTHON" -m pip install --disable-pip-version-check -q -e ".[mcp,native,desktop,claude]"
echo "Démarrage de J.A.R.V.I.S. — au premier lancement, autorisez le micro."
exec "$PYTHON" -m jarvis_cyber.desktop "$@"
