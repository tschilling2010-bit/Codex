"""API: Projektverwaltung."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..models.schemas import ProjectInfo
from ..services import projects as project_service

router = APIRouter()


@router.get("/", response_model=List[ProjectInfo])
def project_list() -> List[ProjectInfo]:
    return [ProjectInfo(**p.to_dict()) for p in project_service.list_projects()]


@router.get("/{project_id}", response_model=ProjectInfo)
def project_get(project_id: str) -> ProjectInfo:
    project = project_service.load_meta(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    return ProjectInfo(**project.to_dict())


@router.delete("/{project_id}")
def project_delete(project_id: str) -> dict:
    if not project_service.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    return {"deleted": project_id}


@router.get("/{project_id}/pages/{page}")
def project_page(project_id: str, page: int) -> FileResponse:
    path = project_service.page_file(project_id, page)
    if path is None:
        raise HTTPException(status_code=404, detail="Seite nicht gefunden.")
    return FileResponse(path, media_type="image/png")
