"""Speicherung und Bereitstellung von Glyphen für die Handschrift-Engine.

Jedes Handschrift-Profil ist ein Ordner unter ``storage/profiles/<id>/`` mit
folgender Struktur::

    meta.json            # Metadaten des Profils
    glyphs/<hex>/<v>.png # Glyph-Bild (transparent PNG) pro Variante

Der Dateiname wird aus dem Codepoint des Zeichens abgeleitet, damit auch
Sonderzeichen und Unicode-Punkte problemlos gespeichert werden können.
"""
from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from .. import config

log = logging.getLogger(__name__)


def _hex(char: str) -> str:
    return f"{ord(char):06x}"


class GlyphEngine:
    """Lädt/speichert Glyph-Bilder eines Handschrift-Profils."""

    def __init__(self, profile_id: str, profile_name: Optional[str] = None) -> None:
        self.profile_id = profile_id
        self.root = config.PROFILES_DIR / profile_id
        self.glyph_dir = self.root / "glyphs"
        self.meta_path = self.root / "meta.json"
        self._cache: Dict[str, List[Image.Image]] = {}

        if self.meta_path.exists():
            self.meta = json.loads(self.meta_path.read_text())
        else:
            self.meta = {
                "id": profile_id,
                "name": profile_name or profile_id,
                "source": "user" if profile_id != "default" else "default",
                "created_at": time.time(),
                "glyph_count": 0,
            }

    # ------------------------------------------------------------------
    # Verwaltung
    # ------------------------------------------------------------------
    def reset(self) -> None:
        if self.glyph_dir.exists():
            for p in self.glyph_dir.glob("**/*"):
                if p.is_file():
                    p.unlink()
        self.glyph_dir.mkdir(parents=True, exist_ok=True)
        self._cache.clear()
        self.meta["glyph_count"] = 0

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        # glyph_count neu berechnen
        total = 0
        if self.glyph_dir.exists():
            for sub in self.glyph_dir.iterdir():
                if sub.is_dir():
                    total += len(list(sub.glob("*.png")))
        self.meta["glyph_count"] = total
        self.meta_path.write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2)
        )

    def add_glyph(self, char: str, variant: int, image: Image.Image) -> None:
        folder = self.glyph_dir / _hex(char)
        folder.mkdir(parents=True, exist_ok=True)
        image.save(folder / f"{variant}.png")

    # ------------------------------------------------------------------
    # Zugriff
    # ------------------------------------------------------------------
    def variants(self, char: str) -> List[Image.Image]:
        if char in self._cache:
            return self._cache[char]
        folder = self.glyph_dir / _hex(char)
        glyphs: List[Image.Image] = []
        if folder.exists():
            for p in sorted(folder.glob("*.png")):
                try:
                    glyphs.append(Image.open(p).convert("RGBA"))
                except Exception:
                    continue
        self._cache[char] = glyphs
        return glyphs

    def pick(self, char: str) -> Optional[Image.Image]:
        variants = self.variants(char)
        if not variants:
            return None
        return random.choice(variants)


# ---------------------------------------------------------------------------
# Default-Profil: programmatisch erzeugte Druckschrift-Glyphen.
# ---------------------------------------------------------------------------


def _load_font(size: int) -> ImageFont.ImageFont:
    for name in (
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Regular.ttf",
        "Arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _render_default_glyph(
    char: str, variant: int, font_size: int = 96
) -> Image.Image:
    """Erzeugt eine saubere Druckschrift-Glyph mit leichten Varianten."""
    font = _load_font(font_size + variant * 2)
    # Temporär messen.
    tmp = Image.new("RGBA", (font_size * 3, font_size * 3), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0, 0), char, font=font)
    w = max(bbox[2] - bbox[0], 4)
    h = max(bbox[3] - bbox[1], 4)
    pad = 6
    img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((pad - bbox[0], pad - bbox[1]), char, font=font, fill=(0, 0, 0, 235))
    # Minimale Rotation und Skalierung pro Variante.
    angle = [-1.5, 0.5, 1.8, -0.8][variant % 4]
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    return img


def ensure_default_profile() -> None:
    """Legt das Default-Profil an, falls es noch nicht existiert."""
    engine = GlyphEngine("default", profile_name="Standard-Druckschrift")
    if engine.meta.get("glyph_count", 0) > 0 and engine.glyph_dir.exists():
        # Nur prüfen, ob Inhalte vorhanden sind.
        for sub in engine.glyph_dir.iterdir():
            if sub.is_dir() and any(sub.glob("*.png")):
                return
    log.info("Erzeuge Default-Handschrift-Profil…")
    engine.reset()
    from .charset import VARIANT_COUNTS, all_characters

    for ch in all_characters():
        n = VARIANT_COUNTS.get(ch, 1)
        for v in range(n):
            glyph = _render_default_glyph(ch, v)
            engine.add_glyph(ch, v, glyph)
    engine.save()
    log.info("Default-Profil erstellt (%d Glyphen).", engine.meta["glyph_count"])


def list_profiles() -> List[Dict]:
    profiles: List[Dict] = []
    for folder in sorted(config.PROFILES_DIR.iterdir()):
        meta_path = folder / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        profiles.append(
            {
                "id": meta.get("id", folder.name),
                "name": meta.get("name", folder.name),
                "source": meta.get("source", "user"),
                "glyph_count": meta.get("glyph_count", 0),
                "created_at": meta.get("created_at"),
            }
        )
    return profiles


def delete_profile(profile_id: str) -> bool:
    if profile_id == "default":
        return False
    folder = config.PROFILES_DIR / profile_id
    if not folder.exists():
        return False
    import shutil

    shutil.rmtree(folder)
    return True
