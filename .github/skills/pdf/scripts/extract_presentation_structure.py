"""
Extract presentation structure from a PDF (typically exported from PowerPoint).

Analyzes each page to extract:
- Text blocks with font info (name, size, color, bold/italic), coordinates, and semantic role
- Images with bounding boxes (actual image files extracted via pdfimages)
- Shapes: rectangles, lines, curves with color/fill info
- Tables with cell content and bounding boxes

For **image-based PDFs** (every page is a single embedded image with no text layer),
the script automatically detects this situation and falls back to OCR:
  1. RapidOCR (rapidocr_onnxruntime) — preferred, no external system dependencies
  2. Tesseract (pytesseract) — fallback if RapidOCR is unavailable

OCR results include bounding boxes which are converted to the same coordinate
system (inches) used by the pdfplumber path, so the downstream PPT generation
script (generate_from_structure.js) works identically for both sources.

Output: A JSON file that can be consumed by the PPT generation script
(generate_from_structure.js) to produce an editable, Cathay-styled PPTX.

Usage:
    python extract_presentation_structure.py <input.pdf> <output.json> [--images-dir <dir>]
           [--ocr-engine auto|rapidocr|tesseract] [--force-ocr] [--min-confidence 0.8]

Dependencies:
    pip install pdfplumber Pillow
    pip install rapidocr_onnxruntime          (recommended OCR engine)
    pip install pytesseract                   (fallback OCR; requires Tesseract system binary)
    pdfimages (from poppler-utils) must be on PATH for image extraction
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

import pdfplumber


# ---------------------------------------------------------------------------
# Data classes for intermediate representation
# ---------------------------------------------------------------------------

@dataclass
class TextRun:
    """A contiguous run of text with uniform styling."""
    text: str
    font_name: str = ""
    size: float = 12.0
    bold: bool = False
    italic: bool = False
    color: str = "262626"  # 6-char hex, no #


@dataclass
class TextBlock:
    """A group of text runs forming a logical block (title, paragraph, etc.)."""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    runs: list = field(default_factory=list)
    role: str = "body"  # title | subtitle | section_header | body | bullet | annotation
    align: str = "left"


@dataclass
class ImageElement:
    """An image on the page."""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    image_file: str = ""


@dataclass
class ShapeElement:
    """A geometric shape (rectangle, line, etc.)."""
    shape_type: str = "rectangle"  # rectangle | line | oval | curve
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    fill_color: str = ""
    stroke_color: str = ""
    line_width: float = 0.0


@dataclass
class TableElement:
    """A table extracted from the page."""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    rows: list = field(default_factory=list)  # list of list of str
    col_widths: list = field(default_factory=list)


@dataclass
class PageStructure:
    """All elements on a single page."""
    page_number: int = 1
    width_inches: float = 10.0
    height_inches: float = 7.5
    text_blocks: list = field(default_factory=list)
    images: list = field(default_factory=list)
    shapes: list = field(default_factory=list)
    tables: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PT_TO_INCH = 1.0 / 72.0


def color_to_hex(color_value) -> str:
    """Convert pdfplumber color (various formats) to 6-char hex string."""
    if color_value is None:
        return ""
    # Grayscale (single float 0-1)
    if isinstance(color_value, (int, float)):
        v = max(0, min(255, int(round(float(color_value) * 255))))
        return f"{v:02X}{v:02X}{v:02X}"
    # RGB tuple (0-1 range)
    if isinstance(color_value, (list, tuple)):
        if len(color_value) == 3:
            r, g, b = [max(0, min(255, int(round(float(c) * 255)))) for c in color_value]
            return f"{r:02X}{g:02X}{b:02X}"
        if len(color_value) == 4:
            # CMYK → RGB approximation
            c_, m_, y_, k_ = [float(x) for x in color_value]
            r = int(round(255 * (1 - c_) * (1 - k_)))
            g = int(round(255 * (1 - m_) * (1 - k_)))
            b = int(round(255 * (1 - y_) * (1 - k_)))
            return f"{max(0,min(255,r)):02X}{max(0,min(255,g)):02X}{max(0,min(255,b)):02X}"
        if len(color_value) == 1:
            return color_to_hex(color_value[0])
    return "262626"


def parse_font_style(fontname: str) -> dict:
    """Infer bold/italic from font name string."""
    fn = fontname.lower() if fontname else ""
    bold = any(tag in fn for tag in ["bold", "-bd", "black", "heavy", "demi"])
    italic = any(tag in fn for tag in ["italic", "oblique", "-it", "slant"])
    return {"bold": bold, "italic": italic}


def detect_chinese_font(fontname: str) -> bool:
    """Check if the font is a CJK font."""
    cjk_markers = [
        "jhenghei", "mingliu", "simsun", "simhei", "yahei", "kaiti",
        "fangsong", "nsimsun", "dfkai", "sung", "ming", "heiti",
        "songti", "stkaiti", "stheiti", "stfangsong", "noto sans cjk",
        "noto serif cjk", "source han", "cjk",
    ]
    fn = fontname.lower() if fontname else ""
    return any(m in fn for m in cjk_markers)


def infer_role(size: float, bold: bool, y_ratio: float, page_height: float,
               block_text: str) -> str:
    """Heuristically infer the semantic role of a text block.

    Args:
        size: font size in pt
        bold: whether the dominant run is bold
        y_ratio: block top position as fraction of page height (0=top, 1=bottom)
        page_height: page height in points
        block_text: concatenated text content
    """
    text_len = len(block_text.strip())
    if text_len == 0:
        return "annotation"

    # Very large text near top → title
    if size >= 24 and y_ratio < 0.35:
        return "title"
    # Large text → subtitle or section header
    if size >= 20:
        return "subtitle" if y_ratio < 0.35 else "section_header"
    if size >= 17 and bold:
        return "section_header"
    # Very small text → annotation / footnote
    if size <= 10:
        return "annotation"
    # Bullet detection: starts with bullet-like chars or has short lines
    bullet_pattern = re.compile(r"^[\u2022\u2023\u25CF\u25CB\u25AA\u25AB\u2013\u2014\-\*\>]")
    if bullet_pattern.match(block_text.strip()):
        return "bullet"
    return "body"


def infer_alignment(chars_in_block: list, block_x0: float, block_x1: float,
                    page_width: float) -> str:
    """Guess text alignment from character positions."""
    if not chars_in_block:
        return "left"
    # group chars by line (same top)
    lines = defaultdict(list)
    for c in chars_in_block:
        key = round(c["top"], 1)
        lines[key].append(c)

    if len(lines) < 2:
        # single line – check centering
        cx = (block_x0 + block_x1) / 2
        page_cx = page_width / 2
        if abs(cx - page_cx) < page_width * 0.08:
            return "center"
        return "left"

    # Multiple lines: check if left edges are aligned vs right edges
    lefts = [min(c["x0"] for c in cs) for cs in lines.values()]
    rights = [max(c["x1"] for c in cs) for cs in lines.values()]
    left_var = max(lefts) - min(lefts) if lefts else 0
    right_var = max(rights) - min(rights) if rights else 0

    if left_var < 3 and right_var < 3:
        return "justify"
    if left_var < 3:
        return "left"
    if right_var < 3:
        return "right"
    # check center alignment
    centers = [(l + r) / 2 for l, r in zip(lefts, rights)]
    center_var = max(centers) - min(centers) if centers else 0
    if center_var < 5:
        return "center"
    return "left"


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def group_chars_into_runs(chars: list) -> list[TextRun]:
    """Group consecutive characters with same style into TextRun objects."""
    if not chars:
        return []
    runs = []
    current_text = ""
    current_font = chars[0].get("fontname", "")
    current_size = round(chars[0].get("size", 12), 1)
    current_color = color_to_hex(chars[0].get("non_stroking_color"))
    style = parse_font_style(current_font)

    for ch in chars:
        fn = ch.get("fontname", "")
        sz = round(ch.get("size", 12), 1)
        col = color_to_hex(ch.get("non_stroking_color"))
        if fn == current_font and sz == current_size and col == current_color:
            current_text += ch.get("text", "")
        else:
            if current_text:
                runs.append(TextRun(
                    text=current_text,
                    font_name=current_font,
                    size=current_size,
                    bold=style["bold"],
                    italic=style["italic"],
                    color=current_color,
                ))
            current_text = ch.get("text", "")
            current_font = fn
            current_size = sz
            current_color = col
            style = parse_font_style(current_font)

    if current_text:
        runs.append(TextRun(
            text=current_text,
            font_name=current_font,
            size=current_size,
            bold=style["bold"],
            italic=style["italic"],
            color=current_color,
        ))
    return runs


def group_chars_into_lines(chars: list, tolerance: float = 3.0) -> list[list]:
    """Group characters into lines by their `top` coordinate."""
    if not chars:
        return []
    sorted_chars = sorted(chars, key=lambda c: (round(c["top"] / tolerance), c["x0"]))
    lines = []
    current_line = [sorted_chars[0]]
    current_top = sorted_chars[0]["top"]

    for ch in sorted_chars[1:]:
        if abs(ch["top"] - current_top) <= tolerance:
            current_line.append(ch)
        else:
            current_line.sort(key=lambda c: c["x0"])
            lines.append(current_line)
            current_line = [ch]
            current_top = ch["top"]
    if current_line:
        current_line.sort(key=lambda c: c["x0"])
        lines.append(current_line)
    return lines


def group_lines_into_blocks(lines: list, page_width: float,
                            page_height: float) -> list[dict]:
    """Group text lines into logical text blocks based on spatial proximity
    and font similarity."""
    if not lines:
        return []

    blocks = []
    current_block_lines = [lines[0]]
    prev_bottom = max(c["bottom"] for c in lines[0])
    prev_size = round(lines[0][0].get("size", 12), 1)
    prev_x0 = min(c["x0"] for c in lines[0])

    for line in lines[1:]:
        line_top = min(c["top"] for c in line)
        line_size = round(line[0].get("size", 12), 1)
        line_x0 = min(c["x0"] for c in line)
        gap = line_top - prev_bottom
        line_height = prev_size * 1.5  # approximate line height

        # Same block if: gap is small, font size similar, x0 reasonably close
        same_block = (
            gap < line_height * 1.8
            and abs(line_size - prev_size) < 4
            and abs(line_x0 - prev_x0) < page_width * 0.15
        )
        if same_block:
            current_block_lines.append(line)
        else:
            blocks.append(current_block_lines)
            current_block_lines = [line]

        prev_bottom = max(c["bottom"] for c in line)
        prev_size = line_size
        prev_x0 = line_x0

    if current_block_lines:
        blocks.append(current_block_lines)

    # Convert to dicts with bounding box
    result = []
    for block_lines in blocks:
        all_chars = [c for line in block_lines for c in line]
        x0 = min(c["x0"] for c in all_chars)
        top = min(c["top"] for c in all_chars)
        x1 = max(c["x1"] for c in all_chars)
        bottom = max(c["bottom"] for c in all_chars)
        result.append({
            "chars": all_chars,
            "lines": block_lines,
            "x0": x0, "top": top, "x1": x1, "bottom": bottom,
        })
    return result


def extract_text_blocks(page) -> list[TextBlock]:
    """Extract and group text into TextBlock objects from a pdfplumber page."""
    chars = page.chars
    if not chars:
        return []

    page_w = float(page.width)
    page_h = float(page.height)

    lines = group_chars_into_lines(chars)
    raw_blocks = group_lines_into_blocks(lines, page_w, page_h)

    text_blocks = []
    for blk in raw_blocks:
        all_chars = blk["chars"]
        runs = group_chars_into_runs(all_chars)
        if not runs:
            continue

        # Dominant style for role inference
        dominant_run = max(runs, key=lambda r: len(r.text))
        block_text = "".join(r.text for r in runs)
        y_ratio = blk["top"] / page_h if page_h > 0 else 0

        role = infer_role(
            dominant_run.size, dominant_run.bold, y_ratio, page_h, block_text
        )
        alignment = infer_alignment(all_chars, blk["x0"], blk["x1"], page_w)

        tb = TextBlock(
            x=round(blk["x0"] * PT_TO_INCH, 3),
            y=round(blk["top"] * PT_TO_INCH, 3),
            w=round((blk["x1"] - blk["x0"]) * PT_TO_INCH, 3),
            h=round((blk["bottom"] - blk["top"]) * PT_TO_INCH, 3),
            runs=[asdict(r) for r in runs],
            role=role,
            align=alignment,
        )
        text_blocks.append(tb)
    return text_blocks


def extract_shapes(page) -> list[ShapeElement]:
    """Extract rectangles and lines as shape elements."""
    shapes = []

    # Rectangles
    for rect in getattr(page, "rects", []):
        x0 = float(rect.get("x0", 0))
        top = float(rect.get("top", 0))
        x1 = float(rect.get("x1", 0))
        bottom = float(rect.get("bottom", 0))
        w = x1 - x0
        h = bottom - top
        if w < 2 and h < 2:
            continue  # skip tiny artifacts

        fill = color_to_hex(rect.get("non_stroking_color"))
        stroke = color_to_hex(rect.get("stroking_color"))
        lw = float(rect.get("linewidth", 0))

        shapes.append(ShapeElement(
            shape_type="rectangle",
            x=round(x0 * PT_TO_INCH, 3),
            y=round(top * PT_TO_INCH, 3),
            w=round(w * PT_TO_INCH, 3),
            h=round(h * PT_TO_INCH, 3),
            fill_color=fill,
            stroke_color=stroke,
            line_width=round(lw * PT_TO_INCH, 3),
        ))

    # Lines
    for line in getattr(page, "lines", []):
        x0 = float(line.get("x0", 0))
        top = float(line.get("top", 0))
        x1 = float(line.get("x1", 0))
        bottom = float(line.get("bottom", 0))
        w = abs(x1 - x0)
        h = abs(bottom - top)
        stroke = color_to_hex(line.get("stroking_color"))
        lw = float(line.get("linewidth", 0))

        shapes.append(ShapeElement(
            shape_type="line",
            x=round(min(x0, x1) * PT_TO_INCH, 3),
            y=round(min(top, bottom) * PT_TO_INCH, 3),
            w=round(w * PT_TO_INCH, 3),
            h=round(h * PT_TO_INCH, 3),
            fill_color="",
            stroke_color=stroke,
            line_width=round(lw * PT_TO_INCH, 3),
        ))

    return shapes


def extract_images_metadata(page, page_number: int) -> list[ImageElement]:
    """Extract image bounding boxes from the page (positions only)."""
    images = []
    for img in getattr(page, "images", []):
        x0 = float(img.get("x0", 0))
        top = float(img.get("top", 0))
        x1 = float(img.get("x1", 0))
        bottom = float(img.get("bottom", 0))
        w = x1 - x0
        h = bottom - top
        if w < 5 or h < 5:
            continue

        images.append(ImageElement(
            x=round(x0 * PT_TO_INCH, 3),
            y=round(top * PT_TO_INCH, 3),
            w=round(w * PT_TO_INCH, 3),
            h=round(h * PT_TO_INCH, 3),
            image_file="",  # filled later by extract_embedded_images()
        ))
    return images


def extract_tables_from_page(page) -> list[TableElement]:
    """Extract tables with bounding boxes."""
    tables = []
    try:
        found = page.find_tables()
    except Exception:
        found = []

    for tbl in found:
        bbox = tbl.bbox  # (x0, top, x1, bottom) in points
        rows = tbl.extract()
        if not rows:
            continue

        x0, top, x1, bottom = [float(v) for v in bbox]
        w = x1 - x0
        num_cols = max(len(r) for r in rows) if rows else 1
        col_w = round((w * PT_TO_INCH) / num_cols, 3) if num_cols else 0

        tables.append(TableElement(
            x=round(x0 * PT_TO_INCH, 3),
            y=round(top * PT_TO_INCH, 3),
            w=round(w * PT_TO_INCH, 3),
            h=round((bottom - top) * PT_TO_INCH, 3),
            rows=[[cell or "" for cell in row] for row in rows],
            col_widths=[col_w] * num_cols,
        ))
    return tables


# ---------------------------------------------------------------------------
# Image file extraction via pdfimages (poppler)
# ---------------------------------------------------------------------------

def extract_embedded_images(pdf_path: str, images_dir: str) -> dict:
    """Use poppler's pdfimages to extract actual image files.

    Returns a dict mapping (page_number, approx_index) -> filepath.
    Falls back gracefully if pdfimages is not available.
    """
    os.makedirs(images_dir, exist_ok=True)
    prefix = os.path.join(images_dir, "img")

    try:
        subprocess.run(
            ["pdfimages", "-all", pdf_path, prefix],
            check=True, capture_output=True, text=True,
        )
    except FileNotFoundError:
        print("WARNING: pdfimages not found. Image extraction skipped.")
        print("Install poppler-utils to enable image extraction.")
        return {}
    except subprocess.CalledProcessError as e:
        print(f"WARNING: pdfimages failed: {e.stderr}")
        return {}

    # Collect extracted files
    extracted = {}
    for fname in sorted(os.listdir(images_dir)):
        if not fname.startswith("img"):
            continue
        fpath = os.path.join(images_dir, fname)
        # pdfimages names files as img-NNN-MMM.ext
        # NNN = sequential index
        extracted[fname] = fpath

    return extracted


def match_images_to_metadata(image_elements: list[list[ImageElement]],
                             extracted_files: dict) -> None:
    """Best-effort assignment of extracted image files to metadata entries.

    Simple sequential matching: images are assigned in order of extraction.
    """
    file_list = sorted(extracted_files.values())
    idx = 0
    for page_images in image_elements:
        for img_elem in page_images:
            if idx < len(file_list):
                img_elem.image_file = file_list[idx]
                idx += 1


# ---------------------------------------------------------------------------
# OCR fallback for image-based PDFs
# ---------------------------------------------------------------------------

def _get_ocr_engine(preference: str = "auto"):
    """Return an OCR callable based on user preference and availability.

    Returns (engine_name, ocr_func) where ocr_func(image_path) returns a list
    of dicts: {"text": str, "bbox": (x0, y0, x1, y1), "confidence": float}
    bbox values are in pixel coordinates.
    """
    engines_to_try = []
    if preference in ("auto", "rapidocr"):
        engines_to_try.append("rapidocr")
    if preference in ("auto", "tesseract"):
        engines_to_try.append("tesseract")

    for engine in engines_to_try:
        if engine == "rapidocr":
            try:
                from rapidocr_onnxruntime import RapidOCR
                ocr_instance = RapidOCR()

                def _run_rapidocr(image_path, _inst=ocr_instance):
                    result, _ = _inst(image_path)
                    if not result:
                        return []
                    lines = []
                    for item in result:
                        bbox_pts = item[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                        text = item[1]
                        conf = item[2]
                        min_x = min(p[0] for p in bbox_pts)
                        min_y = min(p[1] for p in bbox_pts)
                        max_x = max(p[0] for p in bbox_pts)
                        max_y = max(p[1] for p in bbox_pts)
                        lines.append({
                            "text": text,
                            "bbox": (round(min_x), round(min_y),
                                     round(max_x), round(max_y)),
                            "confidence": round(conf, 3),
                        })
                    return lines

                print("  OCR engine: RapidOCR (rapidocr_onnxruntime)")
                return "rapidocr", _run_rapidocr
            except ImportError:
                if preference == "rapidocr":
                    print("ERROR: rapidocr_onnxruntime not installed.")
                    print("  Install: pip install rapidocr_onnxruntime")
                    sys.exit(1)

        if engine == "tesseract":
            try:
                import pytesseract
                # Quick availability check
                pytesseract.get_tesseract_version()

                def _run_tesseract(image_path):
                    from PIL import Image
                    img = Image.open(image_path)
                    data = pytesseract.image_to_data(
                        img, lang="chi_tra+eng", output_type=pytesseract.Output.DICT
                    )
                    lines = []
                    n = len(data["text"])
                    for i in range(n):
                        text = data["text"][i].strip()
                        conf = int(data["conf"][i])
                        if not text or conf < 0:
                            continue
                        x = data["left"][i]
                        y = data["top"][i]
                        w = data["width"][i]
                        h = data["height"][i]
                        lines.append({
                            "text": text,
                            "bbox": (x, y, x + w, y + h),
                            "confidence": conf / 100.0,
                        })
                    return lines

                print("  OCR engine: Tesseract (pytesseract)")
                return "tesseract", _run_tesseract
            except Exception:
                if preference == "tesseract":
                    print("ERROR: Tesseract not available.")
                    print("  Install: pip install pytesseract + Tesseract binary")
                    sys.exit(1)

    print("ERROR: No OCR engine available.")
    print("  Install one of:")
    print("    pip install rapidocr_onnxruntime   (recommended, no system deps)")
    print("    pip install pytesseract             (requires Tesseract binary)")
    sys.exit(1)


def _render_page_to_image(page, output_path: str, resolution: int = 200):
    """Render a pdfplumber page to a PNG image file."""
    img = page.to_image(resolution=resolution)
    img.save(output_path, format="PNG")
    return output_path


def _create_cleaned_image(original_path: str, cleaned_path: str,
                          ocr_lines: list, padding: int = 4) -> str:
    """Create a copy of the page image with text regions masked out.

    For each OCR text bounding box, samples border pixels to determine the
    local background color, then fills that region so the text is removed.
    This prevents ghosting when the image is used behind editable text overlays.

    Args:
        original_path: Path to the original page image.
        cleaned_path:  Where to save the cleaned image.
        ocr_lines:     Raw OCR results (list of dicts with 'bbox' in px coords).
        padding:       Extra pixels to expand each bbox for cleaner masking.

    Returns:
        Path to the saved cleaned image.
    """
    from PIL import Image, ImageDraw
    import numpy as np

    img = Image.open(original_path).convert("RGB")
    pixels = np.array(img)
    draw = ImageDraw.Draw(img)
    h_img, w_img = pixels.shape[:2]

    for line in ocr_lines:
        x0, y0, x1, y1 = line["bbox"]
        # Expand bbox with padding
        x0p = max(0, int(x0) - padding)
        y0p = max(0, int(y0) - padding)
        x1p = min(w_img, int(x1) + padding)
        y1p = min(h_img, int(y1) + padding)

        # Sample border pixels (2px strip around the bbox) to find local bg color
        sample_pixels = []
        border = 3
        # Top border
        ty0 = max(0, y0p - border)
        if ty0 < y0p:
            sample_pixels.append(pixels[ty0:y0p, x0p:x1p].reshape(-1, 3))
        # Bottom border
        by1 = min(h_img, y1p + border)
        if y1p < by1:
            sample_pixels.append(pixels[y1p:by1, x0p:x1p].reshape(-1, 3))
        # Left border
        lx0 = max(0, x0p - border)
        if lx0 < x0p:
            sample_pixels.append(pixels[y0p:y1p, lx0:x0p].reshape(-1, 3))
        # Right border
        rx1 = min(w_img, x1p + border)
        if x1p < rx1:
            sample_pixels.append(pixels[y0p:y1p, x1p:rx1].reshape(-1, 3))

        if sample_pixels:
            all_samples = np.concatenate(sample_pixels, axis=0)
            if len(all_samples) > 0:
                # Use median for robustness against outliers
                bg_color = tuple(int(v) for v in np.median(all_samples, axis=0))
            else:
                bg_color = (255, 255, 255)
        else:
            bg_color = (255, 255, 255)

        draw.rectangle([x0p, y0p, x1p, y1p], fill=bg_color)

    img.save(cleaned_path, format="PNG")
    return cleaned_path


def _segment_cleaned_image(cleaned_path: str, images_dir: str, page_num: int,
                           page_w_inches: float, page_h_inches: float,
                           min_region_pct: float = 0.001,
                           bg_tolerance: int = 25,
                           merge_gap_px: int = 20) -> tuple[list, str]:
    """Segment a cleaned page image into individual visual content regions.

    Detects background colors from edge pixels, creates a foreground mask,
    finds connected components, and crops each distinct visual region into
    a separate image file.

    Args:
        cleaned_path:   Path to the cleaned (text-masked) page image.
        images_dir:     Directory to save cropped region images.
        page_num:       Page number (for naming output files).
        page_w_inches:  Page width in inches (for coordinate conversion).
        page_h_inches:  Page height in inches (for coordinate conversion).
        min_region_pct: Minimum region area as fraction of total image area.
        bg_tolerance:   Max per-channel color difference to count as background.
        merge_gap_px:   Max gap in pixels to merge nearby regions.

    Returns:
        (list_of_ImageElement, bg_hex_color)
    """
    from PIL import Image
    import numpy as np
    from scipy.ndimage import label as ndimage_label

    img = Image.open(cleaned_path).convert("RGB")
    pixels = np.array(img)
    h_img, w_img = pixels.shape[:2]
    total_area = h_img * w_img
    min_area = int(total_area * min_region_pct)

    # --- 1. Detect background colors from edges ---
    border = 12
    edge_strips = []
    edge_strips.append(pixels[:border, :].reshape(-1, 3))      # top
    edge_strips.append(pixels[-border:, :].reshape(-1, 3))      # bottom
    edge_strips.append(pixels[:, :border].reshape(-1, 3))       # left
    edge_strips.append(pixels[:, -border:].reshape(-1, 3))      # right
    edge_px = np.concatenate(edge_strips, axis=0)

    # Quantize to find dominant edge colors (group within 16-value bins)
    quantized = (edge_px // 16) * 16 + 8  # bin centers
    unique_colors, counts = np.unique(quantized, axis=0, return_counts=True)
    order = np.argsort(-counts)

    # Collect bg colors covering >= 90% of edge pixels
    bg_colors = []
    cumulative = 0
    for idx in order:
        bg_colors.append(unique_colors[idx].astype(np.float64))
        cumulative += counts[idx]
        if cumulative >= len(edge_px) * 0.90:
            break

    # Primary bg color for slide background
    primary_bg = bg_colors[0].astype(int)
    bg_hex = f"{primary_bg[0]:02X}{primary_bg[1]:02X}{primary_bg[2]:02X}"

    # --- 2. Build foreground mask ---
    # A pixel is foreground if it differs from ALL detected bg colors
    fg_mask = np.ones(pixels.shape[:2], dtype=bool)
    for bg_c in bg_colors:
        diff = np.max(np.abs(pixels.astype(np.int16) - bg_c.astype(np.int16)), axis=2)
        fg_mask &= (diff > bg_tolerance)

    # --- 3. Morphological close (dilate then erode) to fill small gaps ---
    # Dilation
    dilated = fg_mask.copy()
    for _ in range(4):
        new = dilated.copy()
        new[1:, :] |= dilated[:-1, :]
        new[:-1, :] |= dilated[1:, :]
        new[:, 1:] |= dilated[:, :-1]
        new[:, :-1] |= dilated[:, 1:]
        dilated = new
    # Erosion (partial — 2 iterations to shrink back a bit)
    eroded = dilated.copy()
    for _ in range(2):
        new = eroded.copy()
        new[1:, :] &= eroded[:-1, :]
        new[:-1, :] &= eroded[1:, :]
        new[:, 1:] &= eroded[:, :-1]
        new[:, :-1] &= eroded[:, 1:]
        eroded = new

    # --- 4. Connected component analysis ---
    labeled, num_features = ndimage_label(eroded)

    # --- 5. Extract bounding boxes ---
    raw_regions = []
    for comp_id in range(1, num_features + 1):
        ys, xs = np.where(labeled == comp_id)
        area = len(ys)
        if area < min_area:
            continue
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        raw_regions.append([x0, y0, x1, y1, area])

    # --- 6. Merge nearby regions ---
    def _merge_pass(regions, gap):
        """Single pass: merge any two regions whose bboxes are within `gap` px."""
        merged = True
        while merged:
            merged = False
            new_regions = []
            used = [False] * len(regions)
            for i in range(len(regions)):
                if used[i]:
                    continue
                rx0, ry0, rx1, ry1, ra = regions[i]
                for j in range(i + 1, len(regions)):
                    if used[j]:
                        continue
                    sx0, sy0, sx1, sy1, sa = regions[j]
                    # Check if bboxes are within gap distance
                    dx = max(0, max(rx0, sx0) - min(rx1, sx1))
                    dy = max(0, max(ry0, sy0) - min(ry1, sy1))
                    if dx <= gap and dy <= gap:
                        rx0 = min(rx0, sx0)
                        ry0 = min(ry0, sy0)
                        rx1 = max(rx1, sx1)
                        ry1 = max(ry1, sy1)
                        ra += sa
                        used[j] = True
                        merged = True
                new_regions.append([rx0, ry0, rx1, ry1, ra])
                used[i] = True
            regions = new_regions
        return regions

    regions = _merge_pass(raw_regions, merge_gap_px)

    # --- 7. Crop and save each region ---
    # Sort by position: top-to-bottom, then left-to-right
    regions.sort(key=lambda r: (r[1], r[0]))

    elements = []
    for idx, (x0, y0, x1, y1, _area) in enumerate(regions):
        # Add small padding for cleaner crops
        pad = 2
        cx0 = max(0, x0 - pad)
        cy0 = max(0, y0 - pad)
        cx1 = min(w_img, x1 + pad)
        cy1 = min(h_img, y1 + pad)

        crop = img.crop((cx0, cy0, cx1, cy1))
        crop_path = os.path.join(
            images_dir, f"page_{page_num:02d}_obj_{idx + 1:02d}.png"
        )
        crop.save(crop_path, format="PNG")

        # Convert pixel coordinates to inches
        elem = ImageElement(
            x=round(cx0 / w_img * page_w_inches, 3),
            y=round(cy0 / h_img * page_h_inches, 3),
            w=round((cx1 - cx0) / w_img * page_w_inches, 3),
            h=round((cy1 - cy0) / h_img * page_h_inches, 3),
            image_file=crop_path,
        )
        elements.append(elem)

    return elements, bg_hex


def _is_image_based_page(page, text_blocks: list) -> bool:
    """Detect if a page is image-based (single full-page image, no text)."""
    if text_blocks:
        return False
    images = getattr(page, "images", [])
    if not images:
        return False
    # Check if there's a single image covering most of the page
    pw = float(page.width)
    ph = float(page.height)
    for img in images:
        iw = float(img.get("x1", 0)) - float(img.get("x0", 0))
        ih = float(img.get("bottom", 0)) - float(img.get("top", 0))
        if iw > pw * 0.8 and ih > ph * 0.8:
            return True
    return False


def _ocr_lines_to_text_blocks(ocr_lines: list, img_w_px: int, img_h_px: int,
                               page_w_inches: float, page_h_inches: float,
                               min_confidence: float = 0.5) -> list[TextBlock]:
    """Convert raw OCR lines to TextBlock objects with proper coordinates.

    Groups spatially adjacent OCR lines into logical text blocks,
    converts pixel coordinates to inches, and infers semantic roles.
    """
    if not ocr_lines:
        return []

    # Filter by confidence
    lines = [l for l in ocr_lines if l["confidence"] >= min_confidence]
    if not lines:
        return []

    # Sort by y then x
    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))

    # Convert bbox to inches
    def px_to_inches(bbox):
        x0, y0, x1, y1 = bbox
        return (
            x0 / img_w_px * page_w_inches,
            y0 / img_h_px * page_h_inches,
            x1 / img_w_px * page_w_inches,
            y1 / img_h_px * page_h_inches,
        )

    # Group lines into blocks: merge lines that are vertically close
    # and horizontally overlapping
    processed = []
    for line in lines:
        ix0, iy0, ix1, iy1 = px_to_inches(line["bbox"])
        processed.append({
            "text": line["text"],
            "x0": ix0, "y0": iy0, "x1": ix1, "y1": iy1,
            "confidence": line["confidence"],
            "bbox_px": line["bbox"],
        })

    # Grouping pass: merge vertically adjacent lines
    blocks = []
    current_block = [processed[0]]

    for pl in processed[1:]:
        last = current_block[-1]
        last_h = last["y1"] - last["y0"]
        gap = pl["y0"] - last["y1"]
        # Horizontal overlap check
        overlap_x = min(pl["x1"], last["x1"]) - max(pl["x0"], last["x0"])
        max_w = max(pl["x1"] - pl["x0"], last["x1"] - last["x0"])
        overlap_ratio = overlap_x / max_w if max_w > 0 else 0

        # Same block if: gap < 1.5x line height AND horizontal overlap > 30%
        if gap < last_h * 1.8 and gap >= -last_h * 0.3 and overlap_ratio > 0.25:
            current_block.append(pl)
        else:
            blocks.append(current_block)
            current_block = [pl]

    if current_block:
        blocks.append(current_block)

    # Convert grouped lines to TextBlock objects
    page_h_pt = page_h_inches * 72
    text_blocks = []
    for block_lines in blocks:
        bx0 = min(l["x0"] for l in block_lines)
        by0 = min(l["y0"] for l in block_lines)
        bx1 = max(l["x1"] for l in block_lines)
        by1 = max(l["y1"] for l in block_lines)

        # Estimate font size from bbox height (in points)
        # Average line height → approximate font size (0.85 factor for line spacing)
        avg_line_h_inches = sum(l["y1"] - l["y0"] for l in block_lines) / len(block_lines)
        est_font_size = avg_line_h_inches * 72 * 0.85  # inches → pt, with correction

        # Detect CJK content
        combined_text = "\n".join(l["text"] for l in block_lines)
        cjk_regex = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF]")
        has_cjk = bool(cjk_regex.search(combined_text))
        font_name = "Microsoft JhengHei" if has_cjk else "Arial"

        # Infer role
        y_ratio = by0 / page_h_inches if page_h_inches > 0 else 0
        # For OCR, we can't detect bold — pass False
        role = infer_role(est_font_size, False, y_ratio * (page_h_inches / (page_h_pt / 72)),
                          page_h_pt, combined_text)

        # Build runs (one per OCR line)
        runs = []
        for line_data in block_lines:
            runs.append(asdict(TextRun(
                text=line_data["text"],
                font_name=font_name,
                size=round(est_font_size, 1),
                bold=False,
                italic=False,
                color="262626",
            )))

        # Infer alignment from horizontal position
        center_x = (bx0 + bx1) / 2
        page_center = page_w_inches / 2
        if abs(center_x - page_center) < page_w_inches * 0.08:
            align = "center"
        elif bx0 > page_w_inches * 0.6:
            align = "right"
        else:
            align = "left"

        tb = TextBlock(
            x=round(bx0, 3),
            y=round(by0, 3),
            w=round(bx1 - bx0, 3),
            h=round(by1 - by0, 3),
            runs=runs,
            role=role,
            align=align,
        )
        text_blocks.append(tb)

    return text_blocks


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------

def extract_presentation(pdf_path: str, images_dir: str | None = None,
                         ocr_engine: str = "auto", force_ocr: bool = False,
                         min_confidence: float = 0.5) -> dict:
    """Extract full presentation structure from a PDF file.

    Automatically detects image-based PDFs (no text layer) and falls back
    to OCR (RapidOCR or Tesseract) to extract editable text with positions.

    Args:
        pdf_path: Path to the input PDF file.
        images_dir: Directory to save extracted/rendered page images.
        ocr_engine: OCR engine preference: "auto", "rapidocr", "tesseract".
        force_ocr: If True, always use OCR even if text layer exists.
        min_confidence: Minimum OCR confidence threshold (0.0-1.0).

    Returns:
        A dict representing the full presentation structure (serializable to JSON).
    """
    result = {
        "source_pdf": os.path.basename(pdf_path),
        "ocr_source": False,
        "pages": [],
    }

    all_page_images: list[list[ImageElement]] = []

    # --- First pass: try pdfplumber extraction ---
    pages_data = []
    is_image_based = False

    with pdfplumber.open(pdf_path) as pdf:
        total_text_blocks = 0
        image_based_count = 0

        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            pw = float(page.width)
            ph = float(page.height)

            print(f"  Processing page {page_num} ({pw:.0f}×{ph:.0f} pt) ...")

            text_blocks = extract_text_blocks(page)
            shapes = extract_shapes(page)
            images_meta = extract_images_metadata(page, page_num)
            tables = extract_tables_from_page(page)

            total_text_blocks += len(text_blocks)

            if _is_image_based_page(page, text_blocks):
                image_based_count += 1

            all_page_images.append(images_meta)

            pages_data.append({
                "page_num": page_num,
                "pw": pw, "ph": ph,
                "text_blocks": text_blocks,
                "shapes": shapes,
                "images_meta": images_meta,
                "tables": tables,
            })

        # Detect image-based PDF
        if force_ocr:
            is_image_based = True
            print(f"\n  --force-ocr: Forcing OCR on all {len(pdf.pages)} pages.")
        elif total_text_blocks == 0 and image_based_count == len(pdf.pages):
            is_image_based = True
            print(f"\n  ⚠ Image-based PDF detected: 0 text blocks across "
                  f"{len(pdf.pages)} pages.")
            print(f"    All {image_based_count} pages contain full-page images.")
            print(f"    Switching to OCR fallback...")
        elif total_text_blocks == 0 and image_based_count > 0:
            is_image_based = True
            print(f"\n  ⚠ Mostly image-based PDF: 0 text blocks, "
                  f"{image_based_count}/{len(pdf.pages)} image pages.")
            print(f"    Switching to OCR fallback...")

    # --- OCR pass (if needed) ---
    if is_image_based:
        result["ocr_source"] = True
        engine_name, ocr_func = _get_ocr_engine(ocr_engine)

        # Ensure images_dir exists for rendered page images
        if not images_dir:
            images_dir = os.path.join(os.path.dirname(pdf_path), "pdf_pages")
        os.makedirs(images_dir, exist_ok=True)

        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                pd = pages_data[i]
                page_num = pd["page_num"]
                pw_inches = round(pd["pw"] * PT_TO_INCH, 3)
                ph_inches = round(pd["ph"] * PT_TO_INCH, 3)

                # Render page to image
                img_path = os.path.join(images_dir, f"page_{page_num:02d}.png")
                if not os.path.exists(img_path):
                    print(f"  Rendering page {page_num} to {img_path} ...")
                    _render_page_to_image(page, img_path, resolution=200)
                else:
                    print(f"  Using existing image: {img_path}")

                # Get image dimensions
                from PIL import Image
                with Image.open(img_path) as img:
                    img_w_px, img_h_px = img.size

                # Run OCR
                print(f"  OCR page {page_num} ({engine_name}) ...")
                ocr_lines = ocr_func(img_path)
                print(f"    → {len(ocr_lines)} text lines detected")

                # Convert OCR results to TextBlocks
                ocr_text_blocks = _ocr_lines_to_text_blocks(
                    ocr_lines, img_w_px, img_h_px,
                    pw_inches, ph_inches,
                    min_confidence=min_confidence,
                )

                # Replace the empty text_blocks with OCR results
                pd["text_blocks"] = ocr_text_blocks

                # Create cleaned image with text regions masked out
                # This prevents ghosting in the PPTX output
                filtered_lines = [
                    l for l in ocr_lines
                    if l["confidence"] >= min_confidence
                ]
                if filtered_lines:
                    clean_path = os.path.join(
                        images_dir,
                        f"page_{page_num:02d}_clean.png",
                    )
                    _create_cleaned_image(img_path, clean_path, filtered_lines)
                    print(f"    → Cleaned image saved: {clean_path}")
                else:
                    clean_path = img_path

                # Segment cleaned image into individual visual objects
                print(f"    Segmenting visual objects ...")
                seg_elements, bg_hex = _segment_cleaned_image(
                    clean_path, images_dir, page_num,
                    pw_inches, ph_inches,
                )
                print(f"    → {len(seg_elements)} visual objects extracted (bg: #{bg_hex})")

                # Replace the single full-page image with segmented objects
                pd["images_meta"] = seg_elements
                pd["bg_color"] = bg_hex

    # --- Build final result ---
    for pd in pages_data:
        page_data = {
            "page_number": pd["page_num"],
            "width_inches": round(pd["pw"] * PT_TO_INCH, 3),
            "height_inches": round(pd["ph"] * PT_TO_INCH, 3),
            "elements": [],
        }

        # Include detected background color if available (from OCR segmentation)
        if "bg_color" in pd:
            page_data["bg_color"] = pd["bg_color"]

        # Add shapes first (bottom layer)
        for s in pd["shapes"]:
            page_data["elements"].append({
                "type": "shape",
                **asdict(s),
            })

        # Images
        for img in pd["images_meta"]:
            page_data["elements"].append({
                "type": "image",
                **asdict(img),
            })

        # Tables
        for tbl in pd["tables"]:
            page_data["elements"].append({
                "type": "table",
                **asdict(tbl),
            })

        # Text blocks (top layer)
        for tb in pd["text_blocks"]:
            page_data["elements"].append({
                "type": "text_block",
                **asdict(tb),
            })

        result["pages"].append(page_data)

    # Extract actual image files (only for non-OCR path)
    if images_dir and not is_image_based:
        print(f"  Extracting embedded images to {images_dir} ...")
        extracted = extract_embedded_images(pdf_path, images_dir)
        match_images_to_metadata(all_page_images, extracted)
        img_idx = 0
        for page_data in result["pages"]:
            for elem in page_data["elements"]:
                if elem["type"] == "image":
                    page_num = page_data["page_number"]
                    page_imgs = all_page_images[page_num - 1]
                    if img_idx < len(page_imgs):
                        elem["image_file"] = page_imgs[img_idx].image_file
                        img_idx += 1

    # Summary
    total_text = sum(
        1 for p in result["pages"]
        for e in p["elements"] if e["type"] == "text_block"
    )
    total_img = sum(
        1 for p in result["pages"]
        for e in p["elements"] if e["type"] == "image"
    )
    total_shapes = sum(
        1 for p in result["pages"]
        for e in p["elements"] if e["type"] == "shape"
    )
    total_tables = sum(
        1 for p in result["pages"]
        for e in p["elements"] if e["type"] == "table"
    )
    ocr_label = " (via OCR)" if is_image_based else ""
    print(f"\n  Summary: {len(result['pages'])} pages{ocr_label}, "
          f"{total_text} text blocks, {total_img} images, "
          f"{total_shapes} shapes, {total_tables} tables")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract presentation structure from PDF to JSON."
    )
    parser.add_argument("input_pdf", help="Path to the input PDF file")
    parser.add_argument("output_json", help="Path to the output JSON file")
    parser.add_argument("--images-dir", default=None,
                        help="Directory to save extracted/rendered page images")
    parser.add_argument("--ocr-engine", default="auto",
                        choices=["auto", "rapidocr", "tesseract"],
                        help="OCR engine to use for image-based PDFs (default: auto)")
    parser.add_argument("--force-ocr", action="store_true",
                        help="Force OCR even if text layer exists")
    parser.add_argument("--min-confidence", type=float, default=0.5,
                        help="Minimum OCR confidence threshold 0.0-1.0 (default: 0.5)")

    args = parser.parse_args()

    if not os.path.exists(args.input_pdf):
        print(f"ERROR: File not found: {args.input_pdf}")
        sys.exit(1)

    print(f"Extracting presentation structure from: {args.input_pdf}")
    structure = extract_presentation(
        args.input_pdf,
        images_dir=args.images_dir,
        ocr_engine=args.ocr_engine,
        force_ocr=args.force_ocr,
        min_confidence=args.min_confidence,
    )

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)

    print(f"Structure saved to: {args.output_json}")


if __name__ == "__main__":
    main()
