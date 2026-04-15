"""Zeichensatz für das Handschrift-Template.

Definiert alle Zeichen, die das Template abdeckt, sowie eine Variantenzahl
pro Zeichen.  Häufige Zeichen bekommen mehrere Felder, damit später zwischen
natürlichen Varianten gewechselt werden kann.
"""
from __future__ import annotations

from typing import List, Tuple

UPPERCASE = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
LOWERCASE = list("abcdefghijklmnopqrstuvwxyz")
DIGITS = list("0123456789")

GERMAN = list("äöüÄÖÜß")
FRENCH = list("àâæçéèêëîïôœùûÿÀÂÆÇÉÈÊËÎÏÔŒÙÛŸ")

PUNCT = [".", ",", ":", ";", "?", "!", "-", "–", "—",
         "(", ")", "[", "]", "{", "}", "\"", "'", "„", "“", "«", "»"]
MATH = ["+", "=", "/", "%", "*", "&", "<", ">", "#", "@"]
BULLETS = ["•", "·", "○"]
ARROWS = ["→", "←", "↑", "↓"]

# Varianten: wichtigere Zeichen mehrfach.
VARIANT_COUNTS = {
    **{c: 3 for c in UPPERCASE},
    **{c: 4 for c in LOWERCASE},
    **{c: 3 for c in DIGITS},
    **{c: 2 for c in GERMAN},
    **{c: 2 for c in FRENCH},
    **{c: 2 for c in PUNCT},
    **{c: 2 for c in MATH},
    **{c: 2 for c in BULLETS},
    **{c: 1 for c in ARROWS},
}


def all_characters() -> List[str]:
    return UPPERCASE + LOWERCASE + DIGITS + GERMAN + FRENCH + PUNCT + MATH + BULLETS + ARROWS


def template_cells() -> List[Tuple[str, int]]:
    """Liefert alle (Zeichen, Variantenindex) Paare für das Template."""
    cells: List[Tuple[str, int]] = []
    for ch in all_characters():
        for v in range(VARIANT_COUNTS.get(ch, 1)):
            cells.append((ch, v))
    return cells
