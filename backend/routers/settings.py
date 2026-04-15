"""API: App-Einstellungen."""
from __future__ import annotations

from fastapi import APIRouter

from ..models.schemas import AppSettings
from ..services import settings_store

router = APIRouter()


@router.get("/", response_model=AppSettings)
def get_settings() -> AppSettings:
    return settings_store.load_settings()


@router.put("/", response_model=AppSettings)
def update_settings(settings: AppSettings) -> AppSettings:
    return settings_store.save_settings(settings)
