"""YouTube download and video splitting service."""
from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from pathlib import Path

from .. import config

log = logging.getLogger(__name__)

JOBS_DIR = config.STORAGE_DIR / "youtube_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _meta_path(job_id: str) -> Path:
    return _job_dir(job_id) / "meta.json"


def _load_meta(job_id: str) -> dict:
    path = _meta_path(job_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_meta(job_id: str, meta: dict) -> None:
    _meta_path(job_id).write_text(json.dumps(meta, indent=2, ensure_ascii=False))


def create_download_job(url: str) -> str:
    job_id = str(uuid.uuid4())
    _job_dir(job_id).mkdir(parents=True)
    _save_meta(job_id, {"url": url, "status": "pending", "progress": 0})
    return job_id


def run_download(job_id: str, url: str) -> None:
    job_dir = _job_dir(job_id)
    try:
        _save_meta(job_id, {**_load_meta(job_id), "status": "downloading", "progress": 10})

        info_result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", url],
            capture_output=True, text=True, check=True,
        )
        info = json.loads(info_result.stdout)

        title = info.get("title", "video")
        duration = float(info.get("duration") or 0)
        chapters = info.get("chapters") or []

        _save_meta(job_id, {
            **_load_meta(job_id),
            "title": title,
            "duration": duration,
            "chapters": chapters,
            "progress": 30,
        })

        video_path = job_dir / "video.mp4"
        subprocess.run(
            [
                "yt-dlp",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "-o", str(video_path),
                url,
            ],
            check=True, capture_output=True,
        )

        _save_meta(job_id, {
            **_load_meta(job_id),
            "status": "ready",
            "progress": 100,
            "video_file": str(video_path),
        })

    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
        log.error("Download failed for job %s: %s", job_id, stderr[:500])
        _save_meta(job_id, {**_load_meta(job_id), "status": "error", "error": stderr[:300]})
    except Exception as exc:
        log.exception("Download failed for job %s", job_id)
        _save_meta(job_id, {**_load_meta(job_id), "status": "error", "error": str(exc)})


def get_job_status(job_id: str) -> dict:
    return _load_meta(job_id)


def get_video_path(job_id: str) -> Path | None:
    meta = _load_meta(job_id)
    p = meta.get("video_file")
    return Path(p) if p else None


def split_video(job_id: str, timestamps: list[dict]) -> list[dict]:
    """
    timestamps: list of {start: float, end: float | None, name: str}
    Returns list of {part_id, name, file, start, end}
    """
    meta = _load_meta(job_id)
    video_path = meta.get("video_file")
    if not video_path or not Path(video_path).exists():
        raise FileNotFoundError("Video not found for job")

    parts_dir = _job_dir(job_id) / "parts"
    parts_dir.mkdir(exist_ok=True)

    parts: list[dict] = []
    for i, ts in enumerate(timestamps):
        name = (ts.get("name") or f"Part {i + 1}").strip()
        safe = re.sub(r"[^\w\s\-]", "", name).strip().replace(" ", "_")
        part_file = parts_dir / f"part_{i + 1:02d}_{safe}.mp4"

        start = float(ts.get("start", 0))
        end = ts.get("end")

        cmd = ["ffmpeg", "-y", "-ss", str(start)]
        if end is not None:
            cmd += ["-to", str(float(end))]
        cmd += ["-i", video_path, "-c", "copy", str(part_file)]

        subprocess.run(cmd, check=True, capture_output=True)

        parts.append({
            "part_id": f"part_{i + 1:02d}",
            "name": name,
            "file": str(part_file),
            "start": start,
            "end": end,
        })

    _save_meta(job_id, {**meta, "parts": parts})
    return parts
