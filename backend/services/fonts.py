"""Schrift-Verwaltung für HefterPro.

Bundelt echte Handschrift-Fonts (SIL Open Font License) und gibt pro
Zeichen eine zufällige Kombination aus Schriftart + Variante zurück.
Dadurch wirkt das Ergebnis natürlich statt wie ein Computerausdruck.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PIL import ImageFont

from .. import config

log = logging.getLogger(__name__)

FONTS_DIR = config.BASE_DIR / "fonts"

HANDWRITING_FONTS = [
    "PatrickHand-Regular.ttf",
    "ArchitectsDaughter-Regular.ttf",
    "JustAnotherHand-Regular.ttf",
    "Kalam-Regular.ttf",
]


@dataclass
class FontProfile:
    """Eine Schriftart-Sammlung für eine Handschrift.

    Enthält mehrere Schriftarten, zwischen denen zufällig gewechselt wird,
    damit das Gesamtbild natürlicher wirkt.
    """
    id: str
    name: str
    font_files: List[str]

    def load_fonts(self, size: int) -> List[ImageFont.FreeTypeFont]:
        fonts: List[ImageFont.FreeTypeFont] = []
        for name in self.font_files:
            path = FONTS_DIR / name
            if not path.exists():
                continue
            try:
                fonts.append(ImageFont.truetype(str(path), size))
            except Exception as exc:
                log.warning("Font %s nicht ladbar: %s", name, exc)
        if not fonts:
            fonts.append(ImageFont.load_default())
        return fonts


DEFAULT_PROFILES: Dict[str, FontProfile] = {
    "hefterpro-natur": FontProfile(
        id="hefterpro-natur",
        name="HefterPro Natur (Standard)",
        font_files=["PatrickHand-Regular.ttf", "ArchitectsDaughter-Regular.ttf"],
    ),
    "hefterpro-locker": FontProfile(
        id="hefterpro-locker",
        name="HefterPro Locker",
        font_files=["JustAnotherHand-Regular.ttf", "ArchitectsDaughter-Regular.ttf"],
    ),
    "hefterpro-rund": FontProfile(
        id="hefterpro-rund",
        name="HefterPro Rund",
        font_files=["Kalam-Regular.ttf", "PatrickHand-Regular.ttf"],
    ),
    "hefterpro-klar": FontProfile(
        id="hefterpro-klar",
        name="HefterPro Klar",
        font_files=["PatrickHand-Regular.ttf"],
    ),
}


def get_profile(profile_id: str) -> Optional[FontProfile]:
    return DEFAULT_PROFILES.get(profile_id)


def list_profiles() -> List[Dict]:
    return [
        {"id": p.id, "name": p.name, "source": "default", "glyph_count": len(p.font_files)}
        for p in DEFAULT_PROFILES.values()
    ]


def pick_font(fonts: List[ImageFont.FreeTypeFont], rng: random.Random) -> ImageFont.FreeTypeFont:
    if not fonts:
        return ImageFont.load_default()
    # Gewichtet: erste Schriftart öfter.
    return rng.choices(fonts, weights=[3] + [1] * (len(fonts) - 1))[0] if len(fonts) > 1 else fonts[0]
