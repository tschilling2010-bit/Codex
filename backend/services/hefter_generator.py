"""Automatische Hefterblatt-Erstellung.

Strukturiert Inhalte zu einem schönen, lernfreundlichen Blatt mit Titel,
Abschnitten, Stichpunkten und Merkkästen.  Funktioniert offline per
Heuristik; mit HEFTERPRO_AI=1 wird die Anthropic API zur Verbesserung
der Strukturierung genutzt.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .. import config
from ..models.schemas import HefterDocument, HefterSection
from .file_processing import ExtractedContent

log = logging.getLogger(__name__)

STOPWORDS = {
    "der", "die", "das", "und", "oder", "aber", "ist", "sind", "war", "waren",
    "ein", "eine", "einen", "eines", "einem", "einer", "dem", "den", "des",
    "mit", "ohne", "für", "gegen", "auf", "unter", "über", "bei", "nach",
    "vor", "von", "zum", "zur", "zu", "in", "im", "an", "am", "wenn", "dann",
    "nicht", "auch", "noch", "nur", "sehr", "wie", "als", "man", "sich",
    "dass", "daß", "weil", "also", "etc", "usw", "z", "b", "zb",
    "the", "a", "an", "of", "and", "or", "to", "is", "are", "was", "were",
    "in", "on", "with", "for", "by", "from", "as", "this", "that",
}


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", text)
    return [p.strip() for p in parts if p.strip()]


def _candidate_title(text: str, hint: str) -> str:
    if hint.strip():
        return hint.strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return "Hefterblatt"
    for l in lines[:5]:
        if 3 <= len(l) <= 80 and l[0].isupper():
            if sum(c in ".?!," for c in l) <= 1:
                return l.rstrip(":")
    counts = Counter(
        w.lower()
        for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", text)
        if w.lower() not in STOPWORDS
    )
    if counts:
        return counts.most_common(1)[0][0].capitalize()
    return "Hefterblatt"


def _detect_headings(text: str) -> List[Tuple[str, str]]:
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    sections: List[Tuple[str, str]] = []
    for block in blocks:
        lines = block.split("\n")
        first = lines[0].strip()
        rest = "\n".join(lines[1:]).strip()
        is_heading = (
            len(first) <= 80
            and not first.endswith(".")
            and (first.endswith(":") or first[0:1].isupper())
            and len(lines) > 1
        )
        if is_heading:
            sections.append((first.rstrip(":"), rest))
        else:
            sections.append(("", block))
    return sections


def _make_bullets(text: str, max_items: int = 6) -> List[str]:
    existing = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith(("-", "•", "*", "·")):
            s = s.lstrip("-•*· ").strip()
            if s:
                existing.append(s)
    if existing:
        return existing[:max_items]
    sentences = _split_sentences(text)
    sentences.sort(key=lambda s: abs(len(s) - 80))
    bullets = []
    for s in sentences:
        if 15 <= len(s) <= 140:
            bullets.append(s.rstrip("."))
        if len(bullets) >= max_items:
            break
    return bullets


def _pick_callout(text: str) -> Optional[str]:
    sentences = _split_sentences(text)
    keywords = ("wichtig", "merke", "zentral", "grundsatz", "regel", "definition",
                "achtung", "beachte")
    for s in sentences:
        low = s.lower()
        if any(k in low for k in keywords):
            return s.strip()
    candidates = [s for s in sentences if 25 <= len(s) <= 140]
    if candidates:
        candidates.sort(key=len)
        return candidates[0]
    return None


def build_document(
    content: ExtractedContent,
    additional_text: str = "",
    topic_hint: str = "",
) -> HefterDocument:
    combined = "\n\n".join(
        p for p in (content.text, additional_text) if p and p.strip()
    )
    combined = _normalize_whitespace(combined)
    if not combined:
        combined = "Keine Inhalte erkannt."

    title = _candidate_title(combined, topic_hint)
    subtitle_parts: List[str] = []
    if content.sources:
        subtitle_parts.append("Quellen: " + ", ".join(content.sources[:4]))
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    sections: List[HefterSection] = []
    raw_sections = _detect_headings(combined)

    intro_added = False
    for heading, body in raw_sections:
        if not heading and not intro_added:
            bullets = _make_bullets(body, max_items=4)
            sections.append(
                HefterSection(
                    heading="Überblick",
                    body=[body] if body and not bullets else [],
                    bullets=bullets,
                    callout=_pick_callout(body),
                )
            )
            intro_added = True
            continue
        if heading:
            bullets = _make_bullets(body)
            body_lines: List[str] = []
            if not bullets and body:
                body_lines = [body]
            sections.append(
                HefterSection(
                    heading=heading,
                    body=body_lines,
                    bullets=bullets,
                    callout=_pick_callout(body),
                )
            )

    if not sections:
        sections.append(
            HefterSection(
                heading="Überblick",
                body=[combined],
                bullets=_make_bullets(combined),
                callout=_pick_callout(combined),
            )
        )

    if config.AI_ENABLED:
        try:
            from .ai_structuring import enhance
            enhanced = enhance(title, sections)
            if enhanced:
                title = enhanced.get("title", title)
                if enhanced.get("sections"):
                    sections = [HefterSection(**s) for s in enhanced["sections"]]
        except Exception as exc:
            log.info("KI-Strukturierung übersprungen: %s", exc)

    return HefterDocument(title=title, subtitle=subtitle, sections=sections)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@dataclass
class HefterRenderOptions:
    accent: str = "#1a2a6c"
    sheet_type: str = "blanko"


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    from . import fonts as font_lib
    fonts_dir = font_lib.FONTS_DIR
    if bold:
        for name in ("PatrickHand-Regular.ttf",):
            try:
                return ImageFont.truetype(str(fonts_dir / name), size)
            except (OSError, IOError):
                continue
    for name in ("Kalam-Regular.ttf", "PatrickHand-Regular.ttf",
                 "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(str(fonts_dir / name), size)
        except (OSError, IOError):
            continue
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def render_hefter(
    doc: HefterDocument,
    options: HefterRenderOptions,
) -> List[Image.Image]:
    from .rendering import make_sheet_background

    pages: List[Image.Image] = []
    page = make_sheet_background(options.sheet_type)
    draw = ImageDraw.Draw(page)

    margin = config.mm_to_px(25)
    max_x = config.PAGE_WIDTH_PX - margin
    content_w = max_x - margin
    y = margin

    accent = _hex_to_rgb(options.accent)
    accent_light = tuple(min(255, c + 180) for c in accent)
    text_dark = (25, 28, 38)
    text_body = (45, 48, 60)
    text_muted = (100, 105, 118)

    title_font = _font(config.mm_to_px(9), bold=True)
    subtitle_font = _font(config.mm_to_px(4))
    heading_font = _font(config.mm_to_px(6), bold=True)
    body_font = _font(config.mm_to_px(4))
    bullet_font = _font(config.mm_to_px(3.8))
    callout_label_font = _font(config.mm_to_px(3.5), bold=True)
    callout_font = _font(config.mm_to_px(3.5))

    def _ensure_space(needed: int) -> None:
        nonlocal page, draw, y
        if y + needed > config.PAGE_HEIGHT_PX - margin:
            pages.append(page)
            page = make_sheet_background(options.sheet_type)
            draw = ImageDraw.Draw(page)
            y = margin

    # --- Title block ---
    title_lines = _wrap(draw, doc.title, title_font, content_w)
    for line in title_lines:
        draw.text((margin, y), line, fill=accent, font=title_font)
        y += config.mm_to_px(11)

    # Accent underline
    draw.rounded_rectangle(
        [margin, y, margin + config.mm_to_px(40), y + config.mm_to_px(1.5)],
        radius=2,
        fill=accent,
    )
    y += config.mm_to_px(6)

    if doc.subtitle:
        draw.text((margin, y), doc.subtitle, fill=text_muted, font=subtitle_font)
        y += config.mm_to_px(8)

    y += config.mm_to_px(4)

    # --- Sections ---
    for sec_idx, section in enumerate(doc.sections):
        _ensure_space(config.mm_to_px(25))

        # Section heading with colored bar
        bar_h = config.mm_to_px(8)
        draw.rounded_rectangle(
            [margin, y, margin + config.mm_to_px(1.5), y + bar_h],
            radius=2,
            fill=accent,
        )
        draw.text(
            (margin + config.mm_to_px(5), y),
            section.heading,
            fill=text_dark,
            font=heading_font,
        )
        y += config.mm_to_px(12)

        # Body paragraphs
        for paragraph in section.body:
            wrapped = _wrap(draw, paragraph, body_font, content_w - config.mm_to_px(5))
            for line in wrapped:
                _ensure_space(config.mm_to_px(6))
                draw.text((margin + config.mm_to_px(5), y), line, fill=text_body, font=body_font)
                y += config.mm_to_px(5.5)
            y += config.mm_to_px(2)

        # Bullets
        if section.bullets:
            indent = margin + config.mm_to_px(5)
            for bullet in section.bullets:
                _ensure_space(config.mm_to_px(7))
                # Filled circle bullet
                r = config.mm_to_px(1)
                bx = indent + r
                by = y + config.mm_to_px(2)
                draw.ellipse([bx - r, by - r, bx + r, by + r], fill=accent)

                wrapped = _wrap(draw, bullet, bullet_font, content_w - config.mm_to_px(12))
                tx = indent + config.mm_to_px(5)
                for line in wrapped:
                    _ensure_space(config.mm_to_px(5.5))
                    draw.text((tx, y), line, fill=text_body, font=bullet_font)
                    y += config.mm_to_px(5)
                y += config.mm_to_px(1.5)

        # Callout box
        if section.callout:
            _ensure_space(config.mm_to_px(22))
            y += config.mm_to_px(3)
            box_left = margin + config.mm_to_px(3)
            box_right = max_x - config.mm_to_px(3)

            wrapped = _wrap(draw, section.callout, callout_font, box_right - box_left - config.mm_to_px(10))
            box_h = max(config.mm_to_px(15), len(wrapped) * config.mm_to_px(5) + config.mm_to_px(13))

            # Background
            draw.rounded_rectangle(
                [box_left, y, box_right, y + box_h],
                radius=config.mm_to_px(3),
                fill=(252, 250, 240),
                outline=(235, 220, 175),
                width=1,
            )
            # Left accent bar inside box
            draw.rounded_rectangle(
                [box_left, y, box_left + config.mm_to_px(1.2), y + box_h],
                radius=config.mm_to_px(3),
                fill=(220, 180, 60),
            )

            # "Merke" label
            draw.text(
                (box_left + config.mm_to_px(5), y + config.mm_to_px(3)),
                "💡 Merke",
                fill=(160, 120, 30),
                font=callout_label_font,
            )
            ty = y + config.mm_to_px(8.5)
            for line in wrapped:
                draw.text(
                    (box_left + config.mm_to_px(5), ty),
                    line,
                    fill=(65, 55, 25),
                    font=callout_font,
                )
                ty += config.mm_to_px(5)
            y += box_h + config.mm_to_px(5)

        y += config.mm_to_px(6)

    pages.append(page)
    return pages
