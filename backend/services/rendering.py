"""Text → Handschrift-Rendering auf A4.

Nutzt ausschließlich eigene Glyph-Profile (vom Nutzer per Template erstellt).
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from .. import config
from . import fonts as font_lib

log = logging.getLogger(__name__)


@dataclass
class RenderOptions:
    profile_id: str = ""
    sheet_type: str = "liniert"
    ink_color: str = "#16306b"
    jitter: float = 0.6
    size_scale: float = 1.0
    thickness: float = 1.0


LINE_STEP_MM = 10.0
TEXT_HEIGHT_MM = 6.5
TOP_BASELINE_MM = 35
LEFT_MARGIN_MM = 33
RIGHT_MARGIN_MM = 18
BOTTOM_MARGIN_MM = 22


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def make_sheet_background(sheet_type: str) -> Image.Image:
    paper = (253, 252, 249)
    img = Image.new("RGB", (config.PAGE_WIDTH_PX, config.PAGE_HEIGHT_PX), paper)
    draw = ImageDraw.Draw(img)
    w, h = img.size

    if sheet_type == "liniert":
        top = config.mm_to_px(TOP_BASELINE_MM)
        bottom = h - config.mm_to_px(BOTTOM_MARGIN_MM)
        step = config.mm_to_px(LINE_STEP_MM)
        left = config.mm_to_px(18)
        right = w - config.mm_to_px(12)
        for y in range(top, bottom + 1, step):
            draw.line([(left, y), (right, y)], fill=(201, 217, 235), width=1)
        margin_x = config.mm_to_px(30)
        draw.line(
            [(margin_x, config.mm_to_px(15)), (margin_x, h - config.mm_to_px(15))],
            fill=(228, 148, 153), width=1,
        )
    elif sheet_type == "kariert":
        step = config.mm_to_px(5)
        color = (206, 220, 238)
        pad = config.mm_to_px(12)
        for x in range(pad, w - pad, step):
            draw.line([(x, pad), (x, h - pad)], fill=color, width=1)
        for y in range(pad, h - pad, step):
            draw.line([(pad, y), (w - pad, y)], fill=color, width=1)
    return img


class GlyphRenderer:
    """Renders text using extracted glyph images from a user profile."""

    BULLET_CHARS = {"•", "·", "-", "*", "–"}

    def __init__(self, profile: font_lib.GlyphProfile, options: RenderOptions):
        self.profile = profile
        self.options = options
        self.color = _hex_to_rgb(options.ink_color)
        self.jitter = options.jitter
        self.size_scale = max(0.5, min(2.0, options.size_scale))
        self.thickness = max(0.5, min(2.5, options.thickness))

        self.page_w = config.PAGE_WIDTH_PX
        self.page_h = config.PAGE_HEIGHT_PX
        self.margin_left = config.mm_to_px(LEFT_MARGIN_MM)
        self.margin_right = config.mm_to_px(RIGHT_MARGIN_MM)
        self.margin_bottom = config.mm_to_px(BOTTOM_MARGIN_MM)
        self.first_baseline = config.mm_to_px(TOP_BASELINE_MM)
        self.line_step = int(config.mm_to_px(LINE_STEP_MM) * self.size_scale)

        self.glyph_height = int(config.mm_to_px(TEXT_HEIGHT_MM) * self.size_scale)
        self.rng = random.Random()

    def _adjust_thickness(self, glyph: Image.Image) -> Image.Image:
        if abs(self.thickness - 1.0) < 0.05:
            return glyph
        alpha = glyph.split()[-1]
        radius = abs(self.thickness - 1.0) * 2.5
        size = max(3, int(radius * 2) | 1)
        if self.thickness > 1.0:
            alpha = alpha.filter(ImageFilter.MaxFilter(size))
        else:
            alpha = alpha.filter(ImageFilter.MinFilter(size))
        glyph.putalpha(alpha)
        return glyph

    def _tint_glyph(self, glyph: Image.Image) -> Image.Image:
        r, g, b = self.color
        solid = Image.new("RGBA", glyph.size, (r, g, b, 255))
        alpha = glyph.split()[-1]
        solid.putalpha(alpha)
        return solid

    def _scale_glyph(self, glyph: Image.Image) -> Image.Image:
        w, h = glyph.size
        if h <= 0:
            return glyph
        scale = self.glyph_height / h
        new_w = max(1, int(round(w * scale)))
        return glyph.resize((new_w, self.glyph_height), Image.LANCZOS)

    def _get_glyph(self, ch: str) -> Optional[Image.Image]:
        glyph = self.profile.pick(ch, self.rng)
        if glyph is None:
            return None
        glyph = self._scale_glyph(glyph.convert("RGBA"))
        glyph = self._adjust_thickness(glyph)
        glyph = self._tint_glyph(glyph)
        return glyph

    def _space_width(self) -> int:
        base = int(self.glyph_height * 0.75)
        return base + self.rng.randint(-2, 4)

    def _new_page(self) -> Image.Image:
        return make_sheet_background(self.options.sheet_type)

    def _is_bullet_line(self, line: str) -> Tuple[bool, str]:
        stripped = line.lstrip()
        if stripped and stripped[0] in self.BULLET_CHARS:
            rest = stripped[1:].lstrip()
            return True, rest
        return False, line

    def _draw_bullet(self, page: Image.Image, baseline: int) -> None:
        draw = ImageDraw.Draw(page)
        r = max(2, int(self.glyph_height * 0.08))
        bx = self.margin_left + int(config.mm_to_px(2))
        by = baseline - int(self.glyph_height * 0.35)
        draw.ellipse([bx - r, by - r, bx + r, by + r], fill=self.color)

    def render(self, text: str) -> List[Image.Image]:
        text = text.strip("\n")
        if not text:
            return [self._new_page()]

        pages: List[Image.Image] = [self._new_page()]
        baseline = self.first_baseline
        max_y = self.page_h - self.margin_bottom

        def advance():
            nonlocal baseline
            baseline += self.line_step
            if baseline > max_y:
                pages.append(self._new_page())
                baseline = self.first_baseline

        for raw_line in text.replace("\r\n", "\n").split("\n"):
            if not raw_line.strip():
                advance()
                continue

            is_bullet, content = self._is_bullet_line(raw_line)
            indent = config.mm_to_px(10) if is_bullet else 0
            x_start = self.margin_left + indent

            if is_bullet:
                self._draw_bullet(pages[-1], baseline)

            words = content.split(" ")
            line_dy = int(self.rng.uniform(-0.8, 0.8) * self.jitter)
            x = x_start
            first_word_on_line = True

            for word in words:
                if not word:
                    x += self._space_width()
                    continue

                glyphs = []
                word_w = 0
                for ch in word:
                    g = self._get_glyph(ch)
                    if g is None:
                        glyphs.append(None)
                        word_w += int(self.glyph_height * 0.4)
                    else:
                        glyphs.append(g)
                        word_w += g.size[0]

                space = 0 if first_word_on_line else self._space_width()

                if x + space + word_w > self.page_w - self.margin_right:
                    advance()
                    x = x_start
                    line_dy = int(self.rng.uniform(-0.8, 0.8) * self.jitter)
                    space = 0
                    first_word_on_line = True

                x += space

                for g in glyphs:
                    if g is None:
                        x += int(self.glyph_height * 0.4)
                        continue
                    dy = int(self.rng.uniform(-0.5, 0.5) * self.jitter)
                    paste_y = baseline - self.glyph_height + line_dy + dy
                    pages[-1].paste(g, (x, paste_y), g)
                    kerning = self.rng.randint(-5, -2)
                    x += g.size[0] + kerning

                first_word_on_line = False

            advance()

        return pages


def render_text(
    text: str,
    profile_id: str,
    options: Optional[RenderOptions] = None,
) -> List[Image.Image]:
    opts = options or RenderOptions(profile_id=profile_id)

    glyph_profile = font_lib.get_glyph_profile(profile_id)
    if glyph_profile is None or glyph_profile.glyph_count == 0:
        raise ValueError("Kein gültiges Profil gefunden. Bitte erstelle zuerst ein Handschrift-Profil.")

    return GlyphRenderer(glyph_profile, opts).render(text)
