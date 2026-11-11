# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller de Jarvis.app (macOS). Lancer depuis la racine du dépôt :

    pyinstaller --noconfirm packaging/macos/Jarvis.spec
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]

datas = collect_data_files("jarvis_cyber")          # interface web (HTML, CSS, JS, logo)
binaries = []
hiddenimports = collect_submodules("jarvis_cyber") + collect_submodules("uvicorn")

# Paquets à données ou bibliothèques natives que l'analyse statique ne voit pas
for package in (
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "tokenizers",
    "av",
    "sounddevice",
    "_sounddevice_data",
    "webview",
    "mcp",
    "anthropic",
    "pydantic_settings",
    "tzdata",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception as exc:  # paquet optionnel absent
        print(f"[Jarvis.spec] {package} ignoré : {exc}")
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [str(ROOT / "packaging" / "macos" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Jarvis",
    console=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Jarvis")
app = BUNDLE(
    coll,
    name="Jarvis.app",
    bundle_identifier="com.servais.jarvis",
    info_plist={
        "CFBundleName": "Jarvis",
        "CFBundleDisplayName": "J.A.R.V.I.S.",
        "CFBundleShortVersionString": "2.0.0",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Jarvis écoute le micro pour entendre le mot d'éveil et vos demandes. L'audio est transcrit sur ce Mac et n'est pas envoyé sur Internet.",
        "NSAppleEventsUsageDescription": "Jarvis pilote vos applications (ouvrir, fermer, musique, volume) quand vous le lui demandez.",
    },
)
