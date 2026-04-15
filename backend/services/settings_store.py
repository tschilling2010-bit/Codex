"""Persistente App-Einstellungen."""
from __future__ import annotations

import json
from pathlib import Path

from .. import config
from ..models.schemas import AppSettings

SETTINGS_PATH: Path = config.STORAGE_DIR / "settings.json"


def load_settings() -> AppSettings:
    if SETTINGS_PATH.exists():
        try:
            return AppSettings(**json.loads(SETTINGS_PATH.read_text()))
        except Exception:
            pass
    return AppSettings()


def save_settings(settings: AppSettings) -> AppSettings:
    SETTINGS_PATH.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2))
    return settings
