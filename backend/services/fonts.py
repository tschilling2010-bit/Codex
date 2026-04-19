"""Profilverwaltung für HefterPro.

Ein Profil hält:
- Metadaten (Name, Erstellzeit)
- Einstellungen (Größe, Strichstärke, Tinte, Blatt) — persistent pro Profil
- bis zu ``MAX_PAIRS`` Template-Paare (je 2 Seiten)
- Glyphen im Ordner ``glyphs/{hex_char}/{pair_index}.png``

Beim Rendern wählt :meth:`GlyphProfile.pick` zufällig eine der vorhandenen
Varianten je Buchstabe aus.
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

from .. import config

log = logging.getLogger(__name__)

# TTF-Ordner für das Hefterblatt-Rendering (nicht für Handschriften).
FONTS_DIR: Path = config.BASE_DIR / "fonts"

MAX_PAIRS = 4

DEFAULT_SETTINGS: Dict = {
    "size_scale": 1.0,
    "thickness": 1.0,
    "ink_color": "#16306b",
    "sheet_type": "liniert",
    "jitter": 0.6,
}


@dataclass
class GlyphProfile:
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


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _meta_path(profile_id: str) -> Path:
    return config.PROFILES_DIR / profile_id / "meta.json"


def _read_meta(profile_id: str) -> Optional[Dict]:
    path = _meta_path(profile_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _write_meta(profile_id: str, meta: Dict) -> None:
    path = _meta_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def _count_glyphs(profile_id: str) -> int:
    glyph_dir = config.PROFILES_DIR / profile_id / "glyphs"
    if not glyph_dir.exists():
        return 0
    return sum(1 for _ in glyph_dir.rglob("*.png"))


def _ensure_settings(meta: Dict) -> Dict:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(meta.get("settings") or {})
    meta["settings"] = settings
    meta.setdefault("pairs", [])
    meta.setdefault("glyph_count", 0)
    meta.setdefault("source", "user")
    return meta


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------


def create_profile(profile_id: str, name: str) -> Dict:
    profile_dir = config.PROFILES_DIR / profile_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "glyphs").mkdir(exist_ok=True)

    meta = {
        "id": profile_id,
        "name": (name or profile_id).strip() or profile_id,
        "source": "user",
        "created_at": time.time(),
        "settings": dict(DEFAULT_SETTINGS),
        "pairs": [],
        "glyph_count": 0,
    }
    _write_meta(profile_id, meta)
    return meta


def get_profile(profile_id: str) -> Optional[Dict]:
    meta = _read_meta(profile_id)
    if meta is None:
        return None
    meta = _ensure_settings(meta)
    meta["glyph_count"] = _count_glyphs(profile_id)
    return meta


def get_glyph_profile(profile_id: str) -> Optional[GlyphProfile]:
    meta = get_profile(profile_id)
    if meta is None:
        return None
    return GlyphProfile(
        id=meta["id"],
        name=meta.get("name", profile_id),
        glyph_count=meta.get("glyph_count", 0),
    )


def is_glyph_profile(profile_id: str) -> bool:
    return _meta_path(profile_id).exists()


def list_profiles() -> List[Dict]:
    out: List[Dict] = []
    if not config.PROFILES_DIR.exists():
        return out
    for folder in sorted(config.PROFILES_DIR.iterdir()):
        meta = _read_meta(folder.name)
        if meta is None:
            continue
        meta = _ensure_settings(meta)
        meta["glyph_count"] = _count_glyphs(folder.name)
        out.append(meta)
    return out


def update_settings(profile_id: str, settings: Dict) -> Optional[Dict]:
    meta = get_profile(profile_id)
    if meta is None:
        return None
    allowed = {"size_scale", "thickness", "ink_color", "sheet_type", "jitter"}
    for key in allowed:
        if key in settings and settings[key] is not None:
            meta["settings"][key] = settings[key]
    _write_meta(profile_id, meta)
    return meta


def rename_profile(profile_id: str, name: str) -> Optional[Dict]:
    meta = get_profile(profile_id)
    if meta is None:
        return None
    meta["name"] = (name or profile_id).strip() or profile_id
    _write_meta(profile_id, meta)
    return meta


def delete_user_profile(profile_id: str) -> bool:
    folder = config.PROFILES_DIR / profile_id
    tpl_folder = config.TEMPLATES_DIR / profile_id
    if not folder.exists():
        return False
    import shutil
    shutil.rmtree(folder)
    if tpl_folder.exists():
        shutil.rmtree(tpl_folder, ignore_errors=True)
    return True


# ---------------------------------------------------------------------------
# Pair tracking
# ---------------------------------------------------------------------------


def register_pair(profile_id: str, pair_index: int) -> Optional[Dict]:
    meta = get_profile(profile_id)
    if meta is None:
        return None
    existing = next((p for p in meta["pairs"] if p["index"] == pair_index), None)
    if existing is None:
        meta["pairs"].append({
            "index": pair_index,
            "created_at": time.time(),
            "glyph_count": 0,
            "uploaded_at": None,
        })
        meta["pairs"].sort(key=lambda p: p["index"])
        _write_meta(profile_id, meta)
    return meta


def mark_pair_uploaded(profile_id: str, pair_index: int,
                       glyph_count: int) -> Optional[Dict]:
    meta = get_profile(profile_id)
    if meta is None:
        return None
    existing = next((p for p in meta["pairs"] if p["index"] == pair_index), None)
    if existing is None:
        meta["pairs"].append({
            "index": pair_index,
            "created_at": time.time(),
            "glyph_count": glyph_count,
            "uploaded_at": time.time(),
        })
    else:
        existing["glyph_count"] = glyph_count
        existing["uploaded_at"] = time.time()
    meta["pairs"].sort(key=lambda p: p["index"])
    meta["glyph_count"] = _count_glyphs(profile_id)
    _write_meta(profile_id, meta)
    return meta


def next_free_pair_index(profile_id: str) -> Optional[int]:
    meta = get_profile(profile_id)
    if meta is None:
        return 0
    used = {p["index"] for p in meta["pairs"]}
    for i in range(MAX_PAIRS):
        if i not in used:
            return i
    return None
