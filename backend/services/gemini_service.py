"""Google Gemini: Bildanalyse via REST API (v1) — kein SDK benötigt."""
from __future__ import annotations

import base64
import io
import json
import logging
from typing import List, Optional

import httpx
from PIL import Image

from .. import config

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"

_MODE_PROMPTS = {
    "transcribe": (
        "Schreibe alles, was auf diesen Bildern/in diesem Dokument steht, "
        "vollständig und korrekt ab. Behalte die Struktur (Überschriften, "
        "Stichpunkte, Nummerierungen). Antworte nur mit dem abgeschriebenen Inhalt, "
        "keine eigenen Kommentare."
    ),
    "summary": (
        "Fasse den Inhalt dieser Bilder/dieses Dokuments prägnant zusammen. "
        "Nenne die wichtigsten Punkte als strukturierte Stichpunkte. "
        "Antworte auf Deutsch, nur die Zusammenfassung, keine Kommentare."
    ),
}


class GeminiError(Exception):
    pass


def _img_to_b64_jpeg(image_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > 1024:
        img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extrahiert Text aus text-basierten PDFs via pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(p.strip() for p in pages if p.strip())
    except Exception as exc:
        log.warning("PDF-Textextraktion fehlgeschlagen: %s", exc)
        return ""


def _call_gemini(parts: list) -> str:
    key = (config.GEMINI_API_KEY or "").strip()
    if not key:
        raise GeminiError(
            "Kein Gemini API-Key konfiguriert. Bitte GEMINI_API_KEY auf Render hinterlegen."
        )
    payload: dict = {"contents": [{"parts": parts}]}

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


def analyze_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Bild analysieren und Inhalt strukturiert als Text zurückgeben (Legacy)."""
    img_b64 = _img_to_b64_jpeg(image_bytes)
    parts = [
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
        {"inlineData": {"mimeType": "image/jpeg", "data": img_b64}},
    ]
    return _call_gemini(parts)


def analyze(
    files: List[bytes],
    filenames: List[str],
    mode: str,
    custom_prompt: Optional[str] = None,
    text_content: Optional[str] = None,
) -> dict:
    """KI-Analyse: Verarbeitet Bilder/PDFs in einem von 3 Modi.

    Gibt zurück: { "text": str, "highlight_terms": List[str] }
    """
    if mode == "prompt" and not (custom_prompt or "").strip():
        raise GeminiError("Eigener Prompt ist leer.")

    # --- Inhalts-Parts aufbauen ---
    content_parts: list = []
    has_content = False

    for file_bytes, filename in zip(files, filenames):
        name_lower = filename.lower()
        if name_lower.endswith(".pdf"):
            pdf_text = _extract_pdf_text(file_bytes)
            if len(pdf_text) < 50:
                raise GeminiError(
                    "Das PDF enthält keinen lesbaren Text (z.B. gescannte Seiten). "
                    "Bitte fotografiere die Seiten und lade die Fotos hoch."
                )
            content_parts.append({"text": f"[Dokument: {filename}]\n{pdf_text}"})
            has_content = True
        else:
            img_b64 = _img_to_b64_jpeg(file_bytes)
            content_parts.append({"inlineData": {"mimeType": "image/jpeg", "data": img_b64}})
            has_content = True

    # Text-Quelle vom Nutzer
    if text_content:
        content_parts.append({"text": f"[Text-Quelle]\n{text_content}"})
        has_content = True

    if not has_content:
        raise GeminiError("Keine Inhalte übergeben.")

    # --- Modus-Prompt ---
    if mode == "prompt":
        mode_text = (
            f"Bearbeite die folgenden Bilder/Dokumente. Meine Aufgabe: {custom_prompt.strip()}\n"
            "Schreibe das Ergebnis klar und strukturiert. Antworte auf Deutsch."
        )
    else:
        mode_text = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["transcribe"])

    # JSON-Schema-Anforderung anhängen
    schema_instruction = (
        "\n\nGib das Ergebnis als reines JSON zurück (kein Markdown, kein ```json), "
        "exakt in diesem Format:\n"
        '{"text": "<der verarbeitete Inhalt>", '
        '"highlights": ["Begriff1", "Begriff2", "Begriff3"]}\n'
        "highlights: 5–8 der wichtigsten Begriffe/Schlüsselwörter aus dem Text "
        "(einzelne Wörter oder kurze Phrasen, maximal 3 Wörter je Begriff)."
    )

    parts = [{"text": mode_text + schema_instruction}] + content_parts
    raw = _call_gemini(parts)

    # JSON parsen — Gemini hält sich meist daran, aber als Fallback reinen Text nehmen
    raw_stripped = raw.strip()
    # Manchmal umhüllt Gemini die Antwort doch mit ```json ... ```
    if raw_stripped.startswith("```"):
        lines = raw_stripped.split("\n")
        raw_stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        result = json.loads(raw_stripped)
        text = str(result.get("text", "")).strip()
        highlights = [str(h) for h in result.get("highlights", []) if h]
        if not text:
            raise ValueError("text leer")
        return {"text": text, "highlight_terms": highlights[:8]}
    except Exception:
        # Fallback: Antwort direkt als Text verwenden, keine Highlights
        log.warning("Gemini JSON-Parse fehlgeschlagen, nutze Raw-Text.")
        return {"text": raw_stripped, "highlight_terms": []}
