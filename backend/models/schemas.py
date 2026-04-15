"""Pydantic schemas shared across routers."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


SheetType = Literal["liniert", "kariert", "blanko"]
ExportFormat = Literal["pdf", "png", "jpg"]


class RenderRequest(BaseModel):
    text: str = Field(..., description="Der zu rendernde Text.")
    profile_id: str = Field("default", description="Handschrift-Profil-ID.")
    sheet_type: SheetType = "liniert"
    margin_mm: float = 20
    line_height_mm: float = 9
    glyph_height_mm: float = 5.5
    ink_color: str = "#1a2a6c"
    jitter: float = Field(1.0, ge=0.0, le=2.0, description="Stärke der natürlichen Abweichungen.")


class RenderResponse(BaseModel):
    project_id: str
    pages: int
    preview_urls: List[str]


class ExportRequest(BaseModel):
    project_id: str
    format: ExportFormat = "pdf"


class ExportResponse(BaseModel):
    project_id: str
    format: ExportFormat
    url: str
    filename: str


class ProfileInfo(BaseModel):
    id: str
    name: str
    source: Literal["default", "user"]
    glyph_count: int
    created_at: Optional[float] = None


class HefterProcessRequest(BaseModel):
    project_id: Optional[str] = None
    additional_text: str = ""
    topic_hint: str = ""
    profile_id: str = "default"


class HefterSection(BaseModel):
    heading: str
    body: List[str] = []
    bullets: List[str] = []
    callout: Optional[str] = None


class HefterDocument(BaseModel):
    title: str
    subtitle: Optional[str] = None
    sections: List[HefterSection]


class HefterProcessResponse(BaseModel):
    project_id: str
    document: HefterDocument
    preview_urls: List[str]


class ProjectInfo(BaseModel):
    id: str
    kind: Literal["handwriting", "hefter"]
    title: str
    created_at: float
    pages: int
    exports: List[str] = []


class AppSettings(BaseModel):
    default_profile_id: str = "default"
    default_sheet_type: SheetType = "liniert"
    default_export_format: ExportFormat = "pdf"
    margin_mm: float = 20
    line_height_mm: float = 9
    glyph_height_mm: float = 5.5
    ink_color: str = "#1a2a6c"
