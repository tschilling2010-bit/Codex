"""Template-Erzeugung und -Auswertung für eigene Handschriften.

Das Template ist ein festes Rasterblatt: jede Zelle trägt ein Zeichen als
Hinweis und einen Bereich, in den der Nutzer das Zeichen einträgt.  Da die
Zellen auf dem Blatt genaue Koordinaten haben, kann das ausgefüllte Scan-
Bild rein geometrisch (ohne KI) zurückgeschnitten werden.

Der gelieferte Template-PDF-Export enthält die Gitterkoordinaten in der
oberen linken Ecke als kleine Ankerkreuze, um Skalierung und Rotation des
gescannten Bildes zuverlässig zu erkennen.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from .. import config
from .charset import template_cells
from .glyph_engine import GlyphEngine

log = logging.getLogger(__name__)

# Layout des Templates (A4, 150 dpi).
PAGE_W = config.PAGE_WIDTH_PX
PAGE_H = config.PAGE_HEIGHT_PX
MARGIN = config.mm_to_px(15)
CELL_W = config.mm_to_px(18)
CELL_H = config.mm_to_px(20)
HINT_H = config.mm_to_px(5)
ANCHOR_SIZE = config.mm_to_px(4)


@dataclass
class CellBox:
    char: str
    variant: int
    page: int
    x: int
    y: int
    w: int
    h: int


def _load_hint_font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _draw_anchors(draw: ImageDraw.ImageDraw) -> None:
    s = ANCHOR_SIZE
    for cx, cy in [
        (MARGIN, MARGIN),
        (PAGE_W - MARGIN, MARGIN),
        (MARGIN, PAGE_H - MARGIN),
        (PAGE_W - MARGIN, PAGE_H - MARGIN),
    ]:
        draw.rectangle([cx - s, cy - s, cx + s, cy + s], fill="black")
        draw.rectangle(
            [cx - s + 6, cy - s + 6, cx + s - 6, cy + s - 6], fill="white"
        )


def _layout() -> Tuple[int, int]:
    cols = max(1, (PAGE_W - 2 * MARGIN) // CELL_W)
    rows = max(1, (PAGE_H - 2 * MARGIN - config.mm_to_px(15)) // CELL_H)
    return cols, rows


def generate_template(output_path: Path) -> Dict:
    """Erzeugt das Template als mehrseitiges PDF (+ Metadaten)."""
    cols, rows = _layout()
    per_page = cols * rows
    cells = template_cells()

    pages: List[Image.Image] = []
    boxes: List[CellBox] = []

    title_font = _load_hint_font(config.mm_to_px(6))
    hint_font = _load_hint_font(config.mm_to_px(4))
    small_font = _load_hint_font(config.mm_to_px(3))

    total_pages = (len(cells) + per_page - 1) // per_page
    for page_idx in range(total_pages):
        img = Image.new("RGB", (PAGE_W, PAGE_H), "white")
        draw = ImageDraw.Draw(img)
        _draw_anchors(draw)

        title = "HefterPro · Handschrift-Template"
        draw.text((MARGIN, MARGIN // 2), title, font=title_font, fill="black")
        draw.text(
            (MARGIN, MARGIN // 2 + config.mm_to_px(7)),
            f"Seite {page_idx + 1} von {total_pages} — "
            "bitte jede Zelle mit dem angegebenen Zeichen ausfüllen.",
            font=small_font,
            fill=(70, 70, 70),
        )

        start = page_idx * per_page
        end = min(start + per_page, len(cells))
        y0 = MARGIN + config.mm_to_px(15)
        for i, (ch, variant) in enumerate(cells[start:end]):
            col = i % cols
            row = i // cols
            x = MARGIN + col * CELL_W
            y = y0 + row * CELL_H
            # Hinweis in grau.
            draw.rectangle([x, y, x + CELL_W, y + HINT_H], fill=(245, 245, 247))
            draw.text(
                (x + 4, y + 2),
                f"{ch}  ({variant + 1})",
                font=hint_font,
                fill=(120, 120, 128),
            )
            # Schreibbereich.
            draw.rectangle(
                [x, y + HINT_H, x + CELL_W, y + CELL_H],
                outline=(200, 200, 210),
                width=1,
            )
            boxes.append(
                CellBox(
                    char=ch,
                    variant=variant,
                    page=page_idx,
                    x=x,
                    y=y + HINT_H,
                    w=CELL_W,
                    h=CELL_H - HINT_H,
                )
            )
        pages.append(img)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(
        output_path,
        save_all=True,
        append_images=pages[1:],
        resolution=config.PAGE_DPI,
    )

    meta = {
        "page_size": [PAGE_W, PAGE_H],
        "dpi": config.PAGE_DPI,
        "cells": [b.__dict__ for b in boxes],
        "pages": total_pages,
    }
    meta_path = output_path.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


# ---------------------------------------------------------------------------
# Upload-Verarbeitung: ausgefülltes Template wird in Glyphen zerlegt.
# ---------------------------------------------------------------------------


def _bbox_of_ink(cell: Image.Image, threshold: int = 170) -> Tuple[int, int, int, int]:
    gray = cell.convert("L")
    w, h = gray.size
    px = gray.load()
    minx, miny, maxx, maxy = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            if px[x, y] < threshold:
                if x < minx:
                    minx = x
                if y < miny:
                    miny = y
                if x > maxx:
                    maxx = x
                if y > maxy:
                    maxy = y
                found = True
    if not found:
        return 0, 0, 0, 0
    pad = 2
    minx = max(0, minx - pad)
    miny = max(0, miny - pad)
    maxx = min(w - 1, maxx + pad)
    maxy = min(h - 1, maxy + pad)
    return minx, miny, maxx, maxy


def _cell_to_glyph(cell: Image.Image) -> Image.Image | None:
    bbox = _bbox_of_ink(cell)
    if bbox == (0, 0, 0, 0):
        return None
    cropped = cell.crop(bbox).convert("L")
    # Transparenter Hintergrund, schwarze Tinte.
    rgba = Image.new("RGBA", cropped.size, (0, 0, 0, 0))
    px_src = cropped.load()
    px_dst = rgba.load()
    w, h = cropped.size
    for y in range(h):
        for x in range(w):
            v = px_src[x, y]
            if v < 210:
                alpha = 255 - v
                px_dst[x, y] = (0, 0, 0, alpha)
    return rgba


def process_uploaded_template(
    images: List[Image.Image],
    template_meta: Dict,
    profile_id: str,
    profile_name: str,
) -> Dict:
    """Schneidet ausgefülltes Template in einzelne Glyphen und speichert sie."""
    engine = GlyphEngine(profile_id, profile_name=profile_name)
    engine.reset()

    template_w, template_h = template_meta["page_size"]
    cells_by_page: Dict[int, list] = {}
    for c in template_meta["cells"]:
        cells_by_page.setdefault(c["page"], []).append(c)

    stored = 0
    for page_idx, img in enumerate(images):
        if page_idx not in cells_by_page:
            continue
        # Auf Template-Koordinaten skalieren.
        img = img.resize((template_w, template_h))
        for c in cells_by_page[page_idx]:
            sub = img.crop((c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]))
            glyph = _cell_to_glyph(sub)
            if glyph is None:
                continue
            engine.add_glyph(c["char"], c["variant"], glyph)
            stored += 1

    engine.save()
    log.info("Profil %s mit %d Glyphen gespeichert.", profile_id, stored)
    return {"profile_id": profile_id, "glyph_count": stored}
