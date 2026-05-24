"""Central configuration for HefterPro.

Simple, dependency-free config module. Paths are derived from an optional
HEFTERPRO_STORAGE env variable so the app can run anywhere.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

STORAGE_DIR = Path(os.environ.get("HEFTERPRO_STORAGE", BASE_DIR / "storage"))
PROFILES_DIR = STORAGE_DIR / "profiles"
PROJECTS_DIR = STORAGE_DIR / "projects"
EXPORTS_DIR = STORAGE_DIR / "exports"
UPLOADS_DIR = STORAGE_DIR / "uploads"
TEMPLATES_DIR = STORAGE_DIR / "templates"
SUBJECTS_DIR = STORAGE_DIR / "subjects"

for _d in (PROFILES_DIR, PROJECTS_DIR, EXPORTS_DIR, UPLOADS_DIR, TEMPLATES_DIR, SUBJECTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Page layout defaults (A4 @ 150 dpi).
PAGE_DPI = 300
PAGE_WIDTH_MM = 210
PAGE_HEIGHT_MM = 297


def mm_to_px(mm: float, dpi: int = PAGE_DPI) -> int:
    return int(round(mm / 25.4 * dpi))


PAGE_WIDTH_PX = mm_to_px(PAGE_WIDTH_MM)
PAGE_HEIGHT_PX = mm_to_px(PAGE_HEIGHT_MM)

# Default handwriting settings.
DEFAULT_MARGIN_MM = 20
DEFAULT_LINE_HEIGHT_MM = 9
DEFAULT_GLYPH_HEIGHT_MM = 5.5

SUPPORTED_SHEET_TYPES = ("liniert", "kariert", "blanko")
SUPPORTED_EXPORT_FORMATS = ("pdf", "png", "jpg")

# Optional AI hook for hefter structuring.  Disabled by default so the app
# works fully offline.
AI_ENABLED = os.environ.get("HEFTERPRO_AI", "0") == "1"

# OpenAI integration for AI-generated Hefter pages.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "dall-e-3")
OPENAI_TEXT_MODEL = os.environ.get("OPENAI_TEXT_MODEL", "gpt-4o-mini")
