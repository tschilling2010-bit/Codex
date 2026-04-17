"""Template-Erzeugung und -Auswertung für eigene Handschriften.

Erzeugt druckbare Template-Seiten als PNG-Bilder. Jede Zelle zeigt ein
Zeichen als Hinweis und einen Schreibbereich. Nach dem Scan werden die
Zellen ausgeschnitten und als transparente Glyph-PNGs gespeichert.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .. import config
from .charset import template_cells

log = logging.getLogger(__name__)

PAGE_W = config.PAGE_WIDTH_PX
PAGE_H = config.PAGE_HEIGHT_PX
MARGIN = config.mm_to_px(12)
CELL_W = config.mm_to_px(16)
CELL_H = config.mm_to_px(18)
HINT_H = config.mm_to_px(5)
WRITE_H = CELL_H - HINT_H


@dataclass
class CellBox:
    char: str
    variant: int
    page: int
    x: int
    y: int
    w: int
    h: int


def _hint_font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _layout() -> Tuple[int, int]:
    cols = max(1, (PAGE_W - 2 * MARGIN) // CELL_W)
    rows = max(1, (PAGE_H - 2 * MARGIN - config.mm_to_px(18)) // CELL_H)
    return cols, rows


def _render_pages(cells, cols, rows) -> Tuple[List[Image.Image], List[CellBox]]:
    per_page = cols * rows
    total_pages = (len(cells) + per_page - 1) // per_page

    title_font = _hint_font(config.mm_to_px(5))
    hint_font = _hint_font(config.mm_to_px(3.5))
    small_font = _hint_font(config.mm_to_px(2.5))

    pages: List[Image.Image] = []
    boxes: List[CellBox] = []

    for page_idx in range(total_pages):
        img = Image.new("RGB", (PAGE_W, PAGE_H), "white")
        draw = ImageDraw.Draw(img)

        draw.text(
            (MARGIN, MARGIN // 2),
            "HefterPro - Handschrift-Template",
            font=title_font, fill=(30, 30, 40),
        )
        draw.text(
            (MARGIN, MARGIN // 2 + config.mm_to_px(6)),
            f"Seite {page_idx + 1}/{total_pages} - Jede Zelle mit dem Zeichen ausfuellen",
            font=small_font, fill=(100, 100, 110),
        )

        y0 = MARGIN + config.mm_to_px(12)
        start = page_idx * per_page
        end = min(start + per_page, len(cells))

        for i, (ch, variant) in enumerate(cells[start:end]):
            col = i % cols
            row = i // cols
            x = MARGIN + col * CELL_W
            y = y0 + row * CELL_H

            draw.rectangle([x, y, x + CELL_W - 1, y + HINT_H], fill=(240, 240, 245))
            label = ch if len(ch) == 1 and ch.isprintable() else f"U+{ord(ch):04X}"
            if variant > 0:
                label += f" ({variant + 1})"
            draw.text((x + 4, y + 2), label, font=hint_font, fill=(80, 80, 100))

            draw.rectangle(
                [x, y + HINT_H, x + CELL_W - 1, y + CELL_H - 1],
                outline=(180, 185, 200), width=1,
            )
            baseline_y = y + HINT_H + int(WRITE_H * 0.72)
            draw.line(
                [(x + 3, baseline_y), (x + CELL_W - 4, baseline_y)],
                fill=(215, 220, 235), width=1,
            )

            boxes.append(CellBox(
                char=ch, variant=variant, page=page_idx,
                x=x, y=y + HINT_H, w=CELL_W - 1, h=WRITE_H,
            ))

        pages.append(img)

    return pages, boxes


def generate_template(profile_id: str) -> Dict:
    """Generates template pages as PNGs and returns metadata."""
    cols, rows = _layout()
    cells = template_cells()
    pages, boxes = _render_pages(cells, cols, rows)

    template_dir = config.TEMPLATES_DIR / profile_id
    template_dir.mkdir(parents=True, exist_ok=True)

    page_urls = []
    for i, page in enumerate(pages):
        path = template_dir / f"page-{i + 1}.png"
        page.save(path, "PNG")
        page_urls.append(f"/files/templates/{profile_id}/page-{i + 1}.png")

    meta = {
        "profile_id": profile_id,
        "page_size": [PAGE_W, PAGE_H],
        "dpi": config.PAGE_DPI,
        "cells": [b.__dict__ for b in boxes],
        "pages": len(pages),
        "page_urls": page_urls,
    }
    meta_path = template_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def load_template_meta(profile_id: str) -> Optional[Dict]:
    meta_path = config.TEMPLATES_DIR / profile_id / "meta.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text())


# ---------------------------------------------------------------------------
# Glyph extraction from scanned template
# ---------------------------------------------------------------------------


def _find_ink_bbox(cell: Image.Image, threshold: int = 170) -> Tuple[int, int, int, int]:
    gray = cell.convert("L")
    w, h = gray.size
    px = gray.load()
    minx, miny, maxx, maxy = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            if px[x, y] < threshold:
                minx = min(minx, x)
                miny = min(miny, y)
                maxx = max(maxx, x)
                maxy = max(maxy, y)
                found = True
    if not found:
        return (0, 0, 0, 0)
    pad = 3
    return (max(0, minx - pad), max(0, miny - pad),
            min(w - 1, maxx + pad), min(h - 1, maxy + pad))


def _cell_to_glyph(cell: Image.Image) -> Optional[Image.Image]:
    bbox = _find_ink_bbox(cell)
    if bbox == (0, 0, 0, 0):
        return None
    cropped = cell.crop(bbox).convert("L")
    rgba = Image.new("RGBA", cropped.size, (0, 0, 0, 0))
    px_src = cropped.load()
    px_dst = rgba.load()
    w, h = cropped.size
    for y in range(h):
        for x in range(w):
            v = px_src[x, y]
            if v < 220:
                alpha = min(255, int((220 - v) * 1.5))
                px_dst[x, y] = (0, 0, 0, alpha)
    return rgba


def process_uploaded_template(
    images: List[Image.Image],
    profile_id: str,
    profile_name: str,
) -> Dict:
    """Extracts handwritten glyphs from scanned template pages."""
    meta = load_template_meta(profile_id)
    if meta is None:
        raise ValueError(f"Template-Metadaten für {profile_id} nicht gefunden.")

    profile_dir = config.PROFILES_DIR / profile_id
    glyph_dir = profile_dir / "glyphs"
    glyph_dir.mkdir(parents=True, exist_ok=True)

    template_w, template_h = meta["page_size"]
    cells_by_page: Dict[int, list] = {}
    for c in meta["cells"]:
        cells_by_page.setdefault(c["page"], []).append(c)

    stored = 0
    char_map: Dict[str, List[str]] = {}

    for page_idx, img in enumerate(images):
        if page_idx not in cells_by_page:
            continue
        img = img.resize((template_w, template_h))

        for c in cells_by_page[page_idx]:
            sub = img.crop((c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]))
            glyph = _cell_to_glyph(sub)
            if glyph is None:
                continue

            hex_code = f"{ord(c['char']):06x}"
            char_dir = glyph_dir / hex_code
            char_dir.mkdir(exist_ok=True)
            glyph_path = char_dir / f"{c['variant']}.png"
            glyph.save(glyph_path, "PNG")
            stored += 1
            char_map.setdefault(c["char"], []).append(str(glyph_path.name))

    profile_meta = {
        "id": profile_id,
        "name": profile_name,
        "source": "user",
        "created_at": time.time(),
        "glyph_count": stored,
        "char_count": len(char_map),
    }
    meta_path = profile_dir / "meta.json"
    meta_path.write_text(json.dumps(profile_meta, ensure_ascii=False, indent=2))

    log.info("Profil %s: %d Glyphen fuer %d Zeichen.", profile_id, stored, len(char_map))
    return {"profile_id": profile_id, "glyph_count": stored, "char_count": len(char_map)}
