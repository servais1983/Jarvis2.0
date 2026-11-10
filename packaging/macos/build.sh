#!/usr/bin/env bash
# Construit dist/Jarvis.app et dist/Jarvis-macOS-<arch>.zip. À lancer sur un Mac, depuis la racine du dépôt.
set -euo pipefail
cd "$(dirname "$0")/../.."

PYTHON="${PYTHON:-python3}"
"$PYTHON" -m pip install --disable-pip-version-check -q ".[mcp,native,desktop]" "pyinstaller>=6.6"
rm -rf build dist
"$PYTHON" -m PyInstaller --noconfirm packaging/macos/Jarvis.spec

ARCH="$(uname -m)"
ditto -c -k --sequesterRsrc --keepParent dist/Jarvis.app "dist/Jarvis-macOS-${ARCH}.zip"
echo "Application : dist/Jarvis.app"
echo "Archive     : dist/Jarvis-macOS-${ARCH}.zip"
