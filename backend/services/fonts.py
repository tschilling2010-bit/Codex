"""Schrift-Verwaltung für HefterPro.

Unterstützt zwei Profiltypen:
- Eingebaute TTF-Profile (Standard-Handschriften)
- Eigene Glyph-Profile (vom Nutzer per Template erstellt)
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageFont

from .. import config

log = logging.getLogger(__name__)

FONTS_DIR = config.BASE_DIR / "fonts"


@dataclass
class FontProfile:
    id: str
    name: str
    font_files: List[str]
    source: str = "default"

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


@dataclass
class GlyphProfile:
    """User-created profile with extracted glyph images."""
    id: str
    name: str
    glyph_count: int = 0
    source: str = "user"
    _cache: Dict[str, List[Image.Image]] = field(default_factory=dict, repr=False)

    @property
    def glyph_dir(self) -> Path:
        return config.PROFILES_DIR / self.id / "glyphs"

    def variants(self, char: str) -> List[Image.Image]:
        if char in self._cache:
            return self._cache[char]
        hex_code = f"{ord(char):06x}"
        folder = self.glyph_dir / hex_code
        glyphs: List[Image.Image] = []
        if folder.exists():
            for p in sorted(folder.glob("*.png")):
                try:
                    glyphs.append(Image.open(p).convert("RGBA"))
                except Exception:
                    continue
        self._cache[char] = glyphs
        return glyphs

    def pick(self, char: str, rng: random.Random) -> Optional[Image.Image]:
        variants = self.variants(char)
        if not variants:
            return None
        return rng.choice(variants)


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


def get_glyph_profile(profile_id: str) -> Optional[GlyphProfile]:
    meta_path = config.PROFILES_DIR / profile_id / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text())
        return GlyphProfile(
            id=meta["id"],
            name=meta.get("name", profile_id),
            glyph_count=meta.get("glyph_count", 0),
        )
    except Exception:
        return None


def is_glyph_profile(profile_id: str) -> bool:
    return (config.PROFILES_DIR / profile_id / "meta.json").exists()


def list_profiles() -> List[Dict]:
    profiles: List[Dict] = []
    for p in DEFAULT_PROFILES.values():
        profiles.append({
            "id": p.id, "name": p.name,
            "source": "default", "glyph_count": len(p.font_files),
        })
    # User-created glyph profiles
    if config.PROFILES_DIR.exists():
        for folder in sorted(config.PROFILES_DIR.iterdir()):
            meta_path = folder / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text())
                profiles.append({
                    "id": meta.get("id", folder.name),
                    "name": meta.get("name", folder.name),
                    "source": "user",
                    "glyph_count": meta.get("glyph_count", 0),
                })
            except Exception:
                continue
    return profiles


def delete_user_profile(profile_id: str) -> bool:
    if profile_id in DEFAULT_PROFILES:
        return False
    folder = config.PROFILES_DIR / profile_id
    if not folder.exists():
        return False
    import shutil
    shutil.rmtree(folder)
    return True
