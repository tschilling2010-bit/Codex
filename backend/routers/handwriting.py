"""API: Handschrift-Rendering & Profile."""
from __future__ import annotations

import io
import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image

from .. import config
from ..models.schemas import (
    ExportRequest,
    ExportResponse,
    ProfileInfo,
    RenderRequest,
    RenderResponse,
)
from ..services import export, projects
from ..services.glyph_engine import (
    GlyphEngine,
    delete_profile,
    ensure_default_profile,
    list_profiles,
)
from ..services.rendering import RenderOptions, render_text
from ..services.template_service import generate_template, process_uploaded_template

log = logging.getLogger(__name__)
router = APIRouter()

# Stelle sicher, dass das Default-Profil existiert.
ensure_default_profile()


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@router.get("/profile/list", response_model=List[ProfileInfo])
def profile_list() -> List[ProfileInfo]:
    return [ProfileInfo(**p) for p in list_profiles()]


@router.delete("/profile/{profile_id}")
def profile_delete(profile_id: str) -> dict:
    if not delete_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profil nicht gefunden oder geschützt.")
    return {"deleted": profile_id}


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------


@router.post("/template/create")
def template_create(name: Optional[str] = Form(None)) -> dict:
    """Erstellt ein neues Template (PDF + Metadaten)."""
    profile_id = uuid.uuid4().hex[:10]
    display_name = (name or f"Eigene Handschrift {profile_id[:4]}").strip()

    template_pdf = config.TEMPLATES_DIR / f"{profile_id}.pdf"
    meta = generate_template(template_pdf)

    # Profil-Stub anlegen, damit der Name schon hinterlegt ist.
    engine = GlyphEngine(profile_id, profile_name=display_name)
    engine.save()

    return {
        "profile_id": profile_id,
        "name": display_name,
        "template_url": f"/files/templates/{template_pdf.name}",
        "meta": meta,
    }


@router.post("/template/upload")
async def template_upload(
    profile_id: str = Form(...),
    files: List[UploadFile] = File(...),
) -> dict:
    meta_path = config.TEMPLATES_DIR / f"{profile_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Unbekanntes Template.")
    meta = json.loads(meta_path.read_text())

    images: List[Image.Image] = []
    for f in files:
        data = await f.read()
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Bild nicht lesbar: {exc}")
        images.append(img.convert("RGB"))

    engine = GlyphEngine(profile_id)
    name = engine.meta.get("name", profile_id)
    result = process_uploaded_template(images, meta, profile_id, name)
    return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@router.post("/render", response_model=RenderResponse)
def render(req: RenderRequest) -> RenderResponse:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text darf nicht leer sein.")
    engine = GlyphEngine(req.profile_id)
    if engine.meta.get("glyph_count", 0) == 0 and req.profile_id != "default":
        raise HTTPException(
            status_code=400,
            detail="Dieses Profil hat noch keine Glyphen. Bitte Template hochladen.",
        )
    options = RenderOptions(
        profile_id=req.profile_id,
        sheet_type=req.sheet_type,
        margin_mm=req.margin_mm,
        line_height_mm=req.line_height_mm,
        glyph_height_mm=req.glyph_height_mm,
        ink_color=req.ink_color,
        jitter=req.jitter,
    )
    pages = render_text(req.text, engine, options)
    title = req.text.strip().split("\n")[0][:40] or "Handschrift"
    project = projects.new_project("handwriting", title)
    preview_urls = projects.save_pages(project, pages)
    return RenderResponse(
        project_id=project.id, pages=len(pages), preview_urls=preview_urls
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _load_pages(project_id: str) -> List[Image.Image]:
    project = projects.load_meta(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    pages: List[Image.Image] = []
    for i in range(1, project.pages + 1):
        path = projects.page_file(project_id, i)
        if path is None:
            continue
        pages.append(Image.open(path))
    if not pages:
        raise HTTPException(status_code=400, detail="Keine Seiten zum Export vorhanden.")
    return pages


@router.post("/export/pdf", response_model=ExportResponse)
def export_pdf_ep(req: ExportRequest) -> ExportResponse:
    project = projects.load_meta(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    pages = _load_pages(req.project_id)
    out = config.EXPORTS_DIR / f"{req.project_id}-handwriting.pdf"
    export.export_pdf(pages, out)
    projects.add_export(project, out)
    return ExportResponse(
        project_id=req.project_id,
        format="pdf",
        url=f"/files/exports/{out.name}",
        filename=out.name,
    )


@router.post("/export/image", response_model=ExportResponse)
def export_image_ep(req: ExportRequest) -> ExportResponse:
    project = projects.load_meta(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    pages = _load_pages(req.project_id)
    tmp_dir = config.EXPORTS_DIR / f"{req.project_id}-img"
    tmp_dir.mkdir(exist_ok=True)
    if req.format == "png":
        paths = export.export_png(pages, tmp_dir, "handwriting")
    elif req.format == "jpg":
        paths = export.export_jpg(pages, tmp_dir, "handwriting")
    else:
        raise HTTPException(status_code=400, detail="Nur png oder jpg erlaubt.")
    # Erste Datei als Rückgabe; alle werden per Projekt zugänglich.
    for p in paths:
        projects.add_export(project, p)
    first = paths[0]
    return ExportResponse(
        project_id=req.project_id,
        format=req.format,
        url=f"/files/exports/{project.id}-{first.name}",
        filename=first.name,
    )
