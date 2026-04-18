"""Zeichensatz für das Handschrift-Template.

Jedes Zeichen wird genau einmal abgefragt (eine Variante pro Zeichen),
damit Nutzer das Template in angemessener Zeit komplett ausfüllen können.
"""
from __future__ import annotations

from typing import List, Tuple

UPPERCASE = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
LOWERCASE = list("abcdefghijklmnopqrstuvwxyz")
DIGITS = list("0123456789")
GERMAN = list("äöüÄÖÜß")

PUNCT = [".", ",", ":", ";", "?", "!", "-",
         "(", ")", "\"", "'"]
MATH = ["+", "=", "/", "%", "&", "@"]


def all_characters() -> List[str]:
    return UPPERCASE + LOWERCASE + DIGITS + GERMAN + PUNCT + MATH


# Eine Variante pro Zeichen.
VARIANT_COUNTS = {c: 1 for c in all_characters()}


def template_cells() -> List[Tuple[str, int]]:
    """Liefert alle (Zeichen, Variantenindex) Paare für das Template."""
    return [(ch, 0) for ch in all_characters()]
