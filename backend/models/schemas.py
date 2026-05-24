"""Pydantic schemas shared across routers."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


SheetType = Literal["liniert", "kariert", "blanko"]
ExportFormat = Literal["pdf", "png", "jpg"]


class RenderRequest(BaseModel):
    text: str = Field(..., description="Der zu rendernde Text.")
    profile_id: str = Field(..., description="Handschrift-Profil-ID.")
    sheet_type: Optional[SheetType] = None
    ink_color: Optional[str] = None
    jitter: Optional[float] = Field(None, ge=0.0, le=2.0)
    size_scale: Optional[float] = Field(None, ge=0.5, le=2.0)
    thickness: Optional[float] = Field(None, ge=0.5, le=2.5)


class WordBoxSchema(BaseModel):
    text: str
    page: int
    x: int
    y: int
    w: int
    h: int


class RenderResponse(BaseModel):
    project_id: str
    pages: int
    preview_urls: List[str]
    word_map: List[WordBoxSchema] = []
    page_width: int = 0
    page_height: int = 0


class HighlightItem(BaseModel):
    word_index: int
    color: str = "#FFFF00"
    mode: str = "marker"


class HighlightRequest(BaseModel):
    project_id: str
    highlights: List[HighlightItem]


class ExportRequest(BaseModel):
    project_id: str
    format: ExportFormat = "pdf"
    highlights: List[HighlightItem] = []


class ExportResponse(BaseModel):
    project_id: str
    format: ExportFormat
    url: str
    filename: str


class ProfileSettings(BaseModel):
    size_scale: float = 1.0
    thickness: float = 1.0
    ink_color: str = "#16306b"
    sheet_type: SheetType = "liniert"
    jitter: float = 0.6


class PairInfo(BaseModel):
    index: int
    glyph_count: int = 0
    created_at: Optional[float] = None
    uploaded_at: Optional[float] = None


class ProfileInfo(BaseModel):
    id: str
    name: str
    source: str = "user"
    glyph_count: int = 0
    created_at: Optional[float] = None
    settings: ProfileSettings = ProfileSettings()
    pairs: List[PairInfo] = []


class ProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)


class ProfileRenameRequest(BaseModel):
    name: str = Field(..., min_length=1)


class ProfileSettingsUpdate(BaseModel):
    size_scale: Optional[float] = Field(None, ge=0.5, le=2.0)
    thickness: Optional[float] = Field(None, ge=0.5, le=2.5)
    ink_color: Optional[str] = None
    sheet_type: Optional[SheetType] = None
    jitter: Optional[float] = Field(None, ge=0.0, le=2.0)


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


# ----------------------------- Hefter v2 (Subjects + AI pages) -------------

PaperType = Literal["liniert", "kariert", "blanko"]


class HefterPageInfo(BaseModel):
    id: str
    subject_id: str
    title: str
    created_at: float
    image_url: str


class SubjectInfo(BaseModel):
    id: str
    name: str
    color: str = "#1a2a6c"
    paper_type: PaperType = "liniert"
    created_at: float
    page_count: int = 0
    pages: List[HefterPageInfo] = []


class SubjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    color: str = "#1a2a6c"
    paper_type: PaperType = "liniert"


class SubjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    color: Optional[str] = None
    paper_type: Optional[PaperType] = None


class HefterPageCreateRequest(BaseModel):
    title: Optional[str] = ""
    content: str = Field(..., min_length=1, description="Roher Text/Notizen, die in das Blatt sollen.")
