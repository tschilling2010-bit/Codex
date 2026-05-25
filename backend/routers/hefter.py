"""API: Hefter-Fächer (Subjects) mit PIL-generierten Seiten."""
from __future__ import annotations

import io
import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image
from pypdf import PdfReader

from .. import config
from ..models.schemas import (
    HefterPageInfo,
    SubjectCreateRequest,
    SubjectInfo,
    SubjectUpdateRequest,
)
from ..services import export, subjects
from ..services.file_processing import ExtractedContent
from ..services.hefter_generator import HefterRenderOptions, build_document, render_hefter

log = logging.getLogger(__name__)
router = APIRouter()


def _analyze_image_gemini(raw: bytes, mime: str) -> str:
    from ..services.gemini_service import GeminiError, analyze_image
    try:
        return analyze_image(raw, mime)
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _extract_pdf_bytes(raw: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw))
        texts = [p.extract_text() for p in reader.pages if p.extract_text()]
        return "\n\n".join(t.strip() for t in texts)
    except Exception as exc:
        log.warning("PDF konnte nicht gelesen werden: %s", exc)
        return ""


# ----------------------------------------------------------- Subjects ------

@router.get("/subjects", response_model=List[SubjectInfo])
def list_subjects() -> List[SubjectInfo]:
    return subjects.list_subjects()


@router.post("/subjects", response_model=SubjectInfo)
def create_subject(req: SubjectCreateRequest) -> SubjectInfo:
    return subjects.create_subject(
        name=req.name, color=req.color, paper_type=req.paper_type
    )


@router.get("/subjects/{subject_id}", response_model=SubjectInfo)
def get_subject(subject_id: str) -> SubjectInfo:
    sub = subjects.get_subject(subject_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Fach nicht gefunden.")
    return sub


@router.patch("/subjects/{subject_id}", response_model=SubjectInfo)
def update_subject(subject_id: str, req: SubjectUpdateRequest) -> SubjectInfo:
    sub = subjects.get_subject(subject_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Fach nicht gefunden.")
    if req.name is not None:
        sub.name = req.name.strip()
    if req.color is not None:
        sub.color = req.color
    if req.paper_type is not None:
        sub.paper_type = req.paper_type
    subjects.save_subject(sub)
    return subjects.get_subject(subject_id)


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: str) -> dict:
    if not subjects.delete_subject(subject_id):
        raise HTTPException(status_code=404, detail="Fach nicht gefunden.")
    return {"ok": True}


# ---------------------------------------------------------------- Pages ----

@router.post("/subjects/{subject_id}/pages", response_model=HefterPageInfo)
def create_page(
    subject_id: str,
    title: str = Form(""),
    content: str = Form(""),
    files: Optional[List[UploadFile]] = File(default=None),
) -> HefterPageInfo:
    sub = subjects.get_subject(subject_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Fach nicht gefunden.")

    parts: List[str] = []
    if content.strip():
        parts.append(content.strip())

    for f in (files or []):
        raw = f.file.read()
        if not raw:
            continue
        ct = (f.content_type or "").lower()
        fname = (f.filename or "").lower()

        if ct.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            mime = ct if ct.startswith("image/") else "image/jpeg"
            parts.append(_analyze_image_gemini(raw, mime))
        elif ct == "application/pdf" or fname.endswith(".pdf"):
            text = _extract_pdf_bytes(raw)
            if text:
                parts.append(text)

    combined = "\n\n".join(parts)
    if not combined.strip():
        raise HTTPException(
            status_code=400,
            detail="Bitte Inhalt eingeben oder Dateien hochladen.",
        )

    extracted = ExtractedContent(text=combined)
    doc = build_document(extracted, topic_hint=title)
    options = HefterRenderOptions(accent=sub.color, sheet_type=sub.paper_type)
    page_images = render_hefter(doc, options)

    first_page: Optional[HefterPageInfo] = None
    for i, img in enumerate(page_images):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        page_title = title.strip() or sub.name
        if len(page_images) > 1:
            page_title = "{} – {}".format(page_title, i + 1)
        page_info = subjects.add_page(subject_id, page_title, buf.getvalue())
        if first_page is None:
            first_page = page_info

    return first_page


@router.get("/subjects/{subject_id}/pages/{page_id}.png")
def get_page_image(subject_id: str, page_id: str) -> FileResponse:
    path = subjects.page_image_path(subject_id, page_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Seite nicht gefunden.")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.delete("/subjects/{subject_id}/pages/{page_id}")
def delete_page(subject_id: str, page_id: str) -> dict:
    if not subjects.delete_page(subject_id, page_id):
        raise HTTPException(status_code=404, detail="Seite nicht gefunden.")
    return {"ok": True}


# ----------------------------------------------------------------- Export --

@router.get("/subjects/{subject_id}/export/pdf")
def export_subject_pdf(subject_id: str) -> Response:
    sub = subjects.get_subject(subject_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Fach nicht gefunden.")
    paths = subjects.all_page_paths(subject_id)
    if not paths:
        raise HTTPException(status_code=400, detail="Keine Seiten im Fach.")
    images: List[Image.Image] = [Image.open(p).convert("RGB") for p in paths]
    out = config.EXPORTS_DIR / "hefter-{}.pdf".format(subject_id)
    export.export_pdf(images, out)
    safe_name = "".join(c for c in sub.name if c.isalnum() or c in "_-") or "Hefter"
    headers = {
        "Content-Disposition": 'attachment; filename="{}.pdf"'.format(safe_name),
        "Cache-Control": "no-store",
    }
    return Response(content=out.read_bytes(), media_type="application/pdf", headers=headers)


# --------------------------------------------------- Status / API key check

@router.get("/status")
def status() -> dict:
    has_key = bool((config.GEMINI_API_KEY or "").strip())
    return {"ai_configured": has_key, "model": "gemini-1.5-flash"}
