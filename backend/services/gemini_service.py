"""Google Gemini: Bildanalyse für den Hefter."""
from __future__ import annotations

import io
import logging

from PIL import Image

from .. import config

log = logging.getLogger(__name__)


class GeminiError(Exception):
    pass


def analyze_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Bild analysieren und Inhalt strukturiert als Text zurückgeben."""
    key = (config.GEMINI_API_KEY or "").strip()
    if not key:
        raise GeminiError(
            "Kein Gemini API-Key konfiguriert. Bitte GEMINI_API_KEY auf Render hinterlegen."
        )

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise GeminiError("google-generativeai nicht installiert.") from exc

    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    img = Image.open(io.BytesIO(image_bytes))

    prompt = (
        "Analysiere dieses Bild genau. "
        "Extrahiere den gesamten sichtbaren Text vollständig und korrekt. "
        "Beschreibe Diagramme, Tabellen, Formeln und wichtige visuelle Elemente. "
        "Strukturiere den Inhalt mit Überschriften und Stichpunkten. "
        "Antworte auf Deutsch. Gib NUR den extrahierten Inhalt zurück, keine Kommentare."
    )

    try:
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as exc:
        raise GeminiError(f"Bildanalyse fehlgeschlagen: {exc}") from exc
