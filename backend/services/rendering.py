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
from .charset import get_metrics

log = logging.getLogger(__name__)


@dataclass
class RenderOptions:
    profile_id: str = ""
    sheet_type: str = "liniert"
    ink_color: str = "#000000"
    jitter: float = 0.6
    size_scale: float = 1.0
    thickness: float = 1.0


LINE_STEP_MM = 10.0
TEXT_HEIGHT_MM = 6.5
TOP_MARGIN_MM = 15
LEFT_MARGIN_MM = 15
RIGHT_MARGIN_MM = 12
BOTTOM_MARGIN_MM = 15
HEADER_LINES = 1


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def _compute_baselines(first_baseline: int, line_step: int,
                       page_h: int, bottom_margin: int,
                       descender_space: int) -> List[int]:
    max_y = page_h - bottom_margin - descender_space
    baselines = []
    y = first_baseline
    while y <= max_y:
        baselines.append(y)
        y += line_step
    return baselines


def make_sheet_background(sheet_type: str,
                          baselines: Optional[List[int]] = None) -> Image.Image:
    paper = (255, 255, 255)
    img = Image.new("RGB", (config.PAGE_WIDTH_PX, config.PAGE_HEIGHT_PX), paper)
    draw = ImageDraw.Draw(img)
    w, h = img.size

    if sheet_type == "liniert" and baselines:
        color = (210, 218, 230)
        for y in baselines:
            draw.line([(0, y), (w, y)], fill=color, width=1)
    elif sheet_type == "kariert":
        step = config.mm_to_px(5)
        color = (215, 222, 232)
        for x in range(0, w, step):
            draw.line([(x, 0), (x, h)], fill=color, width=1)
        for y in range(0, h, step):
            draw.line([(0, y), (w, y)], fill=color, width=1)
    return img


class GlyphRenderer:
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

        self.line_step = int(config.mm_to_px(LINE_STEP_MM) * self.size_scale)
        self.glyph_height = int(config.mm_to_px(TEXT_HEIGHT_MM) * self.size_scale)
        self.descender_space = int(self.glyph_height * 0.35)

        self.first_baseline = config.mm_to_px(TOP_MARGIN_MM) + self.glyph_height
        self.baselines = _compute_baselines(
            self.first_baseline, self.line_step,
            self.page_h, self.margin_bottom, self.descender_space,
        )
        self.lines_per_page = len(self.baselines)
        self.first_text_line = HEADER_LINES

        self.bullet_indent = config.mm_to_px(10)
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
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.3))
        glyph.putalpha(alpha)
        return glyph

    def _tint_glyph(self, glyph: Image.Image) -> Image.Image:
        r, g, b = self.color
        solid = Image.new("RGBA", glyph.size, (r, g, b, 255))
        alpha = glyph.split()[-1]
        solid.putalpha(alpha)
        return solid

    def _smooth_glyph(self, glyph: Image.Image) -> Image.Image:
        alpha = glyph.split()[-1]
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.7))
        glyph.putalpha(alpha)
        return glyph

    def _scale_glyph_to(self, glyph: Image.Image, target_h: int) -> Image.Image:
        w, h = glyph.size
        if h <= 0:
            return glyph
        scale = target_h / h
        new_w = max(1, int(round(w * scale)))
        return glyph.resize((new_w, target_h), Image.LANCZOS)

    def _get_glyph(self, ch: str) -> Optional[Tuple[Image.Image, int]]:
        glyph = self.profile.pick(ch, self.rng)
        if glyph is None:
            return None
        scale, top = get_metrics(ch)
        target_h = max(1, int(self.glyph_height * scale))
        above_px = max(1, int(self.glyph_height * top))
        glyph = self._scale_glyph_to(glyph.convert("RGBA"), target_h)
        glyph = self._adjust_thickness(glyph)
        glyph = self._tint_glyph(glyph)
        glyph = self._smooth_glyph(glyph)
        return glyph, above_px

    def _space_width(self) -> int:
        base = int(self.glyph_height * 0.75)
        return base + self.rng.randint(-2, 4)

    def _new_page(self) -> Image.Image:
        return make_sheet_background(self.options.sheet_type, self.baselines)

    def _parse_line(self, line: str) -> Tuple[str, str, int]:
        stripped = line.lstrip()
        indent_chars = len(line) - len(stripped)
        indent_level = indent_chars // 2

        if stripped and stripped[0] in self.BULLET_CHARS:
            return "bullet", stripped[1:].lstrip(), indent_level

        for i in range(len(stripped)):
            if stripped[i].isdigit():
                continue
            if stripped[i] in ".)" and i > 0:
                return "numbered", stripped[:i + 1] + " " + stripped[i + 1:].lstrip(), indent_level
            break

        return "text", line, 0

    def _draw_bullet(self, page: Image.Image, baseline: int, indent: int = 0) -> None:
        draw = ImageDraw.Draw(page)
        r = max(3, int(self.glyph_height * 0.14))
        bx = self.margin_left + indent + int(config.mm_to_px(4))
        by = baseline - int(self.glyph_height * 0.30)
        draw.ellipse([bx - r, by - r, bx + r, by + r], fill=self.color)

    def _measure_word(self, word: str) -> Tuple[List[Tuple[Image.Image, int]], int]:
        glyphs = []
        for ch in word:
            result = self._get_glyph(ch)
            if result is not None:
                glyphs.append(result)
        w = 0
        for i_g, (g, _) in enumerate(glyphs):
            w += g.size[0]
            if i_g < len(glyphs) - 1:
                w += int(g.size[0] * -0.08)
        return glyphs, w

    def _lines_remaining(self, line_idx: int) -> int:
        return self.lines_per_page - (line_idx % self.lines_per_page)

    def render(self, text: str) -> Tuple[List[Image.Image], List[dict]]:
        text = text.strip("\n")
        if not text:
            return [self._new_page()], []

        pages: List[Image.Image] = [self._new_page()]
        word_map: List[dict] = []
        line_idx = self.first_text_line
        is_first_page = True

        def baseline():
            return self.baselines[line_idx % self.lines_per_page]

        def new_page():
            nonlocal line_idx, is_first_page
            remainder = self.lines_per_page - (line_idx % self.lines_per_page)
            line_idx += remainder
            pages.append(self._new_page())
            is_first_page = False

        def advance():
            nonlocal line_idx
            line_idx += 1
            if line_idx % self.lines_per_page == 0:
                new_page()

        paragraphs = text.replace("\r\n", "\n").split("\n")

        for para_i, raw_line in enumerate(paragraphs):
            if not raw_line.strip():
                advance()
                continue

            line_type, content, indent_level = self._parse_line(raw_line)
            extra_indent = self.bullet_indent * indent_level
            if line_type == "bullet":
                indent = self.bullet_indent + extra_indent
                x_start = self.margin_left + indent
            elif line_type == "numbered":
                indent = self.bullet_indent + extra_indent
                x_start = self.margin_left + extra_indent
            else:
                indent = 0
                x_start = self.margin_left

            words = content.split(" ")
            usable_w = self.page_w - self.margin_right - x_start

            render_lines: List[List[Tuple[List[Tuple[Image.Image, int]], int, str]]] = [[]]
            cur_x = 0
            for word in words:
                if not word:
                    cur_x += self._space_width()
                    continue
                glyphs, word_w = self._measure_word(word)
                if not glyphs:
                    continue
                space = 0 if cur_x == 0 else self._space_width()
                if cur_x + space + word_w > usable_w and cur_x > 0:
                    render_lines.append([])
                    cur_x = 0
                    space = 0
                render_lines[-1].append((glyphs, space, word))
                cur_x += space + word_w

            lines_needed = len(render_lines)
            lines_left = self._lines_remaining(line_idx)

            if lines_needed > lines_left and lines_left < self.lines_per_page - self.first_text_line:
                new_page()

            for rl_i, rl in enumerate(render_lines):
                bl = baseline()

                if rl_i == 0 and line_type == "bullet":
                    self._draw_bullet(pages[-1], bl, extra_indent)

                line_dy = int(self.rng.uniform(-0.8, 0.8) * self.jitter)
                x = x_start

                for glyphs, space, word_text in rl:
                    x += space
                    word_start_x = x
                    for g, above_px in glyphs:
                        dy = int(self.rng.uniform(-0.5, 0.5) * self.jitter)
                        paste_y = bl - above_px + line_dy + dy
                        pages[-1].paste(g, (x, max(0, paste_y)), g)
                        kerning = int(g.size[0] * self.rng.uniform(-0.15, -0.03))
                        x += g.size[0] + kerning
                    if glyphs:
                        word_map.append({
                            "text": word_text,
                            "page": len(pages) - 1,
                            "x": word_start_x,
                            "y": bl - self.glyph_height,
                            "w": max(1, x - word_start_x),
                            "h": self.glyph_height + self.descender_space,
                        })

                if rl_i < lines_needed - 1:
                    advance()

            advance()

        return pages, word_map


def render_text(
    text: str,
    profile_id: str,
    options: Optional[RenderOptions] = None,
) -> Tuple[List[Image.Image], List[dict]]:
    opts = options or RenderOptions(profile_id=profile_id)

    glyph_profile = font_lib.get_glyph_profile(profile_id)
    if glyph_profile is None or glyph_profile.glyph_count == 0:
        raise ValueError("Kein gültiges Profil gefunden. Bitte erstelle zuerst ein Handschrift-Profil.")

    return GlyphRenderer(glyph_profile, opts).render(text)


def apply_highlights(
    pages: List[Image.Image],
    highlights: List[dict],
    word_map: List[dict],
) -> List[Image.Image]:
    import numpy as np
    from PIL import ImageChops

    by_page: dict = {}
    for h in highlights:
        idx = h.get("word_index", -1)
        if idx < 0 or idx >= len(word_map):
            continue
        wb = word_map[idx]
        color = h.get("color", "#FFFF00")
        mode = h.get("mode", "marker")
        by_page.setdefault(wb["page"], []).append((idx, wb, color, mode))

    result: List[Image.Image] = []
    for i, page in enumerate(pages):
        if i not in by_page:
            result.append(page.copy())
            continue

        items = by_page[i]
        markers = [(idx, wb, c) for idx, wb, c, m in items if m == "marker"]
        texts = [(idx, wb, c) for idx, wb, c, m in items if m == "text"]

        out = page.copy()

        if markers:
            by_line: dict = {}
            for idx, wb, color in markers:
                by_line.setdefault((wb["y"], color), []).append((idx, wb))
            hl_layer = Image.new("RGB", out.size, (255, 255, 255))
            draw = ImageDraw.Draw(hl_layer)
            for (_y, color), group in by_line.items():
                group.sort(key=lambda g: g[0])
                rects = [dict(group[0][1])]
                for j in range(1, len(group)):
                    cur = rects[-1]
                    nxt = group[j][1]
                    if group[j][0] == group[j - 1][0] + 1:
                        cur["w"] = nxt["x"] + nxt["w"] - cur["x"]
                    else:
                        rects.append(dict(nxt))
                r, g, b = _hex_to_rgb(color)
                strength = 0.35
                pastel = (
                    int(255 - (255 - r) * strength),
                    int(255 - (255 - g) * strength),
                    int(255 - (255 - b) * strength),
                )
                pad = 4
                for rc in rects:
                    draw.rounded_rectangle(
                        [rc["x"] - pad, rc["y"] - pad,
                         rc["x"] + rc["w"] + pad, rc["y"] + rc["h"] + pad],
                        radius=6, fill=pastel,
                    )
            out = ImageChops.multiply(out, hl_layer)

        if texts:
            arr = np.array(out, dtype=np.float32)
            h_px, w_px = arr.shape[:2]
            for _idx, wb, color in texts:
                r, g, b = _hex_to_rgb(color)
                x1 = max(0, wb["x"])
                y1 = max(0, wb["y"])
                x2 = min(w_px, wb["x"] + wb["w"])
                y2 = min(h_px, wb["y"] + wb["h"])
                region = arr[y1:y2, x1:x2]
                gray = region.mean(axis=2, keepdims=True)
                t = np.clip((200.0 - gray) / 100.0, 0.0, 1.0)
                target = np.array([r, g, b], dtype=np.float32).reshape(1, 1, 3)
                arr[y1:y2, x1:x2] = region * (1.0 - t) + target * t
            out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        result.append(out)
    return result
