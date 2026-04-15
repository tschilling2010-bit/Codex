"""Export von Blattlisten in PDF/PNG/JPG."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from PIL import Image

from .. import config

log = logging.getLogger(__name__)


def _ensure_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def export_pdf(pages: List[Image.Image], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    rgb_pages = [_ensure_rgb(p) for p in pages]
    rgb_pages[0].save(
        output,
        save_all=True,
        append_images=rgb_pages[1:],
        resolution=config.PAGE_DPI,
        format="PDF",
    )
    return output


def export_png(pages: List[Image.Image], output_dir: Path, base_name: str) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for i, p in enumerate(pages, start=1):
        path = output_dir / f"{base_name}-{i:02d}.png"
        _ensure_rgb(p).save(path, "PNG")
        paths.append(path)
    return paths


def export_jpg(pages: List[Image.Image], output_dir: Path, base_name: str) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for i, p in enumerate(pages, start=1):
        path = output_dir / f"{base_name}-{i:02d}.jpg"
        _ensure_rgb(p).save(path, "JPEG", quality=92)
        paths.append(path)
    return paths
