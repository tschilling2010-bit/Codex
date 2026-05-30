"""Font export: build a .ttf from handwritten glyph PNGs using SBIX bitmap strikes.

Each character's PNG is embedded directly — no vector tracing needed.
SBIX is Apple's native bitmap strike format (used for emoji); custom SBIX fonts
install and render in Pages, Notes, etc. on iPad/iPhone/Mac.
"""
from __future__ import annotations

import io
import logging
from typing import Dict, List, Tuple

from PIL import Image

from .. import config

log = logging.getLogger(__name__)


def build_font(profile_id: str, profile_name: str) -> bytes:
    """Return a .ttf font file (bytes) from the profile's handwritten glyph PNGs."""
    try:
        from fontTools.fontBuilder import FontBuilder
        from fontTools.ttLib.tables._g_l_y_f import Glyph as GlyfGlyph
        from fontTools.ttLib.tables._s_b_i_x import table__s_b_i_x
        from fontTools.ttLib.tables.sbixStrike import Strike
        from fontTools.ttLib.tables.sbixGlyph import Glyph as SbixGlyph
    except ImportError as exc:
        raise RuntimeError(
            "fonttools fehlt. Bitte 'fonttools' in requirements.txt eintragen."
        ) from exc

    glyph_dir = config.PROFILES_DIR / profile_id / "glyphs"
    if not glyph_dir.exists():
        raise ValueError("Profil nicht gefunden.")

    # --- Load glyph PNGs ---
    char_data: Dict[str, Tuple[int, int, bytes]] = {}  # char -> (w, h, png_bytes)

    for hex_dir in sorted(glyph_dir.iterdir()):
        if not hex_dir.is_dir():
            continue
        try:
            code_point = int(hex_dir.name, 16)
        except ValueError:
            continue
        char = chr(code_point)
        if not char.isprintable() or char in (" ", "\t"):
            continue
        pngs = sorted(hex_dir.glob("*.png"))
        if not pngs:
            continue
        try:
            img = Image.open(pngs[0]).convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, "PNG")
            char_data[char] = (img.width, img.height, buf.getvalue())
        except Exception as exc:
            log.warning("Glyph %s konnte nicht geladen werden: %s", hex_dir.name, exc)

    if not char_data:
        raise ValueError(
            "Keine Glyphen im Profil. Bitte zuerst Vorlagen hochladen und einlernen."
        )

    # --- Font metrics ---
    UPM = 2048

    heights = sorted(h for (_, h, _) in char_data.values())
    ref_height = max(heights[len(heights) // 2], 1)  # median pixel height
    scale = UPM / ref_height  # pixel → font units

    ascent = UPM
    descent = -int(UPM * 0.25)

    # --- Glyph registry ---
    glyph_order: List[str] = [".notdef", "space"]
    cmap: Dict[int, str] = {32: "space"}
    advances: Dict[str, int] = {
        ".notdef": int(UPM * 0.5),
        "space": int(UPM * 0.3),
    }

    for char in sorted(char_data, key=ord):
        w, h, _ = char_data[char]
        gname = "uni%04X" % ord(char)
        glyph_order.append(gname)
        cmap[ord(char)] = gname
        advances[gname] = max(200, int(w * scale))

    glyph_index = {g: i for i, g in enumerate(glyph_order)}

    # --- Build TTF skeleton with FontBuilder ---
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)

    # Empty glyf outlines — visual rendering comes from SBIX bitmaps
    empty_glyph = GlyfGlyph()
    empty_glyph.numberOfContours = 0
    fb.setupGlyf({g: empty_glyph for g in glyph_order})

    fb.setupHorizontalMetrics({g: (advances.get(g, int(UPM * 0.5)), 0) for g in glyph_order})
    fb.setupHorizontalHeader(ascent=ascent, descent=descent)

    # ASCII-only family name for maximum cross-app compatibility
    safe_name = "".join(
        c for c in profile_name if c.isascii() and (c.isalnum() or c in " -_")
    ).strip() or "HefterPro Handschrift"

    fb.setupNameTable({"familyName": safe_name, "styleName": "Regular"})
    fb.setupOS2(
        sTypoAscender=ascent,
        sTypoDescender=descent,
        sTypoLineGap=int(UPM * 0.1),
        usWinAscent=ascent,
        usWinDescent=-descent,
        sxHeight=int(UPM * 0.5),
        sCapHeight=int(UPM * 0.7),
        achVendID="HFPR",
        fsType=0,  # installable embedding
    )
    fb.setupPost()
    fb.setupHead(unitsPerEm=UPM)

    # --- SBIX table: embed PNG images as bitmap strikes ---
    font = fb.font

    sbix_table = table__s_b_i_x("sbix")
    sbix_table.version = 1
    sbix_table.flags = 1

    strike = Strike(ppem=ref_height, resolution=72)

    for gname in glyph_order:
        sg = SbixGlyph(
            glyphName=gname,
            gid=glyph_index[gname],
            originOffsetX=0,
            originOffsetY=0,
            graphicType="png ",
            imageData=b"",
        )
        strike.glyphs[gname] = sg

    for char, (w, h, png_bytes) in char_data.items():
        gname = "uni%04X" % ord(char)
        if gname in strike.glyphs:
            strike.glyphs[gname].imageData = png_bytes

    sbix_table.strikes = {ref_height: strike}
    font["sbix"] = sbix_table

    out = io.BytesIO()
    font.save(out)
    log.info(
        "Font '%s' erstellt: %d Glyphen, ref_height=%dpx",
        safe_name, len(char_data), ref_height,
    )
    return out.getvalue()
