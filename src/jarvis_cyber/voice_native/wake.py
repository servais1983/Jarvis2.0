"""Détection du mot d'éveil dans une transcription.

La reconnaissance vocale écrit rarement « Jarvis » de façon stable : on
accepte les variantes phonétiques courantes (Jarvi, Jervis, Javis, Djarvis,
Charvis, Jarvisse…) sans accepter des mots voisins comme « service ».
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_JARVIS = re.compile(r"^(?:d?j|g|ch)[ae]r?v[iy](?:s{1,2}e?|ce|x|z)?$")
_LEADING = {"ok", "okay", "hey", "he", "eh", "dis", "dit", "bonjour", "salut", "merci", "et"}
_PUNCT = re.compile(r"^[\s,.;:!?…\-–—'\"«»]+|[\s,.;:!?…\-–—'\"«»]+$")


@dataclass(frozen=True)
class WakeResult:
    heard: bool
    command: str


def normalize(word: str) -> str:
    decomposed = unicodedata.normalize("NFD", word.lower())
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", stripped)


def _is_wake(word: str, wake_word: str) -> bool:
    token = normalize(word)
    if not token:
        return False
    if normalize(wake_word) == "jarvis":
        return bool(_JARVIS.match(token))
    return token == normalize(wake_word)


def extract_command(text: str, wake_word: str = "jarvis") -> WakeResult:
    """Cherche le mot d'éveil et renvoie la commande qui l'accompagne.

    « Jarvis, ouvre Safari » → commande « ouvre Safari »
    « ouvre Safari, Jarvis » → commande « ouvre Safari »
    « Jarvis »               → entendu, commande vide
    """
    words = text.split()
    for index, word in enumerate(words):
        if not _is_wake(word, wake_word):
            continue
        after = _PUNCT.sub("", " ".join(words[index + 1 :]))
        before_words = [w for w in words[:index] if normalize(w) not in _LEADING]
        before = _PUNCT.sub("", " ".join(before_words))
        return WakeResult(heard=True, command=after or before)
    return WakeResult(heard=False, command=_PUNCT.sub("", text))
