"""Einlesen hochgeladener Dateien: PDFs, Bilder, Text.

Für PDFs wird der eingebettete Text per ``pypdf`` ausgelesen.  Für Bilder
gibt es keine eingebaute OCR — stattdessen werden die Bildpfade gesammelt,
damit sie im Hefterblatt als Illustration eingebunden werden können.  Wenn
eine Bildbeschriftung/ein Dateiname vorhanden ist, fließt dieser als
Textquelle ein.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from PIL import Image
from pypdf import PdfReader

log = logging.getLogger(__name__)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
PDF_EXT = {".pdf"}
TEXT_EXT = {".txt", ".md"}


@dataclass
class ExtractedContent:
    text: str = ""
    image_paths: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)


def extract_from_pdf(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        log.warning("PDF %s nicht lesbar: %s", path, exc)
        return ""
    parts: List[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts).strip()


def extract_from_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        log.warning("Textdatei %s nicht lesbar: %s", path, exc)
        return ""


def normalize_image(path: Path, max_dim: int = 1200) -> Path:
    """Skaliert Bilder auf eine sinnvolle Größe und konvertiert nach PNG."""
    try:
        img = Image.open(path)
        img.load()
    except Exception as exc:
        log.warning("Bild %s nicht lesbar: %s", path, exc)
        return path
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    out = path.with_suffix(".png")
    img.save(out, "PNG")
    if out != path:
        try:
            path.unlink()
        except OSError:
            pass
    return out


def extract_all(paths: List[Path]) -> ExtractedContent:
    result = ExtractedContent()
    for p in paths:
        ext = p.suffix.lower()
        result.sources.append(p.name)
        if ext in PDF_EXT:
            text = extract_from_pdf(p)
            if text:
                result.text += f"\n\n{text}"
        elif ext in TEXT_EXT:
            result.text += f"\n\n{extract_from_text_file(p)}"
        elif ext in IMAGE_EXT:
            normalized = normalize_image(p)
            result.image_paths.append(str(normalized))
            # Dateiname als sehr grobe Beschreibung nutzen.
            stem = re.sub(r"[-_]+", " ", normalized.stem)
            result.text += f"\n[Bild: {stem}]"
        else:
            log.info("Datei %s wird ignoriert (unbekannter Typ).", p)
    return result
