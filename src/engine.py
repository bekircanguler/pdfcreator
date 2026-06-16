#!/usr/bin/env python3
"""
PDF generation engine — shared between CLI (app.py) and web (web_app.py).
"""

import math
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageOps
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_W, PAGE_H = A4                  # 595.27 × 841.89 pt
IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg"})
MIN_PER_PAGE = 4
MAX_PER_PAGE = 6

def _config_path() -> Path:
    # PyInstaller onefile: dosyalar _MEIPASS altına çıkarılır
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "config.json"
    return Path(__file__).resolve().parent.parent / "config.json"

CONFIG_PATH = _config_path()

DEFAULTS: Dict[str, Any] = {
    "title": "Fotoğraf Raporu",
    "watermark_text": (
        "Fen İşleri Dairesi Başkanlığı Bakım ve Onarım Şube Müdürlüğü  "
        "Doğu İlçeleri (8 İlçe) Mezarlık ve Çevre Düzenlemeleri"
    ),
    "output_filename": "fotograf_raporu.pdf",
    "output_dir": "~/Desktop",
    "page_margin_mm": 15,
    "grid_gap_mm": 4,
    "border_color_hex": "#CCCCCC",
    "border_width_pt": 0.75,
    "title_font_size": 12,          # Times New Roman 12pt per requirements
    "page_number_font_size": 8,
    "title_color_hex": "#1A1A2E",
    "separator_color_hex": "#4A90D9",
    "separator_width_pt": 1.2,
}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> Dict[str, Any]:
    cfg = DEFAULTS.copy()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"[UYARI] config.json okunamadı: {e}")
    return cfg


def hex_rgb(hex_str: str) -> Tuple[float, float, float]:
    h = hex_str.lstrip("#")
    return int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0


# ---------------------------------------------------------------------------
# Font registration — Unicode (Turkish) support
# ---------------------------------------------------------------------------

_BODY_FONTS:  Optional[Tuple[str, str]] = None   # (regular, bold) for subtitle / UI text
_TITLE_FONTS: Optional[Tuple[str, str]] = None   # (regular, bold) for main title (TNR)

_BODY_REGULAR = [
    "/Library/Fonts/Arial Unicode.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_BODY_BOLD = [
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
_TIMES_REGULAR = [
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",   # macOS Supplemental
    "/Library/Fonts/Times New Roman.ttf",
    "C:/Windows/Fonts/times.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
]
_TIMES_BOLD = [
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/Library/Fonts/Times New Roman Bold.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
]


def _first_existing(paths: List[str]) -> Optional[str]:
    try:                                    # prefer matplotlib's bundled DejaVu if available
        import matplotlib
        mpl = Path(matplotlib.__file__).parent / "mpl-data/fonts/ttf"
        paths = [str(mpl / "DejaVuSans.ttf"), str(mpl / "DejaVuSans-Bold.ttf")] + list(paths)
    except ImportError:
        pass
    return next((p for p in paths if Path(p).exists()), None)


def _register(name_reg: str, name_bold: str,
               reg_list: List[str], bold_list: List[str],
               fallback: Tuple[str, str]) -> Tuple[str, str]:
    reg_path  = _first_existing(reg_list)
    bold_path = _first_existing(bold_list)
    if reg_path:
        try:
            pdfmetrics.registerFont(TTFont(name_reg,  reg_path))
            pdfmetrics.registerFont(TTFont(name_bold, bold_path or reg_path))
            print(f"[FONT] {name_reg}: {Path(reg_path).name}")
            return name_reg, name_bold
        except Exception as e:
            print(f"[UYARI] {name_reg} kaydı başarısız ({e})")
    print(f"[UYARI] {name_reg} bulunamadı, {fallback[0]} kullanılıyor")
    return fallback


def get_fonts() -> Tuple[str, str]:
    """Returns (regular, bold) for body/subtitle text (Arial Unicode family)."""
    global _BODY_FONTS
    if _BODY_FONTS is None:
        _BODY_FONTS = _register("BodyReg", "BodyBold",
                                _BODY_REGULAR, _BODY_BOLD,
                                ("Helvetica", "Helvetica-Bold"))
    return _BODY_FONTS


def get_title_fonts() -> Tuple[str, str]:
    """Returns (regular, bold) for main title (Times New Roman family)."""
    global _TITLE_FONTS
    if _TITLE_FONTS is None:
        _TITLE_FONTS = _register("TitleReg", "TitleBold",
                                 _TIMES_REGULAR, _TIMES_BOLD,
                                 get_fonts())              # fall back to body font
    return _TITLE_FONTS


# ---------------------------------------------------------------------------
# Text wrapping
# ---------------------------------------------------------------------------

def wrap_text(text: str, font_name: str, font_size: float,
              max_width: float) -> List[str]:
    """Splits text into lines that fit within max_width (uses pdfmetrics)."""
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if pdfmetrics.stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


# ---------------------------------------------------------------------------
# Image scanning
# ---------------------------------------------------------------------------

def scan_images(folder: str) -> List[Path]:
    return sorted(
        f for f in Path(folder).iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    )


# ---------------------------------------------------------------------------
# Analysis & layout
# ---------------------------------------------------------------------------

def get_orientation(img_path: Path) -> str:
    try:
        with Image.open(img_path) as im:
            w, h = im.size
            return "landscape" if w >= h else "portrait"
    except Exception:
        return "portrait"


def paginate(images: List[Path]) -> List[List[Path]]:
    """Balanced pagination for portrait images (4-6 per page)."""
    n = len(images)
    if n == 0:
        return []
    if n <= MAX_PER_PAGE:
        return [images]
    num_pages = math.ceil(n / MAX_PER_PAGE)
    base, rem = divmod(n, num_pages)
    sizes = [base + 1] * rem + [base] * (num_pages - rem)
    result, idx = [], 0
    for s in sizes:
        result.append(images[idx: idx + s])
        idx += s
    return result


def paginate_oriented(images: List[Path]) -> List[List[Path]]:
    """
    Orientation-aware pagination:
      - Portrait images → existing paginate() logic (4-6 per page)
      - Landscape images → 2 per page (each gets its own full-width row)

    Special case: ≤2 portrait + exactly 1 landscape → one mixed page
    (1 portrait row on top, 1 full-width landscape row on bottom).
    """
    portraits  = [p for p in images if get_orientation(p) == "portrait"]
    landscapes = [p for p in images if get_orientation(p) == "landscape"]

    # Single-page mixed layout for small collections (e.g. 2P+1L)
    if len(landscapes) == 1 and 1 <= len(portraits) <= 2:
        return [portraits + landscapes]

    pages: List[List[Path]] = []
    pages.extend(paginate(portraits))
    for i in range(0, len(landscapes), 2):
        pages.append(landscapes[i: i + 2])
    return pages


def grid_layout(page_imgs: List[Path]) -> Tuple[int, int]:
    count = len(page_imgs)
    if count <= 4:
        return 2, 2
    landscape_n = sum(1 for p in page_imgs if get_orientation(p) == "landscape")
    return (2, 3) if landscape_n * 2 >= count else (3, 2)


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

def center_crop(pil_img: Image.Image, tw: int, th: int) -> Image.Image:
    sw, sh = pil_img.size
    scale = max(tw / sw, th / sh)
    nw, nh = round(sw * scale), round(sh * scale)
    resized = pil_img.resize((nw, nh), Image.LANCZOS)
    lft, top = (nw - tw) // 2, (nh - th) // 2
    return resized.crop((lft, top, lft + tw, top + th))


_AR_THRESHOLD   = 1.4              # AR fark eşiği: üstünde letterbox tetiklenir
_LETTERBOX_BG   = (242, 242, 242)  # neredeyse beyaz nötr dolgu
_LETTERBOX_LINE = (204, 204, 204)  # #CCCCCC — mevcut border rengiyle aynı


def smart_place(pil_img: Image.Image, tw: int, th: int) -> Image.Image:
    """
    AR farkı <= _AR_THRESHOLD → center_crop (cover, mevcut davranış).
    AR farkı >  _AR_THRESHOLD → contain (letterbox): resmi tam gösterir,
      kalan alanı nötr gri dolgu ile kapatır, resim kenarına ince çerçeve çizer.
    """
    sw, sh = pil_img.size
    img_ar   = sw / sh
    cell_ar  = tw / th
    mismatch = max(img_ar / cell_ar, cell_ar / img_ar)

    if mismatch <= _AR_THRESHOLD:
        return center_crop(pil_img, tw, th)

    # Contain modu
    scale = min(tw / sw, th / sh)
    nw, nh = round(sw * scale), round(sh * scale)
    resized = pil_img.resize((nw, nh), Image.LANCZOS)

    result = Image.new("RGB", (tw, th), _LETTERBOX_BG)
    lft = (tw - nw) // 2
    top = (th - nh) // 2
    result.paste(resized, (lft, top))

    # Fotoğraf ile dolgu arasına ince ayırıcı çizgi
    ImageDraw.Draw(result).rectangle(
        [lft, top, lft + nw - 1, top + nh - 1],
        outline=_LETTERBOX_LINE,
    )
    return result


def to_reader(pil_img: Image.Image) -> ImageReader:
    buf = BytesIO()
    pil_img.convert("RGB").save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return ImageReader(buf)


# ---------------------------------------------------------------------------
# Header height calculation  (must match draw_header exactly)
# ---------------------------------------------------------------------------

# Layout constants — keep in sync with draw_header
_SUB_SIZE      = 7.5      # pt — subtitle font size
_SUB_LINE_H    = _SUB_SIZE + 3   # pt — subtitle line spacing
_SUB_GAP       = 6        # pt — gap between last subtitle line and sep-1
_SEP1_H        = 0.5      # pt — thin separator stroke
_SEP1_GAP      = 8        # pt — gap between sep-1 and first title line
_TITLE_EXTRA   = 5        # pt — extra leading per title line
_TITLE_GAP     = 7        # pt — gap between last title line and sep-2
_SEP2_H        = 1.2      # pt — bold separator stroke
_SEP2_GAP      = 7        # pt — gap below sep-2 before grid


def compute_header_height(cfg: Dict, margin: float) -> float:
    """Pre-computes total header height in points (subtitle + title + decorators)."""
    body_reg, _ = get_fonts()
    _, title_bold = get_title_fonts()
    avail_w = PAGE_W - 2 * margin

    subtitle = cfg.get("watermark_text", "")
    sub_lines = wrap_text(subtitle, body_reg, _SUB_SIZE, avail_w) if subtitle else []
    title_size: int = cfg.get("title_font_size", 12)
    title_lines = wrap_text(cfg.get("title", ""), title_bold, title_size, avail_w)

    sub_block  = _SUB_SIZE + (len(sub_lines)  - 1) * _SUB_LINE_H   if sub_lines  else 0
    title_line_h = title_size + _TITLE_EXTRA
    title_block = title_size + (len(title_lines) - 1) * title_line_h

    return (sub_block + _SUB_GAP +
            _SEP1_H  + _SEP1_GAP +
            title_block + _TITLE_GAP +
            _SEP2_H + _SEP2_GAP)


# ---------------------------------------------------------------------------
# PDF drawing helpers
# ---------------------------------------------------------------------------

def _draw_page_border(c: canvas.Canvas, margin: float) -> None:
    """
    Two-rectangle frame: outer thin gray + inner fine accent line,
    creating a classic institutional document border.
    """
    pad_out = 4   # pt outside content margin
    pad_in  = 7   # pt outside content margin (inner rect, slightly further)

    # Outer frame
    c.setStrokeColorRGB(0.72, 0.72, 0.72)
    c.setLineWidth(0.7)
    bx = margin - pad_out
    c.rect(bx, bx, PAGE_W - 2 * bx, PAGE_H - 2 * bx, fill=0, stroke=1)

    # Inner accent line (thin, colored)
    c.setStrokeColorRGB(*hex_rgb("#4A90D9"))
    c.setLineWidth(0.3)
    bx2 = margin - pad_in
    c.rect(bx2, bx2, PAGE_W - 2 * bx2, PAGE_H - 2 * bx2, fill=0, stroke=1)


def draw_header(c: canvas.Canvas, cfg: Dict, margin: float, _hdr_h: float) -> None:
    """
    Draws:
      1. Double-border page frame
      2. Subtitle / watermark (centered, faded, small)
      3. Thin gray separator
      4. Main title  (centered, Times New Roman, multi-line)
      5. Bold accent separator
    """
    body_reg, _ = get_fonts()
    _, title_bold = get_title_fonts()
    avail_w = PAGE_W - 2 * margin
    cx = PAGE_W / 2                  # horizontal center

    title_size: int = cfg.get("title_font_size", 12)
    title_line_h = title_size + _TITLE_EXTRA

    subtitle = cfg.get("watermark_text", "")
    sub_lines   = wrap_text(subtitle,      body_reg,   _SUB_SIZE,  avail_w) if subtitle else []
    title_lines = wrap_text(cfg["title"], title_bold,  title_size, avail_w)

    # ── 1. Page border ────────────────────────────────────────────────
    _draw_page_border(c, margin)

    # ── 2. Subtitle (watermark) ───────────────────────────────────────
    c.setFont(body_reg, _SUB_SIZE)
    c.setFillColorRGB(0.58, 0.58, 0.58)

    y = PAGE_H - margin - _SUB_SIZE      # first baseline (from top)
    for i, line in enumerate(sub_lines):
        c.drawCentredString(cx, y - i * _SUB_LINE_H, line)

    sub_bottom = y - (len(sub_lines) - 1) * _SUB_LINE_H if sub_lines else PAGE_H - margin

    # ── 3. Thin separator ─────────────────────────────────────────────
    sep1_y = sub_bottom - _SUB_GAP
    c.setStrokeColorRGB(0.80, 0.80, 0.80)
    c.setLineWidth(_SEP1_H)
    c.line(margin, sep1_y, PAGE_W - margin, sep1_y)

    # ── 4. Main title ─────────────────────────────────────────────────
    c.setFont(title_bold, title_size)
    c.setFillColorRGB(*hex_rgb(cfg["title_color_hex"]))

    y_title = sep1_y - _SEP1_GAP - title_size   # first title baseline
    for i, line in enumerate(title_lines):
        c.drawCentredString(cx, y_title - i * title_line_h, line)

    title_bottom = y_title - (len(title_lines) - 1) * title_line_h

    # ── 5. Bold accent separator ──────────────────────────────────────
    sep2_y = title_bottom - _TITLE_GAP
    c.setStrokeColorRGB(*hex_rgb(cfg["separator_color_hex"]))
    c.setLineWidth(_SEP2_H)
    c.line(margin, sep2_y, PAGE_W - margin, sep2_y)


def draw_page_number(c: canvas.Canvas, cur: int, total: int,
                     cfg: Dict, margin: float) -> None:
    body_reg, _ = get_fonts()
    fsize: int = cfg["page_number_font_size"]
    text = f"Sayfa {cur} / {total}"
    c.setFont(body_reg, fsize)
    c.setFillColorRGB(0.50, 0.50, 0.50)
    tw = pdfmetrics.stringWidth(text, body_reg, fsize)
    c.drawString(PAGE_W - margin - tw, margin * 0.50, text)


def _draw_cell(c: canvas.Canvas, img_path: Path,
               x: float, y: float, w: float, h: float,
               border_rgb: Tuple, cfg: Dict) -> None:
    """Renders a single image into a cell with smart_place and photo frame."""
    cw_px = round(w * 2)
    ch_px = round(h * 2)
    try:
        with Image.open(img_path) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img)
            reader  = to_reader(smart_place(pil_img, cw_px, ch_px))
        c.drawImage(reader, x, y, width=w, height=h, preserveAspectRatio=False)
    except Exception as e:
        print(f"[HATA] {img_path.name}: {e}")
        c.setFillColorRGB(0.90, 0.90, 0.90)
        c.rect(x, y, w, h, fill=1, stroke=0)
        body_reg, _ = get_fonts()
        c.setFillColorRGB(0.55, 0.55, 0.55)
        c.setFont(body_reg, 8)
        c.drawCentredString(x + w / 2, y + h / 2 - 4, "Yüklenemedi")
    c.setStrokeColorRGB(*border_rgb)
    c.setLineWidth(cfg["border_width_pt"])
    c.rect(x, y, w, h, fill=0, stroke=1)


def draw_grid(c: canvas.Canvas, page_imgs: List[Path],
              cols: int, rows: int, cfg: Dict,
              margin: float, hdr_h: float, gap: float) -> None:
    """
    Lays out images in a fixed cols×rows grid.
    Partial last rows are horizontally centred.
    Used for homogeneous pages (all portrait or all landscape).
    """
    ax, ay = margin, margin
    aw = PAGE_W - 2 * margin
    ah = PAGE_H - margin - hdr_h - margin

    cell_w = (aw - (cols - 1) * gap) / cols
    cell_h = (ah - (rows - 1) * gap) / rows
    border_rgb = hex_rgb(cfg["border_color_hex"])

    for idx, img_path in enumerate(page_imgs):
        row, col = idx // cols, idx % cols
        items_in_row = min(cols, len(page_imgs) - row * cols)
        h_off = (cols - items_in_row) * (cell_w + gap) / 2 if items_in_row < cols else 0.0
        x = ax + col * (cell_w + gap) + h_off
        y = ay + (rows - 1 - row) * (cell_h + gap)
        _draw_cell(c, img_path, x, y, cell_w, cell_h, border_rgb, cfg)


def _build_mixed_rows(portraits: List[Path], landscapes: List[Path],
                      aw: float, ah: float, gap: float) -> List[Dict]:
    """
    Splits images into typed rows and assigns proportional heights.

    Portrait rows  : 2 images per row, target cell AR = 3:4  (tall)
    Landscape rows : 2 images per row, target cell AR = 3:2  (wide)
                     1 image  per row → full page width, same target AR
    All row heights are scaled together to fill ah exactly.
    """
    p_cell_w   = (aw - gap) / 2       # portrait  2-col cell width
    l_cell_w2  = (aw - gap) / 2       # landscape 2-col cell width
    l_cell_w1  = aw                   # landscape full-width cell width

    TARGET_P_AR  = 0.75   # 3:4
    TARGET_L_AR  = 1.50   # 3:2

    rows: List[Dict] = []

    # Portrait rows (2 per row)
    for i in range(0, len(portraits), 2):
        batch = portraits[i:i + 2]
        rows.append({
            "images":    batch,
            "kind":      "portrait",
            "target_h":  p_cell_w / TARGET_P_AR,
            "cell_w":    p_cell_w,
        })

    # Landscape rows (2 per row; last single → full width)
    for i in range(0, len(landscapes), 2):
        batch = landscapes[i:i + 2]
        if len(batch) == 1:
            rows.append({
                "images":   batch,
                "kind":     "landscape_full",
                "target_h": l_cell_w1 / TARGET_L_AR,
                "cell_w":   l_cell_w1,
            })
        else:
            rows.append({
                "images":   batch,
                "kind":     "landscape_half",
                "target_h": l_cell_w2 / TARGET_L_AR,
                "cell_w":   l_cell_w2,
            })

    # Scale all rows proportionally to fill ah
    n = len(rows)
    total_target = sum(r["target_h"] for r in rows)
    total_gaps   = max(0, n - 1) * gap
    scale = (ah - total_gaps) / total_target if total_target > 0 else 1.0
    for r in rows:
        r["row_h"] = r["target_h"] * scale

    return rows


def draw_mixed_grid(c: canvas.Canvas, page_imgs: List[Path], cfg: Dict,
                    margin: float, hdr_h: float, gap: float) -> None:
    """
    Mixed-orientation layout: portrait images go into tall rows (2 per row),
    landscape images go into wide rows (2 per row, or 1 full-width).
    No image is ever forced into a cell whose orientation is opposite to its own.
    """
    ax  = margin
    aw  = PAGE_W - 2 * margin
    ah  = PAGE_H - margin - hdr_h - margin
    y_top = margin + ah          # top of grid area (reportlab: y from bottom)

    portraits  = [p for p in page_imgs if get_orientation(p) == "portrait"]
    landscapes = [p for p in page_imgs if get_orientation(p) == "landscape"]
    border_rgb = hex_rgb(cfg["border_color_hex"])

    rows = _build_mixed_rows(portraits, landscapes, aw, ah, gap)

    y_cursor = y_top   # working downward from the top
    for row in rows:
        row_h   = row["row_h"]
        cell_w  = row["cell_w"]
        images  = row["images"]
        kind    = row["kind"]
        n       = len(images)

        y_bottom = y_cursor - row_h   # bottom edge of this row (reportlab coord)

        if kind == "portrait":
            # 2 portrait cells side-by-side; single portrait is centred
            for i, img_path in enumerate(images):
                x = ax + i * (cell_w + gap)
                if n == 1:
                    x = ax + (aw - cell_w) / 2   # centre single portrait
                _draw_cell(c, img_path, x, y_bottom, cell_w, row_h, border_rgb, cfg)

        elif kind == "landscape_half":
            # 2 landscape cells side-by-side
            for i, img_path in enumerate(images):
                x = ax + i * (cell_w + gap)
                _draw_cell(c, img_path, x, y_bottom, cell_w, row_h, border_rgb, cfg)

        else:  # landscape_full
            _draw_cell(c, images[0], ax, y_bottom, aw, row_h, border_rgb, cfg)

        y_cursor -= row_h + gap


def draw_landscape_rows(c: canvas.Canvas, page_imgs: List[Path], cfg: Dict,
                        margin: float, hdr_h: float, gap: float) -> None:
    """
    Landscape-only layout: each image occupies one full-width row.

    1 image  → sized at 3:2 target AR, vertically centred in the available area.
    2 images → two equal-height rows filling the available area.
    """
    ax  = margin
    aw  = PAGE_W - 2 * margin
    ah  = PAGE_H - margin - hdr_h - margin
    border_rgb = hex_rgb(cfg["border_color_hex"])
    n = len(page_imgs)

    if n == 1:
        # Single landscape: keep natural proportion (3:2), centre vertically
        cell_h = min(aw / 1.5, ah)
        y = margin + (ah - cell_h) / 2
        _draw_cell(c, page_imgs[0], ax, y, aw, cell_h, border_rgb, cfg)
    else:
        # Two landscapes: equal-height rows, top-to-bottom
        row_h = (ah - (n - 1) * gap) / n
        y_top = margin + ah
        for i, img_path in enumerate(page_imgs):
            y = y_top - (i + 1) * row_h - i * gap
            _draw_cell(c, img_path, ax, y, aw, row_h, border_rgb, cfg)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _render_pdf(images: List[Path], cfg: Dict[str, Any], dest: Any) -> None:
    """Core render — dest can be a file path string or a BytesIO."""
    # Ensure fonts are ready before measuring
    get_fonts()
    get_title_fonts()

    margin = cfg["page_margin_mm"] * mm
    gap    = cfg["grid_gap_mm"] * mm
    hdr_h  = compute_header_height(cfg, margin)   # dynamic, based on title & subtitle

    # Orientation-aware pagination: portrait pages first, then landscape pages (2/page).
    pages = paginate_oriented(images)
    total = len(pages)

    c = canvas.Canvas(dest, pagesize=A4)
    c.setTitle(cfg["title"])

    for page_num, page_imgs in enumerate(pages, start=1):
        draw_header(c, cfg, margin, hdr_h)
        draw_page_number(c, page_num, total, cfg, margin)

        orientations = {get_orientation(p) for p in page_imgs}
        if orientations == {"landscape"}:
            draw_landscape_rows(c, page_imgs, cfg, margin, hdr_h, gap)
        elif orientations == {"portrait"}:
            cols, rows = grid_layout(page_imgs)
            draw_grid(c, page_imgs, cols, rows, cfg, margin, hdr_h, gap)
        else:
            # Fallback for any rare mixed page
            draw_mixed_grid(c, page_imgs, cfg, margin, hdr_h, gap)

        if page_num < total:
            c.showPage()

    c.save()


def build_pdf_to_buffer(images: List[Path], cfg: Dict[str, Any]) -> BytesIO:
    """Renders PDF to an in-memory buffer. Used by the web interface."""
    buf = BytesIO()
    _render_pdf(images, cfg, buf)
    buf.seek(0)
    return buf


def build_pdf(images: List[Path], cfg: Dict[str, Any]) -> str:
    """Renders PDF to disk. Used by the CLI. Returns the output path."""
    out_dir = Path(cfg["output_dir"]).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / cfg["output_filename"])
    _render_pdf(images, cfg, out_path)
    return out_path
