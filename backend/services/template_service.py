"""Template-Erzeugung und -Auswertung für eigene Handschriften.

Ein Profil kann bis zu 4 Template-PAARE haben. Ein Paar besteht aus 2 Seiten
(alle 90 Zeichen). Jedes Paar erzeugt eine eigene Variante pro Zeichen, sodass
beim Rendern bis zu 4 verschiedene Varianten je Buchstabe zur Verfügung stehen.

Layout im Stil von Calligraphr:
- Vier schwarze Eckmarker (Fiducials) zur automatischen Ausrichtung
- Kopfzeile mit Titel & Paar-Nummer
- 8-spaltiges Raster mit großzügigen Schreibzellen
- Kleines Zeichen-Label in der linken oberen Ecke jeder Zelle
- Feine horizontale Hilfslinien im Schreibbereich
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .. import config
from .charset import all_characters

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

PAGE_W = config.PAGE_WIDTH_PX
PAGE_H = config.PAGE_HEIGHT_PX

MARGIN = config.mm_to_px(10)
FIDUCIAL_SIZE = config.mm_to_px(9)
HEADER_H = config.mm_to_px(16)
FOOTER_H = config.mm_to_px(14)

COLS = 8
ROWS = 7
LABEL_H = config.mm_to_px(4)

GRID_LEFT = MARGIN + FIDUCIAL_SIZE + config.mm_to_px(4)
GRID_RIGHT = PAGE_W - MARGIN - FIDUCIAL_SIZE - config.mm_to_px(4)
GRID_TOP = MARGIN + FIDUCIAL_SIZE + config.mm_to_px(4) + HEADER_H
GRID_BOTTOM = PAGE_H - MARGIN - FIDUCIAL_SIZE - config.mm_to_px(4) - FOOTER_H

GRID_W = GRID_RIGHT - GRID_LEFT
GRID_H = GRID_BOTTOM - GRID_TOP
CELL_W = GRID_W // COLS
CELL_H = GRID_H // ROWS
WRITE_H = CELL_H - LABEL_H

GUIDE_COLOR = (225, 228, 235)
GRID_COLOR = (70, 70, 90)
LABEL_COLOR = (40, 40, 55)

MAX_PAIRS = 4


@dataclass
class CellBox:
    char: str
    variant: int
    page: int
    x: int
    y: int
    w: int
    h: int


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _draw_fiducial(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    draw.rectangle([x, y, x + size, y + size], fill=(0, 0, 0))
    pad1 = size // 5
    draw.rectangle(
        [x + pad1, y + pad1, x + size - pad1, y + size - pad1],
        fill=(255, 255, 255),
    )
    pad2 = size * 2 // 5
    draw.rectangle(
        [x + pad2, y + pad2, x + size - pad2, y + size - pad2],
        fill=(0, 0, 0),
    )


def _fiducial_positions() -> List[Tuple[int, int]]:
    s = FIDUCIAL_SIZE
    return [
        (MARGIN, MARGIN),
        (PAGE_W - MARGIN - s, MARGIN),
        (MARGIN, PAGE_H - MARGIN - s),
        (PAGE_W - MARGIN - s, PAGE_H - MARGIN - s),
    ]


# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------


def _pair_cells(pair_index: int) -> List[Tuple[str, int]]:
    return [(ch, pair_index) for ch in all_characters()]


def _render_pages(cells: List[Tuple[str, int]],
                  profile_name: str,
                  pair_index: int) -> Tuple[List[Image.Image], List[CellBox]]:
    per_page = COLS * ROWS
    total_pages = max(1, (len(cells) + per_page - 1) // per_page)

    title_font = _font(config.mm_to_px(6))
    sub_font = _font(config.mm_to_px(3.2))
    label_font = _font(config.mm_to_px(3.8))
    ghost_font = _font(int(WRITE_H * 0.65))
    footer_font = _font(config.mm_to_px(2.8))

    pages: List[Image.Image] = []
    boxes: List[CellBox] = []

    for page_idx in range(total_pages):
        img = Image.new("RGB", (PAGE_W, PAGE_H), "white")
        draw = ImageDraw.Draw(img)

        for fx, fy in _fiducial_positions():
            _draw_fiducial(draw, fx, fy, FIDUCIAL_SIZE)

        header_y = MARGIN + config.mm_to_px(1)
        title = profile_name or "HefterPro"
        draw.text(
            (PAGE_W // 2, header_y),
            title,
            font=title_font, fill=(20, 20, 30), anchor="mt",
        )
        subtitle = (
            f"Template-Paar {pair_index + 1} · Seite {page_idx + 1}/{total_pages}"
        )
        draw.text(
            (PAGE_W // 2, header_y + config.mm_to_px(7)),
            subtitle,
            font=sub_font, fill=(110, 110, 120), anchor="mt",
        )

        draw.rectangle(
            [GRID_LEFT, GRID_TOP,
             GRID_LEFT + COLS * CELL_W, GRID_TOP + ROWS * CELL_H],
            outline=GRID_COLOR, width=1,
        )

        start = page_idx * per_page
        end = min(start + per_page, len(cells))

        for i, (ch, variant) in enumerate(cells[start:end]):
            col = i % COLS
            row = i // COLS
            cx = GRID_LEFT + col * CELL_W
            cy = GRID_TOP + row * CELL_H

            draw.rectangle(
                [cx, cy, cx + CELL_W, cy + CELL_H],
                outline=GRID_COLOR, width=1,
            )
            draw.line(
                [(cx, cy + LABEL_H), (cx + CELL_W, cy + LABEL_H)],
                fill=GRID_COLOR, width=1,
            )

            label = ch if len(ch) == 1 and ch.isprintable() else f"U+{ord(ch):04X}"
            draw.text(
                (cx + config.mm_to_px(1.5), cy + LABEL_H // 2),
                label, font=label_font, fill=LABEL_COLOR, anchor="lm",
            )

            write_top = cy + LABEL_H
            baseline_frac = 0.80
            for frac in (0.30, 0.55, baseline_frac):
                gy = write_top + int(WRITE_H * frac)
                draw.line(
                    [(cx + 4, gy), (cx + CELL_W - 4, gy)],
                    fill=GUIDE_COLOR, width=1,
                )

            ghost_label = ch if len(ch) == 1 and ch.isprintable() else ""
            if ghost_label:
                baseline_y = write_top + int(WRITE_H * baseline_frac)
                draw.text(
                    (cx + CELL_W // 2, baseline_y),
                    ghost_label,
                    font=ghost_font,
                    fill=(230, 232, 238),
                    anchor="ms",
                )

            boxes.append(CellBox(
                char=ch, variant=variant, page=page_idx,
                x=cx, y=write_top, w=CELL_W, h=WRITE_H,
            ))

        footer_y = PAGE_H - MARGIN - FIDUCIAL_SIZE // 2
        draw.text(
            (PAGE_W // 2, footer_y),
            "Bitte alle vier Eckmarker mit einscannen · HefterPro",
            font=footer_font, fill=(110, 110, 120), anchor="mm",
        )

        pages.append(img)

    return pages, boxes


# ---------------------------------------------------------------------------
# Pair management
# ---------------------------------------------------------------------------


def _pair_dir(profile_id: str, pair_index: int):
    return config.TEMPLATES_DIR / profile_id / f"pair-{pair_index}"


def generate_pair(profile_id: str, pair_index: int, profile_name: str) -> Dict:
    """Erzeugt ein Template-Paar (2 Seiten) und speichert Meta + PNGs."""
    if not (0 <= pair_index < MAX_PAIRS):
        raise ValueError(f"pair_index muss zwischen 0 und {MAX_PAIRS - 1} liegen.")

    cells = _pair_cells(pair_index)
    pages, boxes = _render_pages(cells, profile_name, pair_index)

    pair_dir = _pair_dir(profile_id, pair_index)
    pair_dir.mkdir(parents=True, exist_ok=True)

    page_urls = []
    for i, page in enumerate(pages):
        path = pair_dir / f"page-{i + 1}.png"
        page.save(path, "PNG")
        page_urls.append(
            f"/files/templates/{profile_id}/pair-{pair_index}/page-{i + 1}.png"
        )

    meta = {
        "profile_id": profile_id,
        "pair_index": pair_index,
        "page_size": [PAGE_W, PAGE_H],
        "dpi": config.PAGE_DPI,
        "fiducial_size": FIDUCIAL_SIZE,
        "fiducials": _fiducial_positions(),
        "cells": [b.__dict__ for b in boxes],
        "pages": len(pages),
        "page_urls": page_urls,
    }
    (pair_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2)
    )
    return meta


def load_pair_meta(profile_id: str, pair_index: int) -> Optional[Dict]:
    meta_path = _pair_dir(profile_id, pair_index) / "meta.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text())


# ---------------------------------------------------------------------------
# Scan alignment via fiducials
# ---------------------------------------------------------------------------


def _find_fiducial(gray: Image.Image, rx: int, ry: int,
                   rw: int, rh: int) -> Tuple[int, int]:
    W, H = gray.size
    rx = max(0, rx); ry = max(0, ry)
    rw = min(W - rx, rw); rh = min(H - ry, rh)
    if rw <= 0 or rh <= 0:
        return (rx, ry)
    sub = gray.crop((rx, ry, rx + rw, ry + rh))
    thr_img = ImageOps.autocontrast(sub).point(lambda v: 0 if v < 90 else 255)
    px = thr_img.load()
    sw, sh = thr_img.size
    sx = sy = count = 0
    for y in range(sh):
        for x in range(sw):
            if px[x, y] == 0:
                sx += x; sy += y; count += 1
    if count < 30:
        return (rx + rw // 2, ry + rh // 2)
    return (rx + sx // count, ry + sy // count)


def _align_scan(img: Image.Image, meta: Dict) -> Image.Image:
    tpl_w, tpl_h = meta["page_size"]
    img = img.convert("RGB").resize((tpl_w, tpl_h), Image.LANCZOS)
    gray = img.convert("L")

    s = meta.get("fiducial_size", FIDUCIAL_SIZE)
    search = int(s * 2.6)
    expected = meta["fiducials"]
    targets = [(ex + s // 2, ey + s // 2) for ex, ey in expected]

    found: List[Tuple[int, int]] = []
    for ex, ey in expected:
        cx, cy = _find_fiducial(
            gray,
            ex + s // 2 - search // 2,
            ey + s // 2 - search // 2,
            search, search,
        )
        found.append((cx, cy))

    try:
        import numpy as np
        from numpy.linalg import solve

        # 4-point perspective transform: solve for 8 coefficients
        # x_src = (a*x + b*y + c) / (g*x + h*y + 1)
        # y_src = (d*x + e*y + f) / (g*x + h*y + 1)
        rows = []
        rhs = []
        for (tx, ty), (sx, sy) in zip(targets, found):
            rows.append([tx, ty, 1, 0, 0, 0, -sx * tx, -sx * ty])
            rhs.append(sx)
            rows.append([0, 0, 0, tx, ty, 1, -sy * tx, -sy * ty])
            rhs.append(sy)
        A = np.array(rows, dtype=float)
        b = np.array(rhs, dtype=float)
        coeffs = solve(A, b)
        return img.transform(
            (tpl_w, tpl_h),
            Image.PERSPECTIVE,
            tuple(coeffs.tolist()),
            resample=Image.BICUBIC,
            fillcolor=(255, 255, 255),
        )
    except Exception as exc:
        log.warning("Fiducial-Ausrichtung fehlgeschlagen: %s", exc)
        return img


# ---------------------------------------------------------------------------
# Glyph extraction
# ---------------------------------------------------------------------------


def _otsu(hist: List[int]) -> int:
    total = sum(hist)
    if total == 0:
        return 128
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_b = 0.0
    w_b = 0
    max_var = -1.0
    thr = 128
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var = var
            thr = i
    return thr


TARGET_GLYPH_H = 140
TARGET_STROKE_PX = 5


def _zhang_suen(binary):
    import numpy as np
    skel = binary.copy()
    while True:
        removed = False
        for sub in (0, 1):
            P = skel
            P2 = np.roll(P,  1, axis=0)
            P3 = np.roll(np.roll(P,  1, axis=0), -1, axis=1)
            P4 = np.roll(P, -1, axis=1)
            P5 = np.roll(np.roll(P, -1, axis=0), -1, axis=1)
            P6 = np.roll(P, -1, axis=0)
            P7 = np.roll(np.roll(P, -1, axis=0),  1, axis=1)
            P8 = np.roll(P,  1, axis=1)
            P9 = np.roll(np.roll(P,  1, axis=0),  1, axis=1)

            B = (P2.astype(np.int8) + P3 + P4 + P5 + P6 + P7 + P8 + P9)
            seq = np.stack([P2, P3, P4, P5, P6, P7, P8, P9, P2], axis=-1)
            trans = ((~seq[..., :-1]) & seq[..., 1:]).sum(axis=-1)

            common = P & (B >= 2) & (B <= 6) & (trans == 1)
            if sub == 0:
                cond = common & ~(P2 & P4 & P6) & ~(P4 & P6 & P8)
            else:
                cond = common & ~(P2 & P4 & P8) & ~(P2 & P6 & P8)

            if cond.any():
                skel = skel & ~cond
                removed = True
        if not removed:
            break
    return skel


def _dilate_disk(mask, radius: int):
    import numpy as np
    r = max(1, int(radius))
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    disk = xx * xx + yy * yy <= r * r

    h, w = mask.shape
    out = np.zeros_like(mask)
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys, xs):
        y0 = max(0, y - r); y1 = min(h, y + r + 1)
        x0 = max(0, x - r); x1 = min(w, x + r + 1)
        dy0 = y0 - (y - r); dy1 = dy0 + (y1 - y0)
        dx0 = x0 - (x - r); dx1 = dx0 + (x1 - x0)
        out[y0:y1, x0:x1] |= disk[dy0:dy1, dx0:dx1]
    return out


def _extract_ink(cell: Image.Image) -> Optional[Image.Image]:
    import numpy as np

    gray = cell.convert("L")
    w, h = gray.size

    border = max(2, int(min(w, h) * 0.05))
    inner = gray.crop((border, border, w - border, h - border))

    blurred = inner.filter(ImageFilter.GaussianBlur(radius=0.6))
    thr = _otsu(blurred.histogram())
    thr = min(thr, 175)

    binary_img = blurred.point(lambda v: 255 if v < thr else 0).convert("L")
    bbox = binary_img.getbbox()
    if bbox is None:
        return None

    iw, ih = inner.size
    minx, miny, maxx, maxy = bbox
    if (maxx - minx) * (maxy - miny) < 80:
        return None

    pad = max(6, min(maxx - minx, maxy - miny) // 10)
    minx = max(0, minx - pad); miny = max(0, miny - pad)
    maxx = min(iw, maxx + pad); maxy = min(ih, maxy + pad)

    cropped = binary_img.crop((minx, miny, maxx, maxy))

    cw, ch = cropped.size
    if ch <= 0:
        return None
    scale = TARGET_GLYPH_H / ch
    new_w = max(4, int(round(cw * scale)))
    resized = cropped.resize((new_w, TARGET_GLYPH_H), Image.LANCZOS)
    arr = np.array(resized, dtype=np.uint8) > 127

    closed = arr | (
        np.roll(arr,  1, axis=0) & np.roll(arr, -1, axis=0) &
        np.roll(arr,  1, axis=1) & np.roll(arr, -1, axis=1)
    )

    skeleton = _zhang_suen(closed)
    if not skeleton.any():
        return None

    uniform = _dilate_disk(skeleton, TARGET_STROKE_PX)

    alpha_img = Image.fromarray((uniform * 255).astype("uint8"), "L")
    alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=1.0))

    rgba = Image.new("RGBA", alpha_img.size, (0, 0, 0, 0))
    solid = Image.new("RGBA", alpha_img.size, (0, 0, 0, 255))
    rgba.paste(solid, (0, 0), alpha_img)
    return rgba


def process_uploaded_pair(
    images: List[Image.Image],
    profile_id: str,
    pair_index: int,
) -> Dict:
    """Extrahiert Glyphen aus den gescannten Seiten eines Template-Paares.

    Jedes Zeichen wird als Variante ``pair_index`` abgelegt, sodass bei
    mehreren Paaren pro Profil mehrere Varianten zur Verfügung stehen.
    """
    meta = load_pair_meta(profile_id, pair_index)
    if meta is None:
        raise ValueError(
            f"Template-Paar {pair_index} für Profil {profile_id} nicht gefunden."
        )

    profile_dir = config.PROFILES_DIR / profile_id
    glyph_dir = profile_dir / "glyphs"
    glyph_dir.mkdir(parents=True, exist_ok=True)

    cells_by_page: Dict[int, list] = {}
    for c in meta["cells"]:
        cells_by_page.setdefault(c["page"], []).append(c)

    stored = 0
    chars_seen = set()
    extracted: List[Tuple[str, Image.Image]] = []

    for page_idx, img in enumerate(images):
        if page_idx not in cells_by_page:
            continue
        aligned = _align_scan(img, meta)

        for c in cells_by_page[page_idx]:
            sub = aligned.crop((c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]))
            glyph = _extract_ink(sub)
            if glyph is None:
                continue

            hex_code = f"{ord(c['char']):06x}"
            char_dir = glyph_dir / hex_code
            char_dir.mkdir(exist_ok=True)
            glyph_path = char_dir / f"{pair_index}.png"
            glyph.save(glyph_path, "PNG")
            stored += 1
            chars_seen.add(c["char"])
            extracted.append((c["char"], glyph))

    preview_url: Optional[str] = None
    if extracted:
        pair_dir = _pair_dir(profile_id, pair_index)
        pair_dir.mkdir(parents=True, exist_ok=True)
        preview_path = pair_dir / "glyph-preview.png"
        _save_glyph_sheet(extracted, preview_path)
        preview_url = (
            f"/files/templates/{profile_id}/pair-{pair_index}/glyph-preview.png"
        )

    log.info(
        "Profil %s Paar %d: %d Glyphen für %d Zeichen.",
        profile_id, pair_index, stored, len(chars_seen),
    )
    return {
        "profile_id": profile_id,
        "pair_index": pair_index,
        "glyph_count": stored,
        "char_count": len(chars_seen),
        "preview_url": preview_url,
    }


def _save_glyph_sheet(items: List[Tuple[str, Image.Image]], out_path) -> None:
    """Speichert eine Übersicht aller extrahierten Glyphen mit Labels."""
    cols = 10
    cell_w = 110
    cell_h = 160
    label_h = 28
    rows = (len(items) + cols - 1) // cols
    width = cols * cell_w + 20
    height = rows * cell_h + 20
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)

    for i, (char, glyph) in enumerate(items):
        col = i % cols
        row = i // cols
        cx = 10 + col * cell_w
        cy = 10 + row * cell_h

        draw.rectangle(
            [cx, cy, cx + cell_w - 4, cy + cell_h - 4],
            outline=(220, 220, 230), width=1,
        )
        label = char if len(char) == 1 and char.isprintable() else f"U+{ord(char):04X}"
        draw.text((cx + 6, cy + 4), label, font=font, fill=(60, 60, 80))

        gw, gh = glyph.size
        max_w = cell_w - 16
        max_h = cell_h - label_h - 12
        scale = min(max_w / gw, max_h / gh, 1.0)
        nw = max(1, int(gw * scale))
        nh = max(1, int(gh * scale))
        resized = glyph.resize((nw, nh), Image.LANCZOS)
        px = cx + (cell_w - nw) // 2
        py = cy + label_h + (max_h - nh) // 2
        sheet.paste(resized, (px, py), resized)

    sheet.save(out_path, "PNG")
