"""Automatische Hefterblatt-Erstellung.

Extrahierte Inhalte werden strukturiert:
* Hauptthema (Titel) wird aus den häufigsten Substantiven / längster Zeile
  abgeleitet, oder aus einem optionalen Hinweis übernommen.
* Unterüberschriften und Abschnitte werden aus Absätzen und Doppelpunkt-
  Strukturen abgeleitet.
* Stichpunkte und Merkkästen werden generiert.

Die Heuristik funktioniert vollständig offline.  Falls ``HEFTERPRO_AI=1``
gesetzt ist, wird zusätzlich eine Modellschnittstelle aufgerufen — diese
Schnittstelle ist optional und fällt bei Fehlern auf die Heuristik zurück.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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


# ---------------------------------------------------------------------------
# Heuristische Strukturierung
# ---------------------------------------------------------------------------


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sentences(text: str) -> List[str]:
    # Simple Satzsplit-Heuristik.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", text)
    return [p.strip() for p in parts if p.strip()]


def _candidate_title(text: str, hint: str) -> str:
    if hint.strip():
        return hint.strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return "Hefterblatt"
    # Kandidaten: erste kurze Zeile in Title-/Upper-Case.
    for l in lines[:5]:
        if 3 <= len(l) <= 80 and l[0].isupper():
            # Heuristik: wenig Interpunktion → Überschrift.
            if sum(c in ".?!," for c in l) <= 1:
                return l.rstrip(":")
    # Fallback: häufigstes Wort.
    counts = Counter(
        w.lower()
        for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", text)
        if w.lower() not in STOPWORDS
    )
    if counts:
        return counts.most_common(1)[0][0].capitalize()
    return "Hefterblatt"


def _detect_headings(text: str) -> List[tuple[str, str]]:
    """Grobe Erkennung von Abschnitten.

    Gibt eine Liste von (Überschrift, Abschnittstext)-Tupeln zurück.
    """
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    sections: List[tuple[str, str]] = []
    for block in blocks:
        lines = block.split("\n")
        first = lines[0].strip()
        rest = "\n".join(lines[1:]).strip()

        # Heuristik: erste Zeile ist kurz & endet nicht mit Punkt → Überschrift.
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
    # Bereits bestehende Bullets erkennen.
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
    # Kurze/prägnante Sätze bevorzugen.
    sentences.sort(key=lambda s: abs(len(s) - 80))
    bullets = []
    for s in sentences:
        if 15 <= len(s) <= 140:
            bullets.append(s.rstrip("."))
        if len(bullets) >= max_items:
            break
    return bullets


def _pick_callout(text: str) -> Optional[str]:
    """Sucht einen prägnanten Satz für einen Merkkasten."""
    sentences = _split_sentences(text)
    keywords = ("wichtig", "merke", "zentral", "grundsatz", "regel", "definition",
                "achtung", "beachte")
    for s in sentences:
        low = s.lower()
        if any(k in low for k in keywords):
            return s.strip()
    # Fallback: kürzester Satz mit > 20 Zeichen.
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

    # Einführung aus erstem Block ohne Überschrift.
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
            # Wenn Bullets existieren, Fließtext kürzen.
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

    # Optionaler KI-Hook.
    if config.AI_ENABLED:
        try:
            from .ai_structuring import enhance  # optional module
            enhanced = enhance(title, sections)
            if enhanced:
                title = enhanced.get("title", title)
                if enhanced.get("sections"):
                    sections = [HefterSection(**s) for s in enhanced["sections"]]
        except Exception as exc:  # pragma: no cover - optional path
            log.info("KI-Strukturierung übersprungen: %s", exc)

    return HefterDocument(title=title, subtitle=subtitle, sections=sections)


# ---------------------------------------------------------------------------
# Rendering: Dokument → Blatt-Bilder
# ---------------------------------------------------------------------------


@dataclass
class HefterRenderOptions:
    profile_id: str = "default"
    accent: str = "#1a2a6c"
    sheet_type: str = "blanko"


def _font(size: int) -> ImageFont.ImageFont:
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
    return lines


def render_hefter(
    doc: HefterDocument,
    options: HefterRenderOptions,
    engine_render_fn=None,
) -> List[Image.Image]:
    """Rendert das Hefterdokument zu einer Liste A4-Seiten.

    Wird ``engine_render_fn`` übergeben (z.B. die Handschrift-Engine), werden
    Fließtext-Blöcke in Handschrift gerendert und als Bilder eingefügt.
    Ansonsten wird eine saubere Druckschrift genutzt.
    """
    from .rendering import make_sheet_background  # late import

    pages: List[Image.Image] = []
    page = make_sheet_background(options.sheet_type)
    draw = ImageDraw.Draw(page)

    margin = config.mm_to_px(20)
    max_x = config.PAGE_WIDTH_PX - margin
    y = margin

    accent = _hex_to_rgb(options.accent)

    # Titel.
    title_font = _font(config.mm_to_px(10))
    subtitle_font = _font(config.mm_to_px(4.5))
    heading_font = _font(config.mm_to_px(6.5))
    body_font = _font(config.mm_to_px(4.6))
    small_font = _font(config.mm_to_px(4))

    draw.text((margin, y), doc.title, fill=accent, font=title_font)
    y += config.mm_to_px(13)
    # Akzentlinie.
    draw.rectangle(
        [margin, y, margin + config.mm_to_px(30), y + 3],
        fill=accent,
    )
    y += config.mm_to_px(5)
    if doc.subtitle:
        draw.text((margin, y), doc.subtitle, fill=(110, 110, 120), font=subtitle_font)
        y += config.mm_to_px(7)

    def _ensure_space(needed: int) -> None:
        nonlocal page, draw, y
        if y + needed > config.PAGE_HEIGHT_PX - margin:
            pages.append(page)
            page = make_sheet_background(options.sheet_type)
            draw = ImageDraw.Draw(page)
            y = margin

    for section in doc.sections:
        _ensure_space(config.mm_to_px(20))
        # Überschrift mit kleinem farbigen Punkt.
        draw.ellipse(
            [margin, y + 8, margin + 10, y + 18],
            fill=accent,
        )
        draw.text((margin + 16, y), section.heading, fill=(30, 30, 40), font=heading_font)
        y += config.mm_to_px(10)

        for paragraph in section.body:
            wrapped = _wrap(draw, paragraph, body_font, max_x - margin)
            for line in wrapped:
                _ensure_space(config.mm_to_px(6))
                draw.text((margin, y), line, fill=(40, 40, 50), font=body_font)
                y += config.mm_to_px(6)
            y += config.mm_to_px(2)

        for bullet in section.bullets:
            _ensure_space(config.mm_to_px(6))
            draw.ellipse(
                [margin + 2, y + 6, margin + 8, y + 12],
                fill=accent,
            )
            wrapped = _wrap(draw, bullet, body_font, max_x - margin - config.mm_to_px(6))
            for i, line in enumerate(wrapped):
                _ensure_space(config.mm_to_px(6))
                draw.text(
                    (margin + config.mm_to_px(6), y),
                    line,
                    fill=(40, 40, 50),
                    font=body_font,
                )
                y += config.mm_to_px(6)
            y += config.mm_to_px(1)

        if section.callout:
            _ensure_space(config.mm_to_px(20))
            box_top = y
            wrapped = _wrap(draw, section.callout, small_font, max_x - margin - config.mm_to_px(12))
            box_h = max(config.mm_to_px(14), len(wrapped) * config.mm_to_px(5) + config.mm_to_px(8))
            draw.rounded_rectangle(
                [margin, box_top, max_x, box_top + box_h],
                radius=config.mm_to_px(3),
                fill=(248, 245, 230),
                outline=(220, 200, 150),
                width=2,
            )
            draw.text(
                (margin + config.mm_to_px(4), box_top + config.mm_to_px(2)),
                "Merke",
                fill=(160, 120, 30),
                font=small_font,
            )
            ty = box_top + config.mm_to_px(7)
            for line in wrapped:
                draw.text(
                    (margin + config.mm_to_px(4), ty),
                    line,
                    fill=(60, 50, 20),
                    font=small_font,
                )
                ty += config.mm_to_px(5)
            y = box_top + box_h + config.mm_to_px(5)

        y += config.mm_to_px(4)

    pages.append(page)
    return pages


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore
