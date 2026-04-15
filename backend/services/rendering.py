"""Text → Handschrift-Rendering.

Rendert normalen Text auf eines oder mehrere A4-Blätter.  Der Renderer
nutzt die gespeicherten Glyphen eines Profils, variiert pro Zeichen Höhe,
Basislinie, Rotation und Abstand leicht und achtet auf Absätze,
Zeilenumbrüche und einfache Stichpunkt-Listen.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw

from .. import config
from .glyph_engine import GlyphEngine

log = logging.getLogger(__name__)


@dataclass
class RenderOptions:
    profile_id: str = "default"
    sheet_type: str = "liniert"  # liniert, kariert, blanko
    margin_mm: float = 20
    line_height_mm: float = 9
    glyph_height_mm: float = 5.5
    ink_color: str = "#1a2a6c"
    jitter: float = 1.0


# ---------------------------------------------------------------------------
# Blatt-Hintergrund
# ---------------------------------------------------------------------------


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def make_sheet_background(sheet_type: str) -> Image.Image:
    img = Image.new("RGB", (config.PAGE_WIDTH_PX, config.PAGE_HEIGHT_PX), "white")
    draw = ImageDraw.Draw(img)
    if sheet_type == "liniert":
        step = config.mm_to_px(9)
        for y in range(config.mm_to_px(25), config.PAGE_HEIGHT_PX - config.mm_to_px(20), step):
            draw.line(
                [(config.mm_to_px(15), y), (config.PAGE_WIDTH_PX - config.mm_to_px(10), y)],
                fill=(210, 220, 235),
                width=1,
            )
        # Randlinie rot.
        draw.line(
            [
                (config.mm_to_px(25), config.mm_to_px(15)),
                (config.mm_to_px(25), config.PAGE_HEIGHT_PX - config.mm_to_px(15)),
            ],
            fill=(230, 170, 170),
            width=1,
        )
    elif sheet_type == "kariert":
        step = config.mm_to_px(5)
        color = (215, 225, 240)
        for x in range(config.mm_to_px(10), config.PAGE_WIDTH_PX - config.mm_to_px(10), step):
            draw.line(
                [(x, config.mm_to_px(10)), (x, config.PAGE_HEIGHT_PX - config.mm_to_px(10))],
                fill=color,
                width=1,
            )
        for y in range(config.mm_to_px(10), config.PAGE_HEIGHT_PX - config.mm_to_px(10), step):
            draw.line(
                [(config.mm_to_px(10), y), (config.PAGE_WIDTH_PX - config.mm_to_px(10), y)],
                fill=color,
                width=1,
            )
    # blanko → nichts.
    return img


# ---------------------------------------------------------------------------
# Glyph-Vorbereitung
# ---------------------------------------------------------------------------


def _tint(glyph: Image.Image, color: Tuple[int, int, int]) -> Image.Image:
    """Färbt eine transparente Glyph (schwarze Tinte) in die Zielfarbe um."""
    r, g, b = color
    tinted = Image.new("RGBA", glyph.size, (r, g, b, 0))
    alpha = glyph.split()[-1]
    tinted.putalpha(alpha)
    return tinted


def _scale_glyph(glyph: Image.Image, target_height: int) -> Image.Image:
    w, h = glyph.size
    if h <= 0:
        return glyph
    scale = target_height / h
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return glyph.resize((new_w, new_h), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------


def _tokens(text: str) -> List[List[str]]:
    """Teilt Text in Zeilen, jede Zeile ist eine Liste von Tokens.

    Wörter werden beibehalten, damit beim Umbruch ganze Wörter auf die neue
    Zeile wandern können.
    """
    lines: List[List[str]] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        tokens: List[str] = []
        buf = ""
        for ch in raw_line:
            if ch == " ":
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(" ")
            else:
                buf += ch
        if buf:
            tokens.append(buf)
        lines.append(tokens)
    return lines


def _bullet_prefix(line_tokens: List[str]) -> Tuple[bool, List[str]]:
    if not line_tokens:
        return False, line_tokens
    first = line_tokens[0]
    if first in ("-", "•", "*", "·"):
        return True, line_tokens[1:]
    return False, line_tokens


# ---------------------------------------------------------------------------
# Hauptrenderer
# ---------------------------------------------------------------------------


class HandwritingRenderer:
    def __init__(self, engine: GlyphEngine, options: RenderOptions):
        self.engine = engine
        self.options = options
        self.color = _hex_to_rgb(options.ink_color)
        self.glyph_height = config.mm_to_px(options.glyph_height_mm)
        self.line_height = config.mm_to_px(options.line_height_mm)
        self.margin_left = config.mm_to_px(options.margin_mm + 5)
        self.margin_right = config.mm_to_px(options.margin_mm)
        self.margin_top = config.mm_to_px(options.margin_mm + 5)
        self.margin_bottom = config.mm_to_px(options.margin_mm)
        self.page_w = config.PAGE_WIDTH_PX
        self.page_h = config.PAGE_HEIGHT_PX
        self.content_w = self.page_w - self.margin_left - self.margin_right
        self.rng = random.Random()

    def _new_page(self) -> Image.Image:
        return make_sheet_background(self.options.sheet_type)

    def _space_width(self) -> int:
        return int(self.glyph_height * 0.35)

    def _render_token_width(self, token: str) -> int:
        """Misst die ungefähre Breite eines Tokens."""
        if token == " ":
            return self._space_width()
        total = 0
        for ch in token:
            g = self.engine.pick(ch)
            if g is None:
                # Unbekanntes Zeichen → als schmaler Platzhalter einrechnen.
                total += int(self.glyph_height * 0.4)
                continue
            scaled = _scale_glyph(g, self.glyph_height)
            total += scaled.width + int(self.glyph_height * 0.05)
        return total

    def _paste_token(
        self,
        page: Image.Image,
        x: int,
        baseline_y: int,
        token: str,
    ) -> int:
        jitter = self.options.jitter
        for ch in token:
            g = self.engine.pick(ch)
            if g is None:
                x += int(self.glyph_height * 0.4)
                continue
            scaled = _scale_glyph(g, int(self.glyph_height * (1 + self.rng.uniform(-0.04, 0.04) * jitter)))
            tinted = _tint(scaled, self.color)
            dy = int(self.rng.uniform(-2, 2) * jitter)
            dx = int(self.rng.uniform(-1, 1) * jitter)
            y = baseline_y - scaled.height + dy
            page.paste(tinted, (x + dx, y), tinted)
            x += scaled.width + int(self.glyph_height * 0.05) + int(
                self.rng.uniform(-1, 1) * jitter
            )
        return x

    def render(self, text: str) -> List[Image.Image]:
        lines = _tokens(text)
        pages: List[Image.Image] = []
        current = self._new_page()
        pages.append(current)

        baseline = self.margin_top + self.glyph_height
        max_y = self.page_h - self.margin_bottom

        for tokens in lines:
            is_bullet, rest = _bullet_prefix(tokens)
            x_start = self.margin_left + (config.mm_to_px(6) if is_bullet else 0)
            x = x_start

            if is_bullet:
                # Stichpunkt zeichnen.
                g = self.engine.pick("•") or self.engine.pick("-")
                if g is not None:
                    scaled = _scale_glyph(g, int(self.glyph_height * 0.9))
                    tinted = _tint(scaled, self.color)
                    current.paste(
                        tinted,
                        (self.margin_left, baseline - scaled.height),
                        tinted,
                    )

            for tok in rest:
                if tok == " ":
                    x += self._space_width()
                    continue
                tw = self._render_token_width(tok)
                if x + tw > self.page_w - self.margin_right:
                    baseline += self.line_height
                    if baseline > max_y:
                        current = self._new_page()
                        pages.append(current)
                        baseline = self.margin_top + self.glyph_height
                    x = x_start
                x = self._paste_token(current, x, baseline, tok)

            baseline += self.line_height
            if baseline > max_y:
                current = self._new_page()
                pages.append(current)
                baseline = self.margin_top + self.glyph_height

        # Falls die letzte Seite leer blieb, entfernen.
        if len(pages) > 1 and baseline == self.margin_top + self.glyph_height:
            pages.pop()
        return pages


def render_text(
    text: str,
    engine: GlyphEngine,
    options: Optional[RenderOptions] = None,
) -> List[Image.Image]:
    renderer = HandwritingRenderer(engine, options or RenderOptions())
    return renderer.render(text)
