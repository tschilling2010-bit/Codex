"""Pydantic schemas shared across routers."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


SheetType = Literal["liniert", "kariert", "blanko"]
ExportFormat = Literal["pdf", "png", "jpg"]


class RenderRequest(BaseModel):
    text: str = Field(..., description="Der zu rendernde Text.")
    profile_id: str = Field("hefterpro-natur", description="Handschrift-Profil-ID.")
    sheet_type: SheetType = "liniert"
    ink_color: str = "#16306b"
    jitter: float = Field(0.6, ge=0.0, le=2.0)


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
    source: str = "default"
    glyph_count: int = 0


class HefterProcessRequest(BaseModel):
    project_id: Optional[str] = None
    additional_text: str = ""
    topic_hint: str = ""


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
