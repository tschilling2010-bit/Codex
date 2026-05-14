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
BULLETS = ["•", "·", "→", "–"]


def all_characters() -> List[str]:
    return UPPERCASE + LOWERCASE + DIGITS + GERMAN + PUNCT + MATH + BULLETS


# Eine Variante pro Zeichen.
VARIANT_COUNTS = {c: 1 for c in all_characters()}


def template_cells() -> List[Tuple[str, int]]:
    """Liefert alle (Zeichen, Variantenindex) Paare für das Template."""
    return [(ch, 0) for ch in all_characters()]


# ---------------------------------------------------------------------------
# Vertical positioning metrics for the renderer
# ---------------------------------------------------------------------------
# (scale, top_position) per character:
#   scale:        target height as fraction of cap height
#   top_position: how far above baseline the TOP of the glyph sits
#                 (fraction of cap height)

from typing import Dict  # noqa: E402 (already imported above but re-stated for clarity)

_METRICS: Dict[str, Tuple[float, float]] = {}

for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ":
    _METRICS[_c] = (1.0, 1.0)

for _c in "acemnorsuvwxz":
    _METRICS[_c] = (0.62, 0.62)

for _c in "bdfhkl":
    _METRICS[_c] = (1.0, 1.0)
_METRICS["t"] = (0.82, 0.82)
_METRICS["i"] = (0.78, 0.78)

for _c in "gjpqy":
    _METRICS[_c] = (0.88, 0.62)

_METRICS["ä"] = (0.76, 0.76)
_METRICS["ö"] = (0.76, 0.76)
_METRICS["ü"] = (0.76, 0.76)
_METRICS["ß"] = (1.0, 1.0)

for _c in "0123456789":
    _METRICS[_c] = (0.88, 0.88)

_METRICS["."] = (0.12, 0.12)
_METRICS[","] = (0.22, 0.12)
_METRICS[":"] = (0.48, 0.48)
_METRICS[";"] = (0.52, 0.42)
_METRICS["!"] = (0.88, 0.88)
_METRICS["?"] = (0.88, 0.88)
_METRICS["-"] = (0.10, 0.38)
_METRICS["–"] = (0.10, 0.38)
_METRICS["("] = (1.0, 1.0)
_METRICS[")"] = (1.0, 1.0)
_METRICS["/"] = (1.0, 1.0)
_METRICS["+"] = (0.38, 0.52)
_METRICS["="] = (0.22, 0.42)
_METRICS["%"] = (0.85, 0.85)
_METRICS["&"] = (0.88, 0.88)
_METRICS["@"] = (0.88, 0.88)
_METRICS['"'] = (0.18, 0.92)
_METRICS["'"] = (0.18, 0.92)
_METRICS["→"] = (0.20, 0.45)


def get_metrics(ch: str) -> Tuple[float, float]:
    """Return (scale, top_position) for a character."""
    return _METRICS.get(ch, (0.62, 0.62))
