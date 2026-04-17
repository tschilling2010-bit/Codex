"""Text → Handschrift-Rendering auf A4.

Nutzt echte Handschrift-Fonts (Patrick Hand, Architects Daughter,
Just Another Hand, Kalam) und wechselt subtil zwischen ihnen, damit der
Text natürlich wirkt.  Der Baseline-Rhythmus rastet sanft auf den Linien
eines linierten Blattes ein.
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
    sheet_type: str = "liniert"  # liniert, kariert, blanko
    ink_color: str = "#16306b"
    jitter: float = 0.6


# Konstante Blatt-Geometrie — passt zu den Hintergrund-Linien.
LINE_STEP_MM = 10.0          # Abstand zwischen zwei Linien
TEXT_HEIGHT_MM = 6.5         # ungefähre Großbuchstabenhöhe
TOP_BASELINE_MM = 35         # y-Position der ersten Grundlinie
LEFT_MARGIN_MM = 33          # hinter der roten Randlinie
RIGHT_MARGIN_MM = 18
BOTTOM_MARGIN_MM = 22
INK_DEFAULT = (22, 48, 107)


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


# ---------------------------------------------------------------------------
# Blatt-Hintergrund
# ---------------------------------------------------------------------------


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
        # Rote Randlinie
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
# Renderer
# ---------------------------------------------------------------------------


class HandwritingRenderer:
    def __init__(self, profile: font_lib.FontProfile, options: RenderOptions):
        self.profile = profile
        self.options = options
        self.color = _hex_to_rgb(options.ink_color)
        self.jitter = options.jitter

        # Seitengeometrie
        self.page_w = config.PAGE_WIDTH_PX
        self.page_h = config.PAGE_HEIGHT_PX
        self.margin_left = config.mm_to_px(LEFT_MARGIN_MM)
        self.margin_right = config.mm_to_px(RIGHT_MARGIN_MM)
        self.margin_bottom = config.mm_to_px(BOTTOM_MARGIN_MM)
        self.first_baseline = config.mm_to_px(TOP_BASELINE_MM)
        self.line_step = config.mm_to_px(LINE_STEP_MM)

        # Fonts: Basisgröße so wählen, dass Text auf Linien passt.
        base_px = config.mm_to_px(TEXT_HEIGHT_MM)
        self.font_size = int(base_px * 1.55)
        self.fonts = profile.load_fonts(self.font_size)
        self.fonts_alt = profile.load_fonts(int(self.font_size * 0.97))
        self.fonts_alt2 = profile.load_fonts(int(self.font_size * 1.03))
        self.rng = random.Random()

    # ---------------- Tokenizer ----------------

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

    # ---------------- Drawing ----------------

    def _word_font(self) -> ImageFont.FreeTypeFont:
        """Eine konsistente Schrift für ein ganzes Wort."""
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

    def _draw_word(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        baseline: int,
        word: str,
        font: ImageFont.FreeTypeFont,
    ) -> int:
        """Zeichnet ein Wort am gewünschten Baseline-Punkt."""
        # Pro Zeichen nur sehr dezentes Jitter: kleine Vertikal-Abweichung,
        # minimale Horizontal-Variation.
        for ch in word:
            bbox = font.getbbox(ch)
            w_ch = bbox[2] - bbox[0]
            ascent = -bbox[1]
            dy = int(self.rng.uniform(-0.6, 0.6) * self.jitter)
            draw.text(
                (x - bbox[0], baseline - ascent + dy),
                ch,
                font=font,
                fill=self.color,
            )
            # Leichte Kerning-Abweichung
            x += w_ch + max(-1, int(self.rng.uniform(-0.4, 0.6) * self.jitter))
        return x

    def _new_page(self) -> Image.Image:
        return make_sheet_background(self.options.sheet_type)

    # ---------------- Main render ----------------

    def render(self, text: str) -> List[Image.Image]:
        text = text.strip("\n")
        lines = self._lines(text) if text else [[]]
        pages: List[Image.Image] = [self._new_page()]
        draw = ImageDraw.Draw(pages[-1])
        baseline = self.first_baseline
        max_y = self.page_h - self.margin_bottom

        def advance(new_line: bool = True) -> None:
            nonlocal baseline, draw
            if new_line:
                baseline += self.line_step
            # ganz leicht die Linie verfehlen — aber nur maximal ±1.2px
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
                # Stichpunkt
                r = int(self.font_size * 0.12)
                bx, by = self.margin_left + int(config.mm_to_px(2)), baseline - int(config.mm_to_px(2))
                draw.ellipse([bx - r, by - r, bx + r, by + r], fill=self.color)

            # Baseline der aktuellen Zeile minimal variieren damit der
            # Zeilenrhythmus natürlich wirkt.
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
                    # Umbruch → neue Zeile
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


def render_text(
    text: str,
    profile_id: str = "hefterpro-natur",
    options: Optional[RenderOptions] = None,
) -> List[Image.Image]:
    profile = font_lib.get_profile(profile_id) or font_lib.get_profile("hefterpro-natur")
    opts = options or RenderOptions(profile_id=profile_id)
    return HandwritingRenderer(profile, opts).render(text)
