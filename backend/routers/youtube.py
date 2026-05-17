"""API router: YouTube video downloader and splitter."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..services import youtube_service

log = logging.getLogger(__name__)
router = APIRouter()


class DownloadRequest(BaseModel):
    url: str


class TimestampEntry(BaseModel):
    start: float
    end: float | None = None
    name: str = ""


class SplitRequest(BaseModel):
    timestamps: List[TimestampEntry]


_YT_URL_RE = re.compile(
    r"https?://(www\.)?(youtube\.com/watch|youtu\.be/|youtube\.com/shorts/)"
)


@router.post("/download")
def start_download(req: DownloadRequest, background_tasks: BackgroundTasks) -> dict:
    url = req.url.strip()
    if not _YT_URL_RE.match(url):
        raise HTTPException(400, "Ungültige YouTube-URL")
    job_id = youtube_service.create_download_job(url)
    background_tasks.add_task(youtube_service.run_download, job_id, url)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    meta = youtube_service.get_job_status(job_id)
    if not meta:
        raise HTTPException(404, "Job nicht gefunden")
    return meta


@router.get("/jobs/{job_id}/video")
def stream_video(job_id: str) -> FileResponse:
    meta = youtube_service.get_job_status(job_id)
    if not meta:
        raise HTTPException(404, "Job nicht gefunden")
    video_path = youtube_service.get_video_path(job_id)
    if not video_path or not video_path.exists():
        raise HTTPException(404, "Video noch nicht bereit")
    return FileResponse(str(video_path), media_type="video/mp4")


@router.post("/jobs/{job_id}/split")
def split_video(job_id: str, req: SplitRequest) -> dict:
    meta = youtube_service.get_job_status(job_id)
    if not meta:
        raise HTTPException(404, "Job nicht gefunden")
    if meta.get("status") != "ready":
        raise HTTPException(400, "Video ist noch nicht bereit")
    if not req.timestamps:
        raise HTTPException(400, "Keine Zeitmarken angegeben")
    try:
        parts = youtube_service.split_video(
            job_id,
            [t.model_dump() for t in req.timestamps],
        )
        return {"parts": parts}
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        log.exception("Split failed for job %s", job_id)
        raise HTTPException(500, str(exc))


@router.get("/jobs/{job_id}/parts/{part_id}/download")
def download_part(job_id: str, part_id: str) -> FileResponse:
    meta = youtube_service.get_job_status(job_id)
    if not meta:
        raise HTTPException(404, "Job nicht gefunden")
    part = next((p for p in meta.get("parts", []) if p["part_id"] == part_id), None)
    if not part:
        raise HTTPException(404, "Part nicht gefunden")
    file_path = Path(part["file"])
    if not file_path.exists():
        raise HTTPException(404, "Part-Datei nicht gefunden")
    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        filename=file_path.name,
        headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'},
    )
