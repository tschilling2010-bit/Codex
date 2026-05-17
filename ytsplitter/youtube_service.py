"""YouTube download and video splitting logic."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import uuid
from pathlib import Path

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass  # ffmpeg already on PATH in local dev

log = logging.getLogger(__name__)

JOBS_DIR = Path(os.environ.get("YT_STORAGE", "/var/data/youtube")) / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _meta(job_id: str) -> dict:
    p = _job_dir(job_id) / "meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save(job_id: str, data: dict) -> None:
    (_job_dir(job_id) / "meta.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False)
    )


def create_job(url: str) -> str:
    job_id = str(uuid.uuid4())
    _job_dir(job_id).mkdir(parents=True)
    _save(job_id, {"url": url, "status": "pending", "progress": 0})
    return job_id


def run_download(job_id: str, url: str) -> None:
    job_dir = _job_dir(job_id)
    try:
        _save(job_id, {**_meta(job_id), "status": "downloading", "progress": 10})

        info_raw = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", url],
            capture_output=True, text=True, check=True,
        )
        info = json.loads(info_raw.stdout)

        _save(job_id, {
            **_meta(job_id),
            "title": info.get("title", "video"),
            "duration": float(info.get("duration") or 0),
            "chapters": info.get("chapters") or [],
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

        _save(job_id, {
            **_meta(job_id),
            "status": "ready",
            "progress": 100,
            "video_file": str(video_path),
        })

    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode(errors="replace")[:400]
        log.error("Download failed %s: %s", job_id, err)
        _save(job_id, {**_meta(job_id), "status": "error", "error": err})
    except Exception as exc:
        log.exception("Download failed %s", job_id)
        _save(job_id, {**_meta(job_id), "status": "error", "error": str(exc)})


def get_status(job_id: str) -> dict:
    return _meta(job_id)


def get_video_path(job_id: str) -> Path | None:
    p = _meta(job_id).get("video_file")
    return Path(p) if p else None


def split_video(job_id: str, timestamps: list[dict]) -> list[dict]:
    meta = _meta(job_id)
    src = meta.get("video_file")
    if not src or not Path(src).exists():
        raise FileNotFoundError("Video nicht gefunden")

    parts_dir = _job_dir(job_id) / "parts"
    parts_dir.mkdir(exist_ok=True)

    parts: list[dict] = []
    for i, ts in enumerate(timestamps):
        name = (ts.get("name") or f"Part {i + 1}").strip()
        safe = re.sub(r"[^\w\s\-]", "", name).strip().replace(" ", "_") or f"part_{i+1}"
        out = parts_dir / f"part_{i + 1:02d}_{safe}.mp4"

        start = float(ts.get("start", 0))
        end = ts.get("end")

        cmd = ["ffmpeg", "-y", "-ss", str(start)]
        if end is not None:
            cmd += ["-to", str(float(end))]
        cmd += ["-i", src, "-c", "copy", str(out)]
        subprocess.run(cmd, check=True, capture_output=True)

        parts.append({
            "part_id": f"part_{i + 1:02d}",
            "name": name,
            "file": str(out),
            "start": start,
            "end": end,
        })

    _save(job_id, {**meta, "parts": parts})
    return parts
