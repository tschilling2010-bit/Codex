"""OpenAI integration: generate beautifully styled Hefter pages.

Uses GPT-4o (text) to structure raw notes into a clean layout description,
then DALL-E 3 to render the page as an A4 portrait image in the subject's
colour theme and paper style. Falls back to a clear error when no API key
is configured so the rest of the app still works.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Tuple

import httpx
from PIL import Image

from .. import config

log = logging.getLogger(__name__)


class OpenAIError(Exception):
    """Raised when an OpenAI API call fails."""


def _require_key() -> str:
    key = (config.OPENAI_API_KEY or "").strip()
    if not key:
        raise OpenAIError(
            "Kein OpenAI API-Key konfiguriert. Bitte OPENAI_API_KEY auf Render hinterlegen."
        )
    return key


# ---------------------------------------------------------------- Prompting

def _structure_prompt(content: str, subject_name: str, color: str, paper_type: str) -> str:
    """Build the DALL-E prompt for a single Hefter page.

    The prompt encodes the user's strict requirements:
      * A4 portrait orientation
      * Color theme based on the subject color
      * Lined / squared / blank paper background
      * Hand-drawn style with clean sketches and diagrams
      * Highlighted key terms in coloured boxes
      * Don't invent extra content — only structure what was provided
      * Empty space at the bottom is OK; never pad with fabricated material
    """
    paper_text = {
        "liniert": "lined notebook paper background with horizontal ruled lines",
        "kariert": "squared notebook paper background with light grid (5mm)",
        "blanko": "clean white notebook paper background, no lines or grid",
    }.get(paper_type, "lined notebook paper background")

    instructions = f"""
A single beautifully designed German school notebook page (Hefterseite) about \"{subject_name}\".

Style:
- A4 portrait orientation, clean educational layout
- {paper_text}
- Main accent color: {color} — use it for headlines, highlight boxes, underlines, simple illustrations and decorative dividers
- Hand-drawn, modern educational style (think: high quality school summary sheet)
- Top: large hand-lettered title underlined in {color}
- Body: clearly structured sections, bullet lists, definition boxes, small relevant illustrations or diagrams as needed
- Highlight key terms in soft coloured rounded boxes (in the accent colour, low saturation)
- A small \"Begriffe\" / definitions box at the bottom if appropriate
- All text in German, perfectly legible and spelled correctly
- Mathematical/scientific symbols rendered exactly
- Calm, clean, plenty of whitespace — it is OK if the lower part of the page stays empty, do NOT invent extra content to fill space

Use ONLY the content listed below. Do not add facts that aren't there.

Content to structure on the page:
---
{content.strip()}
---
""".strip()
    return instructions


# ---------------------------------------------------------------- API calls

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


def _call_image_api(prompt: str) -> bytes:
    """Call OpenAI Images API and return raw PNG bytes."""
    key = _require_key()
    url = "https://api.openai.com/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1792",  # A4 portrait ratio
        "quality": "hd",
        "response_format": "b64_json",
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            res = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise OpenAIError(f"Verbindung zu OpenAI fehlgeschlagen: {exc}") from exc

    if res.status_code != 200:
        try:
            err = res.json().get("error", {}).get("message") or res.text
        except Exception:
            err = res.text
        raise OpenAIError(f"OpenAI Fehler ({res.status_code}): {err}")

    data = res.json()
    try:
        b64 = data["data"][0]["b64_json"]
    except (KeyError, IndexError) as exc:
        raise OpenAIError("Unerwartete Antwort von OpenAI.") from exc
    return base64.b64decode(b64)


# ---------------------------------------------------------------- Public

def analyze_image(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """Use GPT-4o to analyze an image and extract its content."""
    key = _require_key()
    b64 = base64.b64encode(image_bytes).decode()
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENAI_TEXT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analysiere dieses Bild. Extrahiere den gesamten sichtbaren Text, "
                            "beschreibe Diagramme, Formeln, Tabellen und wichtige visuelle Elemente. "
                            "Gib den Inhalt strukturiert zurueck (Ueberschriften, Stichpunkte, Formeln). "
                            "Antworte auf Deutsch. Gib NUR den extrahierten Inhalt zurueck, "
                            "keine Erklaerungen oder Kommentare."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 3000,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            res = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise OpenAIError(f"Bildanalyse fehlgeschlagen: {exc}") from exc

    if res.status_code != 200:
        try:
            err = res.json().get("error", {}).get("message") or res.text
        except Exception:
            err = res.text
        raise OpenAIError(f"OpenAI Bildanalyse Fehler ({res.status_code}): {err}")

    data = res.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OpenAIError("Unerwartete Antwort bei Bildanalyse.") from exc


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF file using pypdf."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                texts.append(text.strip())
        return "\n\n".join(texts)
    except Exception as exc:
        raise OpenAIError(f"PDF konnte nicht gelesen werden: {exc}") from exc


def generate_hefter_page(
    *,
    content: str,
    subject_name: str,
    color: str,
    paper_type: str,
) -> Tuple[bytes, Image.Image]:
    """Generate one Hefter page. Returns (png_bytes, PIL image)."""
    prompt = _structure_prompt(
        content=content,
        subject_name=subject_name,
        color=color,
        paper_type=paper_type,
    )
    log.info("Generating Hefter page (subject=%s, paper=%s)", subject_name, paper_type)
    raw = _call_image_api(prompt)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return raw, img
