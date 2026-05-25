# HefterPro

German student web app that converts typed text into the user's own handwriting. Built by Theo.

## Tech Stack

- **Backend:** Python 3 / FastAPI / Pillow (PIL) — no numpy in rendering pipeline
- **Frontend:** Vanilla JS (ES5 IIFE) — **NO const, let, arrow functions, async/await, template literals** (iOS Safari compatibility)
- **Deployment:** Render.com free tier, deploys from `main` branch (see `render.yaml`)
- **Storage:** File-based (profiles, glyphs, templates, projects under `backend/storage/`)

## Architecture

```
backend/
  config.py              # Paths, A4 layout constants (300 DPI, 2480x3508px)
  routers/
    handwriting.py        # API: profiles, template pairs, render, highlight, export
    hefter.py             # Hefter module (subjects/pages)
    projects.py           # Project CRUD
  services/
    fonts.py              # GlyphProfile, profile CRUD, module-level _profile_cache
    rendering.py          # GlyphRenderer, render_text(), apply_highlights()
    template_service.py   # Template PDF generation, glyph extraction from scans
    projects.py           # Page storage, _original_cache (RAM+disk), word maps
    export.py             # Export helpers
frontend/
  handwriting.html        # Main app page (cache bust ?v=35)
  css/styles.css          # Monochrome dark theme
  js/
    handwriting.js         # Main app logic (ES5 IIFE, ~900 lines)
    api.js                 # API wrapper (ES5)
    common.js              # Shared utilities
    persist.js             # IndexedDB ProfileCache
```

## Key Flows

1. **Render:** Text -> `render_text()` -> GlyphRenderer picks random glyph variants per char -> pastes onto A4 pages -> saves pages + word_map
2. **Highlight:** Client sends word indices + colors -> `apply_highlights()` applies marker (multiply blend) or text coloring (PIL LUT mask) -> re-saves pages
3. **Export:** POST `/export/pdf` or `/export/image` -> returns binary Response directly (no two-step) -> JS blob download
4. **Template upload:** User prints template PDF, fills in by hand, photographs -> uploads 2 pages -> `_extract_ink()` extracts glyphs via numpy

## Critical Constraints

- **ES5 only** in all frontend JS — user is on iPad/iOS Safari
- **Pure PIL** for highlight rendering (no numpy) — marker uses `ImageChops.multiply`, text uses grayscale->invert->LUT->paste
- **Dual cache** for original pages: RAM (`_original_cache`) + disk (`pages-original/`) — survives server restarts
- **Direct binary export** — export endpoints return `Response(content=bytes)`, JS fetches blob and triggers download
- **Zero quality loss** policy on any optimization

## Development

- Active dev branch: `claude/hefter-pro-development-tzBzb`
- **After every change: merge dev branch → `main` → push `main`.** Render.com deploys automatically from `main`. Never leave changes only on the dev branch.
- Workflow: develop on dev branch → commit → `git checkout main && git merge <dev-branch> --no-edit && git push origin main` → switch back to dev branch
- Cache bust: increment `?v=N` on all asset refs in `handwriting.html` when changing CSS/JS
- Server: `uvicorn backend.main:app --reload`

## Current State (May 2026)

- All core features working: render, highlight (marker + text coloring), export (PDF/PNG), profiles, template pairs
- KI-Modus: Gemini ◆ toggle in editor (top-right of editor-actions row), stored in localStorage
- Rainbow nav line + purple theme when KI-Modus active (CSS-only, `body.ai-mode`)
- Gemini 1.5 Flash integration via httpx REST API (free tier, 1500 req/day) — config.py GEMINI_API_KEY
- Hefter subject-management system removed (hefter.js/py/html cleaned up)
- Template variant creation instant (metadata only); PNGs rendered on-demand at PDF download
- Double-tap to delete highlight colors (iOS compatible)
- Export filename dialog before download
- UptimeRobot configured to keep Render instance awake
