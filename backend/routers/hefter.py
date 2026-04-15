"""API: Hefterblatt-Erstellung."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import config
from ..models.schemas import (
    ExportRequest,
    ExportResponse,
    HefterDocument,
    HefterProcessResponse,
)
from ..services import export, file_processing, hefter_generator, projects
from ..services.glyph_engine import GlyphEngine

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def hefter_upload(
    files: List[UploadFile] = File(default=[]),
) -> dict:
    """Speichert hochgeladene Dateien und gibt einen Upload-Token zurück.

    Der Token ist eine einfache ID für den gerade laufenden Upload — er wird
    beim nachfolgenden ``/process``-Aufruf referenziert.
    """
    token = uuid.uuid4().hex[:12]
    target = config.UPLOADS_DIR / token
    target.mkdir(parents=True, exist_ok=True)
    saved: List[str] = []
    for f in files:
        safe_name = Path(f.filename or "datei.bin").name
        out = target / safe_name
        with out.open("wb") as fh:
            fh.write(await f.read())
        saved.append(safe_name)
    return {"upload_id": token, "files": saved}


@router.post("/process", response_model=HefterProcessResponse)
def hefter_process(
    upload_id: str = Form(""),
    additional_text: str = Form(""),
    topic_hint: str = Form(""),
    profile_id: str = Form("default"),
) -> HefterProcessResponse:
    paths: List[Path] = []
    if upload_id:
        folder = config.UPLOADS_DIR / upload_id
        if not folder.exists():
            raise HTTPException(status_code=404, detail="Upload nicht gefunden.")
        paths = sorted(p for p in folder.iterdir() if p.is_file())

    content = file_processing.extract_all(paths)
    doc = hefter_generator.build_document(
        content, additional_text=additional_text, topic_hint=topic_hint
    )

    # Hefter in Druckschrift rendern (Handschrift-Engine optional pro Block).
    options = hefter_generator.HefterRenderOptions(
        profile_id=profile_id,
        accent="#1a2a6c",
        sheet_type="blanko",
    )
    pages = hefter_generator.render_hefter(doc, options)

    project = projects.new_project("hefter", doc.title)
    preview_urls = projects.save_pages(project, pages)

    # Dokument als JSON zusätzlich ablegen, damit Preview/Re-Export möglich ist.
    meta_path = config.PROJECTS_DIR / project.id / "document.json"
    meta_path.write_text(doc.model_dump_json(indent=2))

    return HefterProcessResponse(
        project_id=project.id, document=doc, preview_urls=preview_urls
    )


@router.get("/preview/{project_id}", response_model=HefterDocument)
def hefter_preview(project_id: str) -> HefterDocument:
    doc_path = config.PROJECTS_DIR / project_id / "document.json"
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Hefter-Dokument nicht gefunden.")
    return HefterDocument.model_validate_json(doc_path.read_text())


# Export-Endpunkte teilen sich dieselbe Logik wie Handwriting.
from PIL import Image  # noqa: E402


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
        raise HTTPException(status_code=400, detail="Keine Seiten vorhanden.")
    return pages


@router.post("/export/pdf", response_model=ExportResponse)
def export_pdf_ep(req: ExportRequest) -> ExportResponse:
    project = projects.load_meta(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    pages = _load_pages(req.project_id)
    out = config.EXPORTS_DIR / f"{req.project_id}-hefter.pdf"
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
        paths = export.export_png(pages, tmp_dir, "hefter")
    elif req.format == "jpg":
        paths = export.export_jpg(pages, tmp_dir, "hefter")
    else:
        raise HTTPException(status_code=400, detail="Nur png oder jpg erlaubt.")
    for p in paths:
        projects.add_export(project, p)
    first = paths[0]
    return ExportResponse(
        project_id=req.project_id,
        format=req.format,
        url=f"/files/exports/{project.id}-{first.name}",
        filename=first.name,
    )
