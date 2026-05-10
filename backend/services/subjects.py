"""Persistent storage for Hefter Subjects (Fächer) and their AI-generated pages."""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import List, Optional

from .. import config
from ..models.schemas import HefterPageInfo, SubjectInfo


def _subject_dir(subject_id: str) -> Path:
    return config.SUBJECTS_DIR / subject_id


def _subject_meta(subject_id: str) -> Path:
    return _subject_dir(subject_id) / "subject.json"


def _pages_dir(subject_id: str) -> Path:
    return _subject_dir(subject_id) / "pages"


def list_subjects() -> List[SubjectInfo]:
    out: List[SubjectInfo] = []
    if not config.SUBJECTS_DIR.exists():
        return out
    for child in sorted(config.SUBJECTS_DIR.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        meta = child / "subject.json"
        if not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text())
            out.append(_inflate(data))
        except Exception:
            continue
    out.sort(key=lambda s: s.created_at, reverse=True)
    return out


def get_subject(subject_id: str) -> Optional[SubjectInfo]:
    meta = _subject_meta(subject_id)
    if not meta.exists():
        return None
    return _inflate(json.loads(meta.read_text()))


def _inflate(data: dict) -> SubjectInfo:
    sub = SubjectInfo.model_validate(data)
    pages: List[HefterPageInfo] = []
    pages_dir = _pages_dir(sub.id)
    if pages_dir.exists():
        for p in sorted(pages_dir.glob("*.json")):
            try:
                pages.append(HefterPageInfo.model_validate_json(p.read_text()))
            except Exception:
                continue
    pages.sort(key=lambda p: p.created_at)
    sub.pages = pages
    sub.page_count = len(pages)
    return sub


def create_subject(name: str, color: str, paper_type: str) -> SubjectInfo:
    sid = uuid.uuid4().hex[:10]
    _pages_dir(sid).mkdir(parents=True, exist_ok=True)
    sub = SubjectInfo(
        id=sid,
        name=name.strip(),
        color=color,
        paper_type=paper_type,
        created_at=time.time(),
    )
    save_subject(sub)
    return sub


def save_subject(sub: SubjectInfo) -> None:
    meta = _subject_meta(sub.id)
    meta.parent.mkdir(parents=True, exist_ok=True)
    payload = sub.model_dump(exclude={"pages", "page_count"})
    meta.write_text(json.dumps(payload, indent=2))


def delete_subject(subject_id: str) -> bool:
    d = _subject_dir(subject_id)
    if not d.exists():
        return False
    shutil.rmtree(d, ignore_errors=True)
    return True


def add_page(subject_id: str, title: str, image_bytes: bytes) -> HefterPageInfo:
    if get_subject(subject_id) is None:
        raise FileNotFoundError(subject_id)
    pid = uuid.uuid4().hex[:10]
    pages_dir = _pages_dir(subject_id)
    pages_dir.mkdir(parents=True, exist_ok=True)
    img_path = pages_dir / f"{pid}.png"
    img_path.write_bytes(image_bytes)
    page = HefterPageInfo(
        id=pid,
        subject_id=subject_id,
        title=title or "Hefterseite",
        created_at=time.time(),
        image_url=f"/api/hefter/subjects/{subject_id}/pages/{pid}.png",
    )
    (pages_dir / f"{pid}.json").write_text(page.model_dump_json(indent=2))
    return page


def get_page(subject_id: str, page_id: str) -> Optional[HefterPageInfo]:
    meta = _pages_dir(subject_id) / f"{page_id}.json"
    if not meta.exists():
        return None
    return HefterPageInfo.model_validate_json(meta.read_text())


def page_image_path(subject_id: str, page_id: str) -> Optional[Path]:
    p = _pages_dir(subject_id) / f"{page_id}.png"
    return p if p.exists() else None


def delete_page(subject_id: str, page_id: str) -> bool:
    pages_dir = _pages_dir(subject_id)
    img = pages_dir / f"{page_id}.png"
    meta = pages_dir / f"{page_id}.json"
    found = img.exists() or meta.exists()
    img.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return found


def all_page_paths(subject_id: str) -> List[Path]:
    pages_dir = _pages_dir(subject_id)
    if not pages_dir.exists():
        return []
    sub = get_subject(subject_id)
    if sub is None:
        return []
    return [pages_dir / f"{p.id}.png" for p in sub.pages if (pages_dir / f"{p.id}.png").exists()]
