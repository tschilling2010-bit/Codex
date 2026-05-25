"""Google Gemini: Bildanalyse via REST API (v1) — kein SDK benötigt."""
from __future__ import annotations

import base64
import io
import logging

import httpx
from PIL import Image

from .. import config

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"


class GeminiError(Exception):
    pass


def analyze_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Bild analysieren und Inhalt strukturiert als Text zurückgeben."""
    key = (config.GEMINI_API_KEY or "").strip()
    if not key:
        raise GeminiError(
            "Kein Gemini API-Key konfiguriert. Bitte GEMINI_API_KEY auf Render hinterlegen."
        )

    # Auf max. 1024px verkleinern, immer als JPEG senden
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > 1024:
        img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Analysiere dieses Bild genau. "
                            "Extrahiere den gesamten sichtbaren Text vollstaendig und korrekt. "
                            "Beschreibe Diagramme, Tabellen, Formeln und wichtige visuelle Elemente. "
                            "Strukturiere den Inhalt mit Ueberschriften und Stichpunkten. "
                            "Antworte auf Deutsch. Gib NUR den extrahierten Inhalt zurueck, "
                            "keine Erklaerungen oder Kommentare."
                        )
                    },
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": img_b64,
                        }
                    },
                ]
            }
        ]
    }

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            res = client.post(_API_URL, params={"key": key}, json=payload)
    except httpx.HTTPError as exc:
        raise GeminiError(f"Verbindung zu Gemini fehlgeschlagen: {exc}") from exc

    if res.status_code != 200:
        try:
            err = res.json().get("error", {}).get("message") or res.text
        except Exception:
            err = res.text
        raise GeminiError(f"Gemini Fehler ({res.status_code}): {err}")

    data = res.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise GeminiError("Unerwartete Antwort von Gemini.") from exc
