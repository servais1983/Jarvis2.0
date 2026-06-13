#!/usr/bin/env python3
"""
Jarvis - Assistant vocal local pour PC
=======================================
Wake word : "jarvis"
STT       : SpeechRecognition (Google, fr-FR)
LLM       : Ollama (local) avec fallback OpenAI
TTS       : pyttsx3 (hors-ligne)
Commandes : ouvrir apps, navigateur, YouTube, recherche Google

Prérequis :
  pip install speechrecognition pyttsx3 pyaudio requests
  Installer Ollama : https://ollama.com  puis : ollama pull deepseek-r1
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import webbrowser

import requests
import speech_recognition as sr
import pyttsx3

# ---------------------------------------------------------------------------
# Configuration (modifiable ici ou via variables d'environnement)
# ---------------------------------------------------------------------------

WAKE_WORD: str = os.getenv("JARVIS_WAKE_WORD", "jarvis")
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "deepseek-r1")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
LANGUAGE: str = os.getenv("JARVIS_LANG", "fr-FR")
SPEECH_RATE: int = int(os.getenv("JARVIS_SPEECH_RATE", "170"))
CONVERSATION_TIMEOUT: int = 180  # secondes avant réinitialisation du contexte

# ---------------------------------------------------------------------------
# Moteur TTS
# ---------------------------------------------------------------------------

_engine = pyttsx3.init()
_engine.setProperty("rate", SPEECH_RATE)

# Voix française si disponible
for voice in _engine.getProperty("voices"):
    if "fr" in voice.id.lower() or "french" in voice.name.lower():
        _engine.setProperty("voice", voice.id)
        break

# ---------------------------------------------------------------------------
# État global
# ---------------------------------------------------------------------------

_stop_speaking: bool = False
_speaking_thread: threading.Thread | None = None
_conversation_history: str = ""
_last_interaction: float = time.time()

# ---------------------------------------------------------------------------
# Voix
# ---------------------------------------------------------------------------


def speak(text: str) -> None:
    """Lit le texte à voix haute dans un thread séparé (non-bloquant)."""
    global _stop_speaking, _speaking_thread

    _stop_speaking = False

    def _run() -> None:
        try:
            _engine.say(text)
            while not _stop_speaking:
                _engine.runAndWait()
                break
        except RuntimeError:
            pass

    _speaking_thread = threading.Thread(target=_run, daemon=True)
    _speaking_thread.start()


def stop_speech() -> None:
    """Interrompt immédiatement la parole de Jarvis."""
    global _stop_speaking
    _stop_speaking = True
    try:
        _engine.stop()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# LLM : Ollama (local) avec fallback OpenAI
# ---------------------------------------------------------------------------


def _call_ollama(prompt: str) -> str:
    """Envoie le prompt à Ollama et retourne la réponse nettoyée."""
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        if resp.status_code == 200:
            raw = resp.json().get("response", "")
            # Supprime les balises <think>...</think> (deepseek-r1)
            return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        return f"Ollama a retourné le code {resp.status_code}."
    except requests.ConnectionError:
        return None  # type: ignore[return-value]
    except requests.Timeout:
        return "L'IA locale met trop de temps à répondre."


def _call_openai(prompt: str) -> str:
    """Fallback OpenAI si Ollama n'est pas disponible."""
    if not OPENAI_API_KEY:
        return "Ollama n'est pas disponible et aucune clé OpenAI n'est configurée."
    try:
        from openai import OpenAI  # noqa: PLC0415

        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="claude-haiku-4-5-20251001",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        return f"Erreur OpenAI : {exc}"


def ask_llm(prompt: str) -> str:
    """Interroge Ollama en priorité, puis OpenAI en fallback."""
    result = _call_ollama(prompt)
    if result is None:
        print("⚠️  Ollama indisponible, bascule vers OpenAI...")
        return _call_openai(prompt)
    return result


# ---------------------------------------------------------------------------
# Commandes PC
# ---------------------------------------------------------------------------

_PC_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brecherche\b|\bcherche\b"), "search"),
    (re.compile(r"\byoutube\b|\bjoue\b"), "youtube"),
    (re.compile(r"\bnavigateur\b|\binternet\b|\bbrowser\b"), "browser"),
    (re.compile(r"\bfichiers\b|\bexplorateur\b"), "files"),
    (re.compile(r"\bbloc.notes\b|\bnotepad\b|\béditeur\b"), "notepad"),
    (re.compile(r"\bcalculatrice\b|\bcalcul\b"), "calc"),
    (re.compile(r"\bmétéo\b|\btemps\b|\btemperature\b"), "weather"),
    (re.compile(r"\bmusique\b|\bspotify\b"), "music"),
]


def _open_app(cmd: list[str]) -> None:
    try:
        subprocess.Popen(cmd)
    except FileNotFoundError:
        pass


def handle_pc_command(command: str) -> str | None:
    """
    Détecte une commande PC dans la phrase et l'exécute.
    Retourne une réponse textuelle ou None si ce n'est pas une commande PC.
    """
    for pattern, action in _PC_PATTERNS:
        if pattern.search(command):
            if action == "search":
                query = re.sub(r".*(?:recherche|cherche)\s+", "", command).strip()
                query = re.sub(r"\bsur\s+google\b", "", query).strip()
                if query:
                    webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
                    return f"Je recherche '{query}' sur Google."

            elif action == "youtube":
                query = re.sub(
                    r".*(?:youtube|joue|lance|met)\s*(?:sur\s+youtube)?\s*", "", command
                ).strip()
                if query:
                    webbrowser.open(
                        f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
                    )
                    return f"Je lance '{query}' sur YouTube."
                webbrowser.open("https://www.youtube.com")
                return "J'ouvre YouTube."

            elif action == "browser":
                webbrowser.open("https://www.google.com")
                return "J'ouvre le navigateur."

            elif action == "files":
                if sys.platform == "win32":
                    _open_app(["explorer"])
                elif sys.platform == "darwin":
                    _open_app(["open", os.path.expanduser("~")])
                else:
                    _open_app(["xdg-open", os.path.expanduser("~")])
                return "J'ouvre le gestionnaire de fichiers."

            elif action == "notepad":
                if sys.platform == "win32":
                    _open_app(["notepad"])
                elif sys.platform == "darwin":
                    _open_app(["open", "-a", "TextEdit"])
                else:
                    for editor in ["gedit", "mousepad", "xed", "nano"]:
                        try:
                            _open_app([editor])
                            break
                        except Exception:
                            continue
                return "J'ouvre l'éditeur de texte."

            elif action == "calc":
                if sys.platform == "win32":
                    _open_app(["calc"])
                elif sys.platform == "darwin":
                    _open_app(["open", "-a", "Calculator"])
                else:
                    for calc in ["gnome-calculator", "kcalc", "xcalc"]:
                        try:
                            _open_app([calc])
                            break
                        except Exception:
                            continue
                return "J'ouvre la calculatrice."

            elif action == "weather":
                webbrowser.open("https://www.google.com/search?q=météo+aujourd%27hui")
                return "Je vérifie la météo pour vous."

            elif action == "music":
                webbrowser.open("https://open.spotify.com")
                return "J'ouvre Spotify."

    return None


# ---------------------------------------------------------------------------
# Assistant IA principal
# ---------------------------------------------------------------------------


def ai_assistant(text: str) -> str:
    """
    Traite une commande vocale :
    1. Commandes PC directes
    2. Questions IA (Ollama / OpenAI)
    Retourne la réponse textuelle et déclenche la synthèse vocale.
    """
    global _conversation_history, _last_interaction

    # Réinitialisation du contexte si inactif
    if time.time() - _last_interaction > CONVERSATION_TIMEOUT:
        print("🧹 Contexte de conversation réinitialisé (inactivité).")
        _conversation_history = ""

    # Essai commande PC
    pc_result = handle_pc_command(text)
    if pc_result:
        _last_interaction = time.time()
        speak(pc_result)
        return pc_result

    # Question pour l'IA
    _conversation_history += f"\nUtilisateur: {text}"

    system_prompt = (
        "Tu es Jarvis, l'assistant personnel intelligent d'Iron Man.\n"
        "Tu réponds toujours en français, de façon concise et directe.\n"
        "Tu es efficace, précis et légèrement formel."
    )

    prompt = (
        f"{system_prompt}\n\n"
        f"Historique :\n{_conversation_history}\n\n"
        "Réponds à la dernière question de l'utilisateur.\n"
        "Jarvis:"
    )

    response = ask_llm(prompt)
    _conversation_history += f"\nJarvis: {response}"
    _last_interaction = time.time()

    speak(response)
    return response


# ---------------------------------------------------------------------------
# Écoute microphone
# ---------------------------------------------------------------------------


def listen() -> str:
    """Écoute le microphone et retourne le texte reconnu (minuscules)."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 En écoute...")
        recognizer.adjust_for_ambient_noise(source, duration=0.8)
        recognizer.pause_threshold = 1.5
        try:
            audio = recognizer.listen(source, phrase_time_limit=12)
        except sr.WaitTimeoutError:
            return ""

    try:
        text = recognizer.recognize_google(audio, language=LANGUAGE)
        print(f"👉 Vous avez dit : {text}")
        return text.lower()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as exc:
        print(f"❌ Erreur reconnaissance vocale : {exc}")
        return ""


# ---------------------------------------------------------------------------
# Détection commandes d'arrêt
# ---------------------------------------------------------------------------

_STOP_KEYWORDS = ["stop jarvis", "jarvis stop", "arrête", "tais-toi", "silence", "stop"]


def is_stop_command(cmd: str) -> bool:
    return any(kw in cmd for kw in _STOP_KEYWORDS)


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 50)
    print("  🤖  JARVIS - Assistant Vocal Local")
    print("=" * 50)
    print(f"  Modèle  : {OLLAMA_MODEL} via Ollama")
    print(f"  Langue  : {LANGUAGE}")
    print(f"  Wake    : '{WAKE_WORD}'")
    print("=" * 50)
    print(f"\n  Dites '{WAKE_WORD.capitalize()}' pour activer l'assistant.")
    print("  Dites 'arrête' ou 'tais-toi' pour interrompre.\n")

    speak("Jarvis en ligne. Prêt à vous assister.")

    while True:
        try:
            command = listen()
        except KeyboardInterrupt:
            print("\n👋 Arrêt de Jarvis.")
            stop_speech()
            sys.exit(0)

        if not command:
            continue

        # Priorité 1 : commande d'arrêt
        if is_stop_command(command):
            print("⏹️  Jarvis interrompu.")
            stop_speech()
            continue

        # Priorité 2 : wake word
        if WAKE_WORD in command:
            print(f"🔑 Wake word détecté.")
            response = ai_assistant(command)
            preview = response[:80] + "..." if len(response) > 80 else response
            print(f"🤖 Jarvis : {preview}")


if __name__ == "__main__":
    main()
