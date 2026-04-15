"""Smoke-Tests: Import, Default-Profil, Text-Rendering, Hefter-Build, Export."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend import config  # noqa: E402
from backend.models.schemas import HefterProcessRequest  # noqa: E402
from backend.services import export, hefter_generator, projects  # noqa: E402
from backend.services.file_processing import ExtractedContent  # noqa: E402
from backend.services.glyph_engine import GlyphEngine, ensure_default_profile  # noqa: E402
from backend.services.rendering import RenderOptions, render_text  # noqa: E402
from backend.services.template_service import generate_template  # noqa: E402


def run() -> None:
    ensure_default_profile()
    engine = GlyphEngine("default")
    assert engine.meta["glyph_count"] > 0, "Default-Profil leer"

    # Render
    pages = render_text(
        "HefterPro — Test!\n\n- Erster Stichpunkt\n- Zweiter Stichpunkt",
        engine,
        RenderOptions(sheet_type="liniert"),
    )
    assert len(pages) >= 1
    project = projects.new_project("handwriting", "Smoke Test")
    projects.save_pages(project, pages)

    # Export
    out = config.EXPORTS_DIR / f"{project.id}-handwriting.pdf"
    export.export_pdf(pages, out)
    assert out.exists() and out.stat().st_size > 1000

    # Template
    tmpl = config.TEMPLATES_DIR / "smoke.pdf"
    meta = generate_template(tmpl)
    assert tmpl.exists()
    assert meta["pages"] >= 1 and len(meta["cells"]) > 50

    # Hefter
    content = ExtractedContent(
        text="Photosynthese:\nPflanzen nutzen Licht, um Zucker herzustellen. Wichtig: Sauerstoff wird als Nebenprodukt freigesetzt.",
        sources=["biologie.pdf"],
    )
    doc = hefter_generator.build_document(content, additional_text="", topic_hint="Photosynthese")
    assert doc.title == "Photosynthese"
    assert doc.sections
    hefter_pages = hefter_generator.render_hefter(doc, hefter_generator.HefterRenderOptions())
    assert hefter_pages
    out2 = config.EXPORTS_DIR / "smoke-hefter.pdf"
    export.export_pdf(hefter_pages, out2)
    assert out2.exists()

    print("OK")
    print(json.dumps({
        "glyph_count": engine.meta["glyph_count"],
        "handwriting_pages": len(pages),
        "hefter_pages": len(hefter_pages),
        "template_cells": len(meta["cells"]),
    }, indent=2))


if __name__ == "__main__":
    run()
