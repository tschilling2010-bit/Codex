"""API: Handschrift-Rendering, Profile & Template-Paare."""
from __future__ import annotations

import io
import json
import logging
import time
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image

from .. import config
from ..models.schemas import (
    ExportRequest,
    ExportResponse,
    HighlightRequest,
    ProfileCreateRequest,
    ProfileInfo,
    ProfileRenameRequest,
    ProfileSettingsUpdate,
    RenderRequest,
    RenderResponse,
)
from ..services import export, fonts, projects, template_service
from ..services.rendering import RenderOptions, apply_highlights, render_text

log = logging.getLogger(__name__)
router = APIRouter()

MAX_PAIRS = fonts.MAX_PAIRS


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@router.get("/profile/list", response_model=List[ProfileInfo])
def profile_list() -> List[ProfileInfo]:
    return [ProfileInfo(**p) for p in fonts.list_profiles()]


@router.post("/profile/create", response_model=ProfileInfo)
def profile_create(req: ProfileCreateRequest) -> ProfileInfo:
    profile_id = uuid.uuid4().hex[:10]
    meta = fonts.create_profile(profile_id, req.name)
    return ProfileInfo(**meta)


@router.get("/profile/{profile_id}", response_model=ProfileInfo)
def profile_get(profile_id: str) -> ProfileInfo:
    meta = fonts.get_profile(profile_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    return ProfileInfo(**meta)


@router.post("/profile/{profile_id}/rename", response_model=ProfileInfo)
def profile_rename(profile_id: str, req: ProfileRenameRequest) -> ProfileInfo:
    meta = fonts.rename_profile(profile_id, req.name)
    if meta is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    return ProfileInfo(**meta)


@router.post("/profile/{profile_id}/settings", response_model=ProfileInfo)
def profile_settings(profile_id: str,
                     req: ProfileSettingsUpdate) -> ProfileInfo:
    meta = fonts.update_settings(
        profile_id,
        req.model_dump(exclude_none=True),
    )
    if meta is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    return ProfileInfo(**meta)


@router.delete("/profile/{profile_id}")
def profile_delete(profile_id: str) -> dict:
    if not fonts.delete_user_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    return {"deleted": profile_id}


@router.get("/profile/{profile_id}/backup")
def profile_backup(profile_id: str) -> Response:
    """Download entire profile (meta + glyphs + templates) as ZIP."""
    profile_dir = config.PROFILES_DIR / profile_id
    template_dir = config.TEMPLATES_DIR / profile_id
    if not profile_dir.exists():
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for base_dir, prefix in [(profile_dir, "profile"), (template_dir, "templates")]:
            if not base_dir.exists():
                continue
            for fpath in sorted(base_dir.rglob("*")):
                if fpath.is_file():
                    arcname = f"{prefix}/{fpath.relative_to(base_dir)}"
                    zf.write(fpath, arcname)
    buf.seek(0)

    meta = fonts.get_profile(profile_id)
    name = (meta or {}).get("name", profile_id)
    filename = f"hefterpro-{name}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/profile/restore")
async def profile_restore(file: UploadFile = File(...)) -> dict:
    """Restore a profile from a backup ZIP."""
    data = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige ZIP-Datei.")

    meta_entry = None
    for name in zf.namelist():
        if name == "profile/meta.json" or name.endswith("/meta.json"):
            if "profile/" in name:
                meta_entry = name
                break
    if meta_entry is None:
        raise HTTPException(status_code=400, detail="Kein Profil in der ZIP gefunden.")

    meta = json.loads(zf.read(meta_entry))
    profile_id = meta.get("id")
    if not profile_id:
        profile_id = uuid.uuid4().hex[:10]
        meta["id"] = profile_id

    profile_dir = config.PROFILES_DIR / profile_id
    template_dir = config.TEMPLATES_DIR / profile_id

    for entry in zf.namelist():
        if entry.endswith("/"):
            continue
        if entry.startswith("profile/"):
            rel = entry[len("profile/"):]
            out = profile_dir / rel
        elif entry.startswith("templates/"):
            rel = entry[len("templates/"):]
            out = template_dir / rel
        else:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(zf.read(entry))

    zf.close()
    updated = fonts.get_profile(profile_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Wiederherstellung fehlgeschlagen.")
    return {"profile": updated, "profile_id": profile_id}


# ---------------------------------------------------------------------------
# Template pairs
# ---------------------------------------------------------------------------


@router.post("/profile/{profile_id}/pair/create")
def pair_create(profile_id: str,
                pair_index: Optional[int] = Form(None)) -> dict:
    meta = fonts.get_profile(profile_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")

    if pair_index is None:
        idx = fonts.next_free_pair_index(profile_id)
        if idx is None:
            raise HTTPException(
                status_code=400,
                detail=f"Profil hat bereits {MAX_PAIRS} Paare.",
            )
    else:
        if not (0 <= pair_index < MAX_PAIRS):
            raise HTTPException(
                status_code=400,
                detail=f"pair_index muss zwischen 0 und {MAX_PAIRS - 1} liegen.",
            )
        idx = pair_index

    tpl = template_service.generate_pair(profile_id, idx, meta["name"])
    updated = fonts.register_pair(profile_id, idx)
    return {
        "profile_id": profile_id,
        "pair_index": idx,
        "page_urls": tpl["page_urls"],
        "pages": tpl["pages"],
        "profile": updated,
    }


@router.get("/profile/{profile_id}/pair/{pair_index}/pdf")
def pair_pdf(profile_id: str, pair_index: int) -> Response:
    if fonts.get_profile(profile_id) is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    if template_service.load_pair_meta(profile_id, pair_index) is None:
        raise HTTPException(status_code=404, detail="Template-Paar nicht gefunden.")

    pair_dir = config.TEMPLATES_DIR / profile_id / f"pair-{pair_index}"
    page_paths = [pair_dir / f"page-{i}.png" for i in (1, 2)]

    # Render pages on demand — they may not exist yet if just registered.
    if not all(p.exists() for p in page_paths):
        try:
            template_service.render_pair_pages(profile_id, pair_index)
        except Exception as exc:
            log.exception("render_pair_pages failed for pair %d", pair_index)
            raise HTTPException(status_code=500, detail=f"Seiten-Rendering fehlgeschlagen: {exc}")

    pages: List[Image.Image] = []
    for p in page_paths:
        if p.exists():
            pages.append(Image.open(p).convert("RGB"))
    if not pages:
        raise HTTPException(status_code=404, detail="Keine Seiten gefunden.")

    buf = io.BytesIO()
    pages[0].save(
        buf, save_all=True, append_images=pages[1:],
        resolution=config.PAGE_DPI, format="PDF",
    )
    buf.seek(0)
    filename = f"template-paar-{pair_index + 1}.pdf"
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/profile/{profile_id}/pair/{pair_index}/upload")
async def pair_upload(
    profile_id: str,
    pair_index: int,
    page_1: UploadFile = File(...),
    page_2: UploadFile = File(...),
) -> dict:
    if fonts.get_profile(profile_id) is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    if template_service.load_pair_meta(profile_id, pair_index) is None:
        raise HTTPException(
            status_code=404,
            detail="Template-Paar nicht gefunden. Bitte zuerst erzeugen.",
        )

    images: List[Image.Image] = []
    for f in (page_1, page_2):
        data = await f.read()
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Bild nicht lesbar: {exc}")
        images.append(img.convert("RGB"))

    result = template_service.process_uploaded_pair(images, profile_id, pair_index)
    meta = fonts.mark_pair_uploaded(profile_id, pair_index, result["glyph_count"])
    if meta is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    return {
        "profile": ProfileInfo(**meta).model_dump(),
        "preview_url": result.get("preview_url"),
        "char_count": result.get("char_count", 0),
        "glyph_count": result.get("glyph_count", 0),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@router.post("/render", response_model=RenderResponse)
def render(req: RenderRequest) -> RenderResponse:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text darf nicht leer sein.")

    profile = fonts.get_profile(req.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    if profile["glyph_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail="Profil hat noch keine Glyphen. Bitte mindestens ein Template-Paar ausfüllen & hochladen.",
        )

    settings = profile["settings"]
    options = RenderOptions(
        profile_id=req.profile_id,
        sheet_type=req.sheet_type or settings["sheet_type"],
        ink_color=req.ink_color or settings["ink_color"],
        jitter=req.jitter if req.jitter is not None else settings["jitter"],
        size_scale=req.size_scale if req.size_scale is not None else settings["size_scale"],
        thickness=req.thickness if req.thickness is not None else settings["thickness"],
    )
    pages, word_map = render_text(req.text, profile_id=req.profile_id, options=options)
    title = req.text.strip().split("\n")[0][:40] or "Handschrift"
    project = projects.new_project("handwriting", title)
    preview_urls = projects.save_pages(project, pages)
    projects.save_original_pages(project, pages)
    projects.save_word_map(project.id, word_map)
    return RenderResponse(
        project_id=project.id,
        pages=len(pages),
        preview_urls=preview_urls,
        word_map=word_map,
        page_width=config.PAGE_WIDTH_PX,
        page_height=config.PAGE_HEIGHT_PX,
    )


# ---------------------------------------------------------------------------
# Highlighting
# ---------------------------------------------------------------------------


@router.post("/highlight", response_model=RenderResponse)
def highlight(req: HighlightRequest) -> RenderResponse:
    project = projects.load_meta(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")

    word_map = projects.load_word_map(req.project_id)
    if not word_map:
        raise HTTPException(status_code=400, detail="Keine Wort-Positionen vorhanden.")

    original_pages = projects.load_original_pages(req.project_id)
    if not original_pages:
        raise HTTPException(status_code=400, detail="Keine Seiten vorhanden.")

    highlights = [h.model_dump() for h in req.highlights]
    highlighted = apply_highlights(original_pages, highlights, word_map)
    preview_urls = projects.save_pages(project, highlighted)

    return RenderResponse(
        project_id=req.project_id,
        pages=len(highlighted),
        preview_urls=preview_urls,
        word_map=word_map,
        page_width=config.PAGE_WIDTH_PX,
        page_height=config.PAGE_HEIGHT_PX,
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _export_pages(req: ExportRequest):
    project = projects.load_meta(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    if req.highlights:
        pages = projects.load_original_pages(req.project_id)
        if not pages:
            raise HTTPException(status_code=400, detail="Keine Seiten vorhanden.")
        word_map = projects.load_word_map(req.project_id)
        hl_data = [h.model_dump() for h in req.highlights]
        try:
            pages = apply_highlights(pages, hl_data, word_map)
        except Exception as exc:
            log.exception("apply_highlights failed for project %s", req.project_id)
            raise HTTPException(status_code=500, detail=f"Highlight-Fehler: {exc}")
    else:
        pages = []
        for i in range(1, project.pages + 1):
            path = projects.page_file(project.id, i)
            if path is None:
                continue
            img = Image.open(path)
            img.load()
            pages.append(img)
    if not pages:
        raise HTTPException(status_code=400, detail="Keine Seiten zum Export vorhanden.")
    return project, pages


_export_cache: dict = {}


def _ensure_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def _clean_export_cache() -> None:
    now = time.time()
    expired = [k for k, (_, ts) in _export_cache.items() if now - ts > 300]
    for k in expired:
        del _export_cache[k]


@router.post("/export/pdf")
def export_pdf_ep(req: ExportRequest):
    log.info("PDF export: project=%s highlights=%d", req.project_id, len(req.highlights))
    project, pages = _export_pages(req)
    log.info("Pages ready: count=%d sizes=%s", len(pages), [p.size for p in pages])
    buf = io.BytesIO()
    rgb = [_ensure_rgb(p) for p in pages]
    rgb[0].save(
        buf, save_all=True, append_images=rgb[1:],
        resolution=config.PAGE_DPI, format="PDF",
    )
    data = buf.getvalue()
    log.info("PDF generated: %d bytes", len(data))
    filename = f"{project.id}-handwriting.pdf"
    _export_cache[filename] = (data, time.time())
    _clean_export_cache()
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/image")
def export_image_ep(req: ExportRequest):
    log.info("PNG export: project=%s highlights=%d", req.project_id, len(req.highlights))
    project, pages = _export_pages(req)
    buf = io.BytesIO()
    _ensure_rgb(pages[0]).save(buf, "PNG")
    data = buf.getvalue()
    log.info("PNG generated: %d bytes", len(data))
    filename = f"{project.id}-handwriting.png"
    _export_cache[filename] = (data, time.time())
    _clean_export_cache()
    return Response(
        content=data,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/download/{filename:path}")
def download_export_file(filename: str):
    safe = Path(filename).name
    if safe in _export_cache:
        data, _ = _export_cache[safe]
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe}"'},
        )
    filepath = config.EXPORTS_DIR / safe
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden.")
    return FileResponse(filepath, filename=safe, media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# Font export
# ---------------------------------------------------------------------------

import re as _re


@router.get("/profile/{profile_id}/font")
def download_font(profile_id: str):
    """Build and return a .ttf font file from the profile's handwritten glyphs."""
    from ..services import font_export

    meta = fonts.get_profile(profile_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden.")
    try:
        font_bytes = font_export.build_font(profile_id, meta.get("name", profile_id))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    safe_name = _re.sub(r"[^\w\-]", "_", meta.get("name", profile_id))
    filename = f"{safe_name}.ttf"
    return Response(
        content=font_bytes,
        media_type="font/ttf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# KI-Modus
# ---------------------------------------------------------------------------
