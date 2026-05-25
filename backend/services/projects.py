"""Projekt-Speicherung.

Jedes Projekt liegt als eigener Ordner unter ``storage/projects/<id>`` mit:
  - meta.json         Projektmetadaten
  - pages/            Seitenvorschauen (PNG)
  - exports/          erzeugte Exporte (werden zusätzlich in EXPORTS_DIR
                      gespiegelt, damit der statische Mount sie findet)
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import io

from PIL import Image, ImageFile

from .. import config

ImageFile.LOAD_TRUNCATED_IMAGES = True

_original_cache: dict = {}


@dataclass
class Project:
    id: str
    kind: str
    title: str
    created_at: float
    pages: int = 0
    exports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "created_at": self.created_at,
            "pages": self.pages,
            "exports": self.exports,
        }


def _project_dir(project_id: str) -> Path:
    return config.PROJECTS_DIR / project_id


def _meta_path(project_id: str) -> Path:
    return _project_dir(project_id) / "meta.json"


def new_project(kind: str, title: str) -> Project:
    pid = uuid.uuid4().hex[:12]
    folder = _project_dir(pid)
    (folder / "pages").mkdir(parents=True, exist_ok=True)
    (folder / "exports").mkdir(parents=True, exist_ok=True)
    project = Project(id=pid, kind=kind, title=title, created_at=time.time())
    save_meta(project)
    return project


def save_meta(project: Project) -> None:
    _meta_path(project.id).write_text(
        json.dumps(project.to_dict(), ensure_ascii=False, indent=2)
    )


def load_meta(project_id: str) -> Optional[Project]:
    path = _meta_path(project_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return Project(**data)


def list_projects() -> List[Project]:
    result: List[Project] = []
    for folder in sorted(config.PROJECTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        project = load_meta(folder.name)
        if project is not None:
            result.append(project)
    return result


def save_pages(project: Project, pages: List[Image.Image]) -> List[str]:
    folder = _project_dir(project.id) / "pages"
    for f in folder.glob("*.png"):
        f.unlink()
    urls: List[str] = []
    for i, p in enumerate(pages, start=1):
        path = folder / f"page-{i:02d}.png"
        if p.mode != "RGB":
            bg = Image.new("RGB", p.size, "white")
            if "A" in p.mode:
                bg.paste(p, mask=p.split()[-1])
            else:
                bg.paste(p)
            bg.save(path, "PNG")
        else:
            p.save(path, "PNG")
        urls.append(f"/api/projects/{project.id}/pages/{i}")
    project.pages = len(pages)
    save_meta(project)
    return urls


def save_original_pages(project: Project, pages: List[Image.Image]) -> None:
    _original_cache.clear()
    compressed = []
    folder = _project_dir(project.id) / "pages-original"
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob("*.png"):
        f.unlink()
    for i, p in enumerate(pages, start=1):
        rgb = p
        if p.mode != "RGB":
            rgb = Image.new("RGB", p.size, "white")
            if "A" in p.mode:
                rgb.paste(p, mask=p.split()[-1])
            else:
                rgb.paste(p)
        buf = io.BytesIO()
        rgb.save(buf, "PNG")
        data = buf.getvalue()
        compressed.append(data)
        (folder / f"page-{i:02d}.png").write_bytes(data)
    _original_cache[project.id] = compressed


def load_original_pages(project_id: str) -> List[Image.Image]:
    if project_id in _original_cache:
        pages = []
        for data in _original_cache[project_id]:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img.load()
            pages.append(img)
        return pages
    folder = _project_dir(project_id) / "pages-original"
    if not folder.exists() or not list(folder.glob("*.png")):
        folder = _project_dir(project_id) / "pages"
    pages: List[Image.Image] = []
    for path in sorted(folder.glob("*.png")):
        img = Image.open(path).convert("RGB")
        img.load()
        pages.append(img)
    if pages:
        compressed = []
        for p in pages:
            buf = io.BytesIO()
            p.save(buf, "PNG")
            compressed.append(buf.getvalue())
        _original_cache[project_id] = compressed
    return pages


def save_word_map(project_id: str, word_map: list) -> None:
    path = _project_dir(project_id) / "word-map.json"
    path.write_text(json.dumps(word_map, ensure_ascii=False))


def load_word_map(project_id: str) -> list:
    path = _project_dir(project_id) / "word-map.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def page_file(project_id: str, page_number: int) -> Optional[Path]:
    path = _project_dir(project_id) / "pages" / f"page-{page_number:02d}.png"
    return path if path.exists() else None


def add_export(project: Project, source: Path) -> Path:
    """Kopiert eine Exportdatei in den statisch ausgelieferten Ordner."""
    dest = config.EXPORTS_DIR / f"{project.id}-{source.name}"
    shutil.copy2(source, dest)
    url = f"/files/exports/{dest.name}"
    if url not in project.exports:
        project.exports.append(url)
    save_meta(project)
    return dest


def delete_project(project_id: str) -> bool:
    folder = _project_dir(project_id)
    if not folder.exists():
        return False
    shutil.rmtree(folder)
    # Zugehörige Exporte aufräumen.
    for f in config.EXPORTS_DIR.glob(f"{project_id}-*"):
        try:
            f.unlink()
        except OSError:
            pass
    return True
