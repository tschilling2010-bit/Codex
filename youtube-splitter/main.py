"""YouTube Splitter – standalone FastAPI app."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import youtube_service

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-splitter")

app = FastAPI(title="YouTube Splitter", version="1.0.0")

_YT_RE = re.compile(
    r"https?://(www\.)?(youtube\.com/watch|youtu\.be/|youtube\.com/shorts/)"
)


# ------------------------------------------------------------------ Models ---

class DownloadRequest(BaseModel):
    url: str


class TimestampEntry(BaseModel):
    start: float
    end: float | None = None
    name: str = ""


class SplitRequest(BaseModel):
    timestamps: List[TimestampEntry]


# ------------------------------------------------------------------- Routes --

@app.post("/api/download")
def start_download(req: DownloadRequest, bg: BackgroundTasks) -> dict:
    url = req.url.strip()
    if not _YT_RE.match(url):
        raise HTTPException(400, "Ungültige YouTube-URL")
    job_id = youtube_service.create_job(url)
    bg.add_task(youtube_service.run_download, job_id, url)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    meta = youtube_service.get_status(job_id)
    if not meta:
        raise HTTPException(404, "Job nicht gefunden")
    return meta


@app.get("/api/jobs/{job_id}/video")
def stream_video(job_id: str) -> FileResponse:
    path = youtube_service.get_video_path(job_id)
    if not path or not path.exists():
        raise HTTPException(404, "Video nicht bereit")
    return FileResponse(str(path), media_type="video/mp4")


@app.post("/api/jobs/{job_id}/split")
def split_video(job_id: str, req: SplitRequest) -> dict:
    meta = youtube_service.get_status(job_id)
    if not meta:
        raise HTTPException(404, "Job nicht gefunden")
    if meta.get("status") != "ready":
        raise HTTPException(400, "Video noch nicht bereit")
    if not req.timestamps:
        raise HTTPException(400, "Keine Zeitmarken angegeben")
    try:
        parts = youtube_service.split_video(job_id, [t.model_dump() for t in req.timestamps])
        return {"parts": parts}
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        log.exception("Split failed")
        raise HTTPException(500, str(exc))


@app.get("/api/jobs/{job_id}/parts/{part_id}/download")
def download_part(job_id: str, part_id: str) -> FileResponse:
    meta = youtube_service.get_status(job_id)
    if not meta:
        raise HTTPException(404, "Job nicht gefunden")
    part = next((p for p in meta.get("parts", []) if p["part_id"] == part_id), None)
    if not part:
        raise HTTPException(404, "Part nicht gefunden")
    file_path = Path(part["file"])
    if not file_path.exists():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        filename=file_path.name,
        headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'},
    )


# ----------------------------------------------------------- Static frontend --

_STATIC = Path(__file__).parent / "static"

app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")
