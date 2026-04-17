"""Text → Handschrift-Rendering auf A4.

Unterstützt zwei Modi:
- TTF-Fonts (eingebaute Profile)
- Eigene Glyph-Bilder (vom Nutzer per Template erstellt)
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .. import config
from . import fonts as font_lib

log = logging.getLogger(__name__)


@dataclass
class RenderOptions:
    profile_id: str = "hefterpro-natur"
    sheet_type: str = "liniert"
    ink_color: str = "#16306b"
    jitter: float = 0.6


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


# ---------------------------------------------------------------------------
# TTF-based renderer (built-in profiles)
# ---------------------------------------------------------------------------


class HandwritingRenderer:
    def __init__(self, profile: font_lib.FontProfile, options: RenderOptions):
        self.profile = profile
        self.options = options
        self.color = _hex_to_rgb(options.ink_color)
        self.jitter = options.jitter

        self.page_w = config.PAGE_WIDTH_PX
        self.page_h = config.PAGE_HEIGHT_PX
        self.margin_left = config.mm_to_px(LEFT_MARGIN_MM)
        self.margin_right = config.mm_to_px(RIGHT_MARGIN_MM)
        self.margin_bottom = config.mm_to_px(BOTTOM_MARGIN_MM)
        self.first_baseline = config.mm_to_px(TOP_BASELINE_MM)
        self.line_step = config.mm_to_px(LINE_STEP_MM)

        base_px = config.mm_to_px(TEXT_HEIGHT_MM)
        self.font_size = int(base_px * 1.55)
        self.fonts = profile.load_fonts(self.font_size)
        self.fonts_alt = profile.load_fonts(int(self.font_size * 0.97))
        self.fonts_alt2 = profile.load_fonts(int(self.font_size * 1.03))
        self.rng = random.Random()

    def _lines(self, text: str) -> List[List[str]]:
        lines: List[List[str]] = []
        for raw in text.replace("\r\n", "\n").split("\n"):
            tokens: List[str] = []
            buf = ""
            for ch in raw:
                if ch.isspace():
                    if buf:
                        tokens.append(buf); buf = ""
                    tokens.append(" ")
                else:
                    buf += ch
            if buf:
                tokens.append(buf)
            lines.append(tokens)
        return lines

    def _is_bullet(self, tokens: List[str]) -> bool:
        return bool(tokens) and tokens[0] in ("-", "*", "•", "·")

    def _word_font(self) -> ImageFont.FreeTypeFont:
        pool = self.rng.choices(
            [self.fonts, self.fonts_alt, self.fonts_alt2],
            weights=[6, 1, 1],
        )[0]
        if not pool:
            return ImageFont.load_default()
        if len(pool) == 1:
            return pool[0]
        return self.rng.choices(pool, weights=[5] + [1] * (len(pool) - 1))[0]

    def _measure_word(self, word: str, font: ImageFont.FreeTypeFont) -> int:
        bbox = font.getbbox(word)
        return bbox[2] - bbox[0]

    def _space_width(self) -> int:
        return int(self.font_size * 0.27) + self.rng.randint(-2, 3)

    def _draw_word(self, draw, x, baseline, word, font) -> int:
        for ch in word:
            bbox = font.getbbox(ch)
            w_ch = bbox[2] - bbox[0]
            ascent = -bbox[1]
            dy = int(self.rng.uniform(-0.6, 0.6) * self.jitter)
            draw.text(
                (x - bbox[0], baseline - ascent + dy),
                ch, font=font, fill=self.color,
            )
            x += w_ch + max(-1, int(self.rng.uniform(-0.4, 0.6) * self.jitter))
        return x

    def _new_page(self) -> Image.Image:
        return make_sheet_background(self.options.sheet_type)

    def render(self, text: str) -> List[Image.Image]:
        text = text.strip("\n")
        lines = self._lines(text) if text else [[]]
        pages: List[Image.Image] = [self._new_page()]
        draw = ImageDraw.Draw(pages[-1])
        baseline = self.first_baseline
        max_y = self.page_h - self.margin_bottom

        def advance():
            nonlocal baseline, draw
            baseline += self.line_step
            if baseline > max_y:
                pages.append(self._new_page())
                draw = ImageDraw.Draw(pages[-1])
                baseline = self.first_baseline

        for tokens in lines:
            if not tokens:
                advance()
                continue
            bullet = self._is_bullet(tokens)
            if bullet:
                tokens = tokens[1:]
                while tokens and tokens[0] == " ":
                    tokens.pop(0)
                indent = config.mm_to_px(10)
            else:
                indent = 0

            x_start = self.margin_left + indent
            x = x_start

            if bullet:
                r = int(self.font_size * 0.12)
                bx = self.margin_left + int(config.mm_to_px(2))
                by = baseline - int(config.mm_to_px(2))
                draw.ellipse([bx - r, by - r, bx + r, by + r], fill=self.color)

            line_baseline = baseline + int(self.rng.uniform(-0.8, 0.8) * self.jitter)
            pending_space = False

            for tok in tokens:
                if tok == " ":
                    pending_space = True
                    continue
                font = self._word_font()
                w = self._measure_word(tok, font)
                space = self._space_width() if pending_space else 0
                if x + space + w > self.page_w - self.margin_right:
                    advance()
                    line_baseline = baseline + int(self.rng.uniform(-0.8, 0.8) * self.jitter)
                    if baseline == self.first_baseline and len(pages) > 1:
                        draw = ImageDraw.Draw(pages[-1])
                    x = x_start
                    pending_space = False
                    space = 0
                if pending_space:
                    x += space
                    pending_space = False
                x = self._draw_word(draw, x, line_baseline, tok, font)

            advance()
            if baseline == self.first_baseline and len(pages) > 1:
                draw = ImageDraw.Draw(pages[-1])

        return pages


# ---------------------------------------------------------------------------
# Glyph-based renderer (user-created profiles)
# ---------------------------------------------------------------------------


class GlyphRenderer:
    """Renders text using extracted glyph images from a user profile."""

    def __init__(self, profile: font_lib.GlyphProfile, options: RenderOptions):
        self.profile = profile
        self.options = options
        self.color = _hex_to_rgb(options.ink_color)
        self.jitter = options.jitter

        self.page_w = config.PAGE_WIDTH_PX
        self.page_h = config.PAGE_HEIGHT_PX
        self.margin_left = config.mm_to_px(LEFT_MARGIN_MM)
        self.margin_right = config.mm_to_px(RIGHT_MARGIN_MM)
        self.margin_bottom = config.mm_to_px(BOTTOM_MARGIN_MM)
        self.first_baseline = config.mm_to_px(TOP_BASELINE_MM)
        self.line_step = config.mm_to_px(LINE_STEP_MM)

        self.glyph_height = config.mm_to_px(TEXT_HEIGHT_MM)
        self.rng = random.Random()

    def _tint_glyph(self, glyph: Image.Image) -> Image.Image:
        """Recolor a black glyph to the chosen ink color."""
        r, g, b = self.color
        tinted = Image.new("RGBA", glyph.size, (0, 0, 0, 0))
        px_src = glyph.load()
        px_dst = tinted.load()
        w, h = glyph.size
        for y in range(h):
            for x in range(w):
                _, _, _, a = px_src[x, y]
                if a > 0:
                    px_dst[x, y] = (r, g, b, a)
        return tinted

    def _scale_glyph(self, glyph: Image.Image) -> Image.Image:
        """Scale glyph to fit the target line height."""
        w, h = glyph.size
        if h <= 0:
            return glyph
        scale = self.glyph_height / h
        new_w = max(1, int(w * scale))
        return glyph.resize((new_w, self.glyph_height), Image.LANCZOS)

    def _get_glyph(self, ch: str) -> Optional[Image.Image]:
        glyph = self.profile.pick(ch, self.rng)
        if glyph is None:
            return None
        glyph = self._scale_glyph(glyph)
        glyph = self._tint_glyph(glyph)
        return glyph

    def _space_width(self) -> int:
        return int(self.glyph_height * 0.45) + self.rng.randint(-1, 2)

    def _new_page(self) -> Image.Image:
        return make_sheet_background(self.options.sheet_type)

    def render(self, text: str) -> List[Image.Image]:
        text = text.strip("\n")
        if not text:
            return [self._new_page()]

        pages: List[Image.Image] = [self._new_page()]
        baseline = self.first_baseline
        max_y = self.page_h - self.margin_bottom
        x = self.margin_left

        def advance():
            nonlocal baseline, x
            baseline += self.line_step
            x = self.margin_left
            if baseline > max_y:
                pages.append(self._new_page())
                baseline = self.first_baseline

        for raw_line in text.replace("\r\n", "\n").split("\n"):
            if not raw_line.strip():
                advance()
                continue

            x = self.margin_left
            line_dy = int(self.rng.uniform(-0.8, 0.8) * self.jitter)

            for ch in raw_line:
                if ch == " ":
                    x += self._space_width()
                    continue

                glyph = self._get_glyph(ch)
                if glyph is None:
                    x += int(self.glyph_height * 0.5)
                    continue

                gw = glyph.size[0]

                if x + gw > self.page_w - self.margin_right:
                    advance()
                    line_dy = int(self.rng.uniform(-0.8, 0.8) * self.jitter)

                dy = int(self.rng.uniform(-0.5, 0.5) * self.jitter)
                paste_y = baseline - self.glyph_height + line_dy + dy

                pages[-1].paste(glyph, (x, paste_y), glyph)

                kerning = max(-1, int(self.rng.uniform(-0.3, 0.5) * self.jitter))
                x += gw + kerning

            advance()

        return pages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_text(
    text: str,
    profile_id: str = "hefterpro-natur",
    options: Optional[RenderOptions] = None,
) -> List[Image.Image]:
    opts = options or RenderOptions(profile_id=profile_id)

    # Check if this is a user glyph profile
    if font_lib.is_glyph_profile(profile_id):
        glyph_profile = font_lib.get_glyph_profile(profile_id)
        if glyph_profile and glyph_profile.glyph_count > 0:
            return GlyphRenderer(glyph_profile, opts).render(text)

    # Fall back to TTF font profile
    profile = font_lib.get_profile(profile_id) or font_lib.get_profile("hefterpro-natur")
    return HandwritingRenderer(profile, opts).render(text)
