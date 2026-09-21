"""Renders the "screenshot" of a source chunk shown in the reference view.

- PDF: the real page is rasterized (pypdfium2) and the chunk's exact
  characters are highlighted on it, with the value the extractor read
  highlighted more strongly. "crop" is a band around the chunk; "page" is the
  whole page.
- DOCX / TXT: these have no page images without a word processor, so the
  passage is drawn as an excerpt of the document text -- the chunk highlighted
  amid the lines around it, table rows drawn as table rows. It is a rendering
  of the extracted text, not of the original layout, and its header says so.

Images are cached under config.EVIDENCE_DIR and are safe to delete; they are
regenerated from the original upload on the next request.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config

PAGE_SCALE = 2.0
CROP_MARGIN_PX = 90
MIN_CROP_HEIGHT_PX = 280

_CHUNK_FILL = (255, 213, 0, 80)
_VALUE_FILL = (255, 111, 0, 120)
_VALUE_OUTLINE = (214, 74, 0, 255)


def cache_path(document_id: str, evidence_id: str, view: str) -> Path:
    return config.EVIDENCE_DIR / document_id / f"{evidence_id}_{view}.png"


# ---- text location helpers --------------------------------------------------------------

def _normalize_with_map(s: str) -> tuple[str, list[int]]:
    """Lower-cases and collapses whitespace runs to single spaces, returning the
    normalized string and, for each of its characters, the index in `s` it came
    from. PDF text and the extractor's text differ in whitespace and line breaks,
    so matching is done on the normalized forms and mapped back."""
    out: list[str] = []
    index: list[int] = []
    prev_space = True
    for i, ch in enumerate(s):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                index.append(i)
                prev_space = True
        else:
            out.append(ch.lower())
            index.append(i)
            prev_space = False
    if out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def _find_range(haystack: tuple[str, list[int]], needle: str, lo: int = 0, hi: int | None = None) -> tuple[int, int, int, int] | None:
    """Finds `needle` in the (normalized) haystack, searching normalized
    positions [lo, hi). Returns (start, end) in the original text plus
    (start, end) in normalized positions -- the latter so a second search can be
    confined to this match. Falls back to the needle's first 40 characters when
    the whole thing is not found, e.g. when extraction and the PDF wrapped a long
    chunk differently. None if not found."""
    norm, index = haystack
    needle_norm, _ = _normalize_with_map(needle)
    if not needle_norm:
        return None
    hi = len(norm) if hi is None else hi
    for candidate in (needle_norm, needle_norm[:40]):
        pos = norm.find(candidate, lo, hi)
        if pos >= 0:
            end = pos + len(candidate)
            return index[pos], index[end - 1] + 1, pos, end
    return None


# ---- PDF ----------------------------------------------------------------------------------

def _render_pdf(path: Path, page_number: int, chunk_text: str, value_text: str, view: str) -> Image.Image:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[page_number - 1]
        left, bottom, right, top = page.get_cropbox()
        image = page.render(scale=PAGE_SCALE).to_pil().convert("RGBA")

        chunk_rects: list[tuple[float, float, float, float]] = []
        value_rects: list[tuple[float, float, float, float]] = []
        if page.get_rotation() == 0:
            textpage = page.get_textpage()
            page_text = textpage.get_text_range()
            haystack = _normalize_with_map(page_text)

            chunk_range = _find_range(haystack, chunk_text)
            if chunk_range:
                start, end, norm_start, norm_end = chunk_range
                chunk_rects = _rects(textpage, start, end, left, top)
                # look for the value only inside the chunk's own characters
                value_range = _find_range(haystack, value_text, norm_start, norm_end) if value_text.strip() else None
                if value_range:
                    value_rects = _rects(textpage, value_range[0], value_range[1], left, top)

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for x0, y0, x1, y1 in chunk_rects:
            draw.rectangle((x0 - 3, y0 - 2, x1 + 3, y1 + 2), fill=_CHUNK_FILL)
        for x0, y0, x1, y1 in value_rects:
            draw.rectangle((x0 - 3, y0 - 2, x1 + 3, y1 + 2), fill=_VALUE_FILL, outline=_VALUE_OUTLINE, width=2)
        image = Image.alpha_composite(image, overlay).convert("RGB")

        if view == "crop" and chunk_rects:
            y_top = min(r[1] for r in chunk_rects)
            y_bottom = max(r[3] for r in chunk_rects)
            box_top = max(0, int(y_top - CROP_MARGIN_PX))
            box_bottom = min(image.height, int(y_bottom + CROP_MARGIN_PX))
            if box_bottom - box_top < MIN_CROP_HEIGHT_PX:
                extra = (MIN_CROP_HEIGHT_PX - (box_bottom - box_top)) // 2
                box_top, box_bottom = max(0, box_top - extra), min(image.height, box_bottom + extra)
            return image.crop((0, box_top, image.width, box_bottom))

        if view == "crop":  # could not locate the passage on the page: say so on the full page
            banner = Image.new("RGB", (image.width, 44), (253, 240, 214))
            ImageDraw.Draw(banner).text(
                (16, 12), "Could not pinpoint this passage on the page - showing the whole page.",
                fill=(154, 106, 0), font=_font(20),
            )
            combined = Image.new("RGB", (image.width, image.height + banner.height), "white")
            combined.paste(banner, (0, 0))
            combined.paste(image, (0, banner.height))
            return combined
        return image
    finally:
        pdf.close()


def _rects(textpage, start: int, end: int, page_left: float, page_top: float) -> list[tuple[float, float, float, float]]:
    """Pixel-space rectangles (x0, y0, x1, y1) covering characters [start, end) of a PDF page."""
    out = []
    for i in range(textpage.count_rects(start, end - start)):
        l, b, r, t = textpage.get_rect(i)
        out.append(((l - page_left) * PAGE_SCALE, (page_top - t) * PAGE_SCALE, (r - page_left) * PAGE_SCALE, (page_top - b) * PAGE_SCALE))
    return out


# ---- excerpt (DOCX / TXT / no original file) -----------------------------------------------

_FONT_NAMES = ("consola.ttf", "DejaVuSansMono.ttf", "cour.ttf", "LiberationMono-Regular.ttf")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_NAMES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1: scalable built-in font
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


def _wrap(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        trial = f"{current} {word}" if current else word
        if current and font.getlength(trial) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    lines.append(current)
    return lines


def _fit(text: str, font, max_width: int) -> str:
    """`text` shortened with an ellipsis so it renders within `max_width`."""
    if font.getlength(text) <= max_width:
        return text
    while text and font.getlength(text + "...") > max_width:
        text = text[:-1]
    return text + "..."


def _render_excerpt(context_text: str | None, chunk_start: int, chunk_text: str, value_text: str, header: str) -> Image.Image:
    width, pad, font_size = 940, 22, 17
    font, small = _font(font_size), _font(14)
    line_h = font_size + 9
    usable = width - 2 * pad

    # Split the document into lines with their offsets, then find the ones the chunk covers.
    entries: list[tuple[int, str]] = []  # (offset, line)
    if context_text is not None and context_text[chunk_start:chunk_start + 8] == chunk_text[:8]:
        pos = 0
        for line in context_text.split("\n"):
            entries.append((pos, line))
            pos += len(line) + 1
        chunk_end = chunk_start + len(chunk_text)
        hit = [i for i, (off, line) in enumerate(entries) if off < chunk_end and off + len(line) >= chunk_start]
    else:  # no usable surrounding text: show the chunk alone
        entries = [(chunk_start, line) for line in chunk_text.split("\n")]
        hit = list(range(len(entries)))

    first = max(0, (hit[0] if hit else 0) - 3)
    last = min(len(entries) - 1, (hit[-1] if hit else 0) + 3)
    if hit and hit[-1] - hit[0] > 14:  # a very long chunk: keep the top of it
        last = min(len(entries) - 1, hit[0] + 14)
    hit_set = set(hit)

    # lay out visual rows: (text, is_chunk, is_table_cells)
    rows: list[tuple[list[str], bool, bool]] = []
    for i in range(first, last + 1):
        line = entries[i][1].rstrip()
        in_chunk = i in hit_set
        if " | " in line:
            rows.append(([c.strip() for c in line.split(" | ")], in_chunk, True))
        elif not line.strip():
            rows.append(([""], in_chunk, False))
        else:
            for piece in _wrap(line, font, usable):
                rows.append(([piece], in_chunk, False))

    header_h = 34
    height = header_h + pad + len(rows) * line_h + pad
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, header_h), fill=(236, 239, 242))
    draw.text((pad, 9), _fit(header, small, usable), fill=(70, 80, 90), font=small)

    y = header_h + pad
    for cells, in_chunk, is_table in rows:
        if is_table:
            col_w = [usable * 0.62, *[usable * 0.38 / max(len(cells) - 1, 1)] * (len(cells) - 1)] if len(cells) > 1 else [usable]
            x = pad
            for cell, w in zip(cells, col_w):
                if in_chunk:
                    draw.rectangle((x, y - 2, x + w, y + line_h - 4), fill=(255, 240, 160))
                draw.rectangle((x, y - 2, x + w, y + line_h - 4), outline=(190, 196, 203))
                shown = cell
                while shown and font.getlength(shown) > w - 12:
                    shown = shown[:-2]
                draw.text((x + 6, y), shown + ("..." if shown != cell else ""), fill=(30, 36, 42), font=font)
                _mark_value(draw, font, value_text, shown, x + 6, y, line_h, in_chunk)
                x += w
        else:
            text = cells[0]
            if in_chunk:
                draw.rectangle((pad - 6, y - 3, width - pad + 6, y + line_h - 5), fill=(255, 240, 160))
            draw.text((pad, y), text, fill=(30, 36, 42), font=font)
            _mark_value(draw, font, value_text, text, pad, y, line_h, in_chunk)
        y += line_h
    return image


def _mark_value(draw: ImageDraw.ImageDraw, font, value_text: str, line: str, x: int, y: int, line_h: int, in_chunk: bool) -> None:
    """Outlines the raw value the extractor read, on the line that contains it."""
    if not (in_chunk and value_text.strip()):
        return
    needle = value_text.strip()
    at = line.find(needle)
    if at < 0:
        return
    x0 = x + font.getlength(line[:at])
    x1 = x0 + font.getlength(needle)
    draw.rectangle((x0 - 2, y - 2, x1 + 2, y + line_h - 4), fill=(255, 176, 102), outline=_VALUE_OUTLINE[:3], width=2)
    draw.text((x0, y), needle, fill=(30, 36, 42), font=font)


# ---- entry point ----------------------------------------------------------------------------

def render(
    *,
    original_path: Path | None,
    is_pdf: bool,
    page: int | None,
    chunk_text: str,
    chunk_start: int,
    value_text: str,
    context_text: str | None,
    header: str,
    view: str,
    out_path: Path,
) -> Path:
    """Renders one evidence image to `out_path` (creating parent directories)."""
    if is_pdf and original_path is not None and original_path.exists() and page:
        image = _render_pdf(original_path, page, chunk_text, value_text, view)
    else:
        image = _render_excerpt(context_text, chunk_start, chunk_text, value_text, header)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write then rename, so a concurrent request never serves a half-written image.
    tmp = out_path.with_name(f"{out_path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    image.save(tmp, format="PNG", optimize=True)
    os.replace(tmp, out_path)
    return out_path
