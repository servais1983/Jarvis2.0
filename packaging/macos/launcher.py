"""Lanceur empaqueté par PyInstaller pour Jarvis.app."""

import multiprocessing
import sys

from jarvis_cyber.desktop.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
