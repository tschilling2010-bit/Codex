"""OpenAI GPT-4o-mini: Multi-modal analysis via REST API — kein SDK benötigt."""
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
_API_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = "gpt-4o-mini"

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

_SCHEMA_INSTRUCTION = (
    "\n\nGib das Ergebnis als reines JSON zurück (kein Markdown, kein ```json), "
    "exakt in diesem Format:\n"
    '{"text": "<der verarbeitete Inhalt>", '
    '"highlights": ["Begriff1", "Begriff2", "Begriff3"]}\n'
    "highlights: 5–8 der wichtigsten Begriffe/Schlüsselwörter aus dem Text "
    "(einzelne Wörter oder kurze Phrasen, maximal 3 Wörter je Begriff)."
)


class OpenAIError(Exception):
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
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(p.strip() for p in pages if p.strip())
    except Exception as exc:
        log.warning("PDF-Textextraktion fehlgeschlagen: %s", exc)
        return ""


def analyze(
    files: List[bytes],
    filenames: List[str],
    mode: str,
    custom_prompt: Optional[str] = None,
    text_content: Optional[str] = None,
) -> dict:
    """KI-Analyse mit GPT-4o-mini. Gibt {"text": str, "highlight_terms": [...]} zurück."""
    key = (config.OPENAI_API_KEY or "").strip()
    if not key:
        raise OpenAIError("Kein OpenAI API-Key konfiguriert.")

    if mode == "prompt" and not (custom_prompt or "").strip():
        raise OpenAIError("Eigener Prompt ist leer.")

    content_parts: list = []
    has_content = False

    for file_bytes, filename in zip(files, filenames):
        if filename.lower().endswith(".pdf"):
            pdf_text = _extract_pdf_text(file_bytes)
            if len(pdf_text) < 50:
                raise OpenAIError(
                    "Das PDF enthält keinen lesbaren Text (gescannte Seiten?). "
                    "Bitte fotografiere die Seiten und lade die Fotos hoch."
                )
            content_parts.append({"type": "text", "text": f"[Dokument: {filename}]\n{pdf_text}"})
            has_content = True
        else:
            img_b64 = _img_to_b64_jpeg(file_bytes)
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            })
            has_content = True

    if text_content:
        content_parts.append({"type": "text", "text": f"[Text-Quelle]\n{text_content}"})
        has_content = True

    if not has_content:
        if mode == "prompt" and (custom_prompt or "").strip():
            pass  # Der Prompt selbst ist die Aufgabe
        else:
            raise OpenAIError("Keine Inhalte übergeben.")

    if mode == "prompt":
        mode_text = f"Bearbeite folgende Aufgabe: {custom_prompt.strip()}"
    else:
        mode_text = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["transcribe"])

    content_parts.append({"type": "text", "text": mode_text + _SCHEMA_INSTRUCTION})

    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": content_parts}],
        "max_tokens": 4096,
    }

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            res = client.post(
                _API_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
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
        raw = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OpenAIError("Unerwartete Antwort von OpenAI.") from exc

    raw_stripped = raw.strip()
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
        log.warning("OpenAI JSON-Parse fehlgeschlagen, nutze Raw-Text.")
        return {"text": raw_stripped, "highlight_terms": []}
