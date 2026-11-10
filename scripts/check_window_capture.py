#!/usr/bin/env python3
"""Vérifie qu'une capture d'écran montre bien l'interface de Jarvis.

    python scripts/check_window_capture.py capture.png

Compte les pixels du fond sombre et ceux de l'anneau doré de l'orb : une
fenêtre vide, blanche ou absente ne passe pas.
"""

from __future__ import annotations

import sys

import numpy as np
from PIL import Image


def main() -> int:
    image = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(np.int16)
    r, g, b = image[..., 0], image[..., 1], image[..., 2]
    total = r.size
    dark = (r < 25) & (g < 30) & (b < 45)
    gold = (r > 200) & (g > 130) & (g < 215) & (b < 120) & (r - b > 110)
    blue = (b > 170) & (r < 140) & (g > 110) & (b - r > 70)

    gold_count = int(gold.sum())
    stats = {
        "taille": f"{image.shape[1]}x{image.shape[0]}",
        "fond_sombre": round(float(dark.sum()) / total, 3),
        "pixels_dores": gold_count,
        "pixels_bleus": int(blue.sum()),
    }
    if gold_count:
        ys, xs = np.nonzero(gold)
        stats["anneau_centre"] = (int(xs.mean()), int(ys.mean()))
        stats["anneau_etendue"] = (int(xs.max() - xs.min()), int(ys.max() - ys.min()))
    print(stats)

    ok = stats["fond_sombre"] > 0.25 and gold_count > 800
    print("FENÊTRE:", "OK (interface affichée)" if ok else "ÉCHEC (interface non reconnue)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
