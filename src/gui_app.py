#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fotoğraf PDF Dönüştürücü — Modern masaüstü uygulaması
"""

import os
import sys
import math
import time
import queue
import random
import threading
from pathlib import Path

import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw, ImageOps, ImageTk

sys.path.insert(0, str(Path(__file__).parent))
from engine import load_config, scan_images, build_pdf, get_orientation, grid_layout

# ─── Tema ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

HEADER_BG   = "#1A2E4A"
PAGE_BG     = "#EEF3FF"
CARD_BG     = "#FFFFFF"
CARD_BORDER = "#D5E0F5"
STEP_BADGE  = "#2563EB"
BTN_PRIMARY = "#2563EB"
BTN_HOVER   = "#1D4ED8"
BTN_SUCCESS = "#059669"
BTN_SUC_H   = "#047857"
BTN_NEUTRAL = "#4B5563"
BTN_NEU_H   = "#374151"
TEXT_DARK   = "#0F172A"
TEXT_MID    = "#475569"
TEXT_LIGHT  = "#94A3B8"
SUCCESS     = "#059669"
ERROR       = "#DC2626"
WARN        = "#D97706"

IMAGE_FILTER = [("Fotoğraf", "*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG")]

LAYOUT_OPTIONS = [
    "Otomatik Düzen",
    "1×1  (Tam Sayfa)",
    "1×2  (Sayfada 2)",
    "2×2  (Sayfada 4)",
    "3×2  (Sayfada 6)",
    "4×2  (Sayfada 8)",
]

LAYOUT_GRID = {
    "Otomatik Düzen":   None,
    "1×1  (Tam Sayfa)": (1, 1),
    "1×2  (Sayfada 2)": (1, 2),
    "2×2  (Sayfada 4)": (2, 2),
    "3×2  (Sayfada 6)": (3, 2),
    "4×2  (Sayfada 8)": (4, 2),
}

PREVIEW_W = 300
PREVIEW_H = 424   # ≈ A4 oranı


def _safe_filename(title: str) -> str:
    invalid = r'\/:*?"<>|'
    name = "".join(c if c not in invalid else "_" for c in title)
    return name.strip(". ") or "fotograf_raporu"


# ─── Logo ────────────────────────────────────────────────────────────────────
def make_logo(size: int = 56, pil_only: bool = False):
    """Kurumsal logo: dişli çark + belge — Bakım ve Onarım teması."""
    s  = size
    sc = s / 56
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Arka plan: koyu lacivert daire
    d.ellipse([1, 1, s - 2, s - 2], fill=(26, 46, 74, 255))
    # İç ince halka
    ir = max(2, int(3 * sc))
    d.ellipse([ir + 1, ir + 1, s - ir - 2, s - ir - 2],
              outline=(50, 85, 140, 180), width=max(1, int(1 * sc)))

    cx, cy = s / 2, s / 2

    # ── Dişli çark (sol-üst bölge) ──
    gc_x = cx - int(3 * sc)
    gc_y = cy - int(4 * sc)
    r_out = int(14 * sc)
    r_inn = int(9 * sc)
    n_t   = 8
    period = 2 * math.pi / n_t
    half_tooth = period * 0.40 / 2

    gear_pts = []
    for i in range(n_t):
        base = 2 * math.pi * i / n_t - math.pi / 2
        a0 = base - period / 2 + period * 0.06
        a1 = base - half_tooth
        a2 = base + half_tooth
        a3 = base + period / 2 - period * 0.06
        for ang, r in [(a0, r_inn), (a1, r_out), (a2, r_out), (a3, r_inn)]:
            gear_pts.append((gc_x + r * math.cos(ang),
                             gc_y + r * math.sin(ang)))
    d.polygon(gear_pts, fill=(37, 99, 235, 255))

    # Dişli merkez deliği
    hole_r = max(3, int(5 * sc))
    d.ellipse([gc_x - hole_r, gc_y - hole_r, gc_x + hole_r, gc_y + hole_r],
              fill=(26, 46, 74, 255))

    # ── Belge ikonu (sağ-alt bölge, dişliyle örtüşür) ──
    doc_x = int(cx)
    doc_y = int(cy - int(1 * sc))
    doc_w = int(15 * sc)
    doc_h = int(18 * sc)
    fold  = int(5 * sc)

    # Belge gövdesi (beyaz)
    d.rectangle([doc_x, doc_y, doc_x + doc_w - fold, doc_y + doc_h],
                fill=(255, 255, 255, 245))
    d.rectangle([doc_x + doc_w - fold, doc_y + fold,
                 doc_x + doc_w, doc_y + doc_h],
                fill=(255, 255, 255, 245))
    # Katlama üçgeni (açık mavi)
    d.polygon([
        (doc_x + doc_w - fold, doc_y),
        (doc_x + doc_w, doc_y + fold),
        (doc_x + doc_w - fold, doc_y + fold),
    ], fill=(150, 185, 230, 255))

    # Belge çizgileri (mavi)
    lx1 = doc_x + max(2, int(3 * sc))
    lx2 = doc_x + doc_w - fold - max(2, int(3 * sc))
    for ly_off in [int(7 * sc), int(10 * sc), int(13 * sc), int(16 * sc)]:
        ly = doc_y + ly_off
        if ly < doc_y + doc_h - 1:
            d.line([lx1, ly, lx2, ly], fill=(37, 99, 235, 200),
                   width=max(1, int(1.2 * sc)))

    if pil_only:
        return img
    return ctk.CTkImage(light_image=img, dark_image=img, size=(s // 2, s // 2))


# ─── UI Yardımcıları ─────────────────────────────────────────────────────────
def fnt(size: int, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight="bold" if bold else "normal")


def make_card(parent, pady: tuple = (0, 10)) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=14,
                        border_width=1, border_color=CARD_BORDER)
    card.pack(fill="x", pady=pady)
    return card


def step_header(card: ctk.CTkFrame, num: str, title: str) -> None:
    row = ctk.CTkFrame(card, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=(12, 7))
    badge = ctk.CTkFrame(row, fg_color=STEP_BADGE, corner_radius=12, width=26, height=26)
    badge.pack(side="left", padx=(0, 9))
    badge.pack_propagate(False)
    ctk.CTkLabel(badge, text=num, font=fnt(11, True),
                 text_color="white").place(relx=0.5, rely=0.5, anchor="center")
    ctk.CTkLabel(row, text=title, font=fnt(13, True),
                 text_color=TEXT_DARK, anchor="w").pack(side="left")
    ctk.CTkFrame(card, fg_color=CARD_BORDER, height=1).pack(fill="x", padx=16)


def labeled_entry(card, label, placeholder="", default="") -> ctk.CTkEntry:
    row = ctk.CTkFrame(card, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=5)
    ctk.CTkLabel(row, text=label, font=fnt(11), text_color=TEXT_MID,
                 width=80, anchor="w").pack(side="left")
    ent = ctk.CTkEntry(row, placeholder_text=placeholder, font=fnt(11),
                       fg_color="#F8FAFF", border_color=CARD_BORDER,
                       border_width=1, corner_radius=8)
    ent.pack(side="left", fill="x", expand=True)
    if default:
        ent.insert(0, default)
    return ent


# ─── Önizleme Renderer ───────────────────────────────────────────────────────
def _render_page_preview(page_imgs: list, grid, crop_mode: bool,
                         title: str, pw: int, ph: int) -> Image.Image:
    """Sayfanın küçük PIL görselini üretir. Thread'de çalıştırılır."""
    # Arka plan (sayfa gölgesi)
    canvas = Image.new("RGB", (pw, ph), (210, 220, 235))
    d = ImageDraw.Draw(canvas)

    # Sayfa yüzeyi
    PAD = 4  # shadow offset
    d.rectangle([0, 0, pw - PAD - 1, ph - PAD - 1], fill=(255, 255, 255))
    d.rectangle([0, 0, pw - PAD - 1, ph - PAD - 1], outline=(180, 200, 225), width=1)

    face_w = pw - PAD
    face_h = ph - PAD
    margin = max(8, int(pw * 0.055))

    # Header bloğu
    hdr_h = max(44, int(ph * 0.115))
    hdr_bottom = margin + hdr_h

    d.rectangle([margin, margin, face_w - margin, hdr_bottom],
                fill=(245, 248, 255))

    # Alt yazı satırı (silik gri şerit)
    sy = margin + int(hdr_h * 0.20)
    d.rectangle([margin + 18, sy, face_w - margin - 18, sy + 4],
                fill=(200, 212, 228))

    # İnce ayırıcı
    sep1 = margin + int(hdr_h * 0.52)
    d.line([margin, sep1, face_w - margin, sep1], fill=(210, 220, 235), width=1)

    # Başlık (kalın şerit)
    ty = sep1 + 7
    tw = min(max(40, int(len(title) * 5.2)), face_w - margin * 2 - 30)
    tx = (face_w - margin + margin) // 2 - tw // 2
    d.rectangle([tx, ty, tx + tw, ty + 9], fill=(26, 46, 74))

    # Mavi kalın ayırıcı
    sep2 = hdr_bottom - 2
    d.line([margin, sep2, face_w - margin, sep2], fill=(74, 144, 217), width=2)

    # Grid alanı
    gap = max(3, int(pw * 0.018))
    gx = margin
    gy = hdr_bottom + gap
    gw = face_w - margin - margin
    gh = face_h - margin - gy

    if not page_imgs:
        d.rectangle([gx, gy, gx + gw, gy + gh], fill=(238, 243, 255))
        return canvas

    # Grid boyutunu belirle
    if grid is not None:
        cols, rows = grid
    else:
        n = len(page_imgs)
        orientations = set()
        for p in page_imgs:
            try:
                orientations.add(get_orientation(p))
            except Exception:
                orientations.add("portrait")
        if orientations == {"landscape"}:
            cols, rows = 1, min(n, 2)
        else:
            cols, rows = grid_layout(page_imgs)

    cols = max(1, cols)
    rows = max(1, rows)
    cell_w = (gw - (cols - 1) * gap) / cols
    cell_h = (gh - (rows - 1) * gap) / rows

    for idx, img_path in enumerate(page_imgs[: cols * rows]):
        r_idx = idx // cols
        c_idx = idx % cols
        items_in_row = min(cols, len(page_imgs) - r_idx * cols)
        x_off = (cols - items_in_row) * (cell_w + gap) / 2 if items_in_row < cols else 0
        cx_ = int(gx + c_idx * (cell_w + gap) + x_off)
        cy_ = int(gy + r_idx * (cell_h + gap))
        cw_ = max(1, int(cell_w))
        ch_ = max(1, int(cell_h))

        try:
            with Image.open(img_path) as thumb:
                thumb = ImageOps.exif_transpose(thumb)
                if crop_mode:
                    sw, sh = thumb.size
                    scale = max(cw_ / sw, ch_ / sh)
                    nw = max(1, int(sw * scale))
                    nh = max(1, int(sh * scale))
                    thumb = thumb.resize((nw, nh), Image.LANCZOS)
                    lft = (nw - cw_) // 2
                    top = (nh - ch_) // 2
                    thumb = thumb.crop((lft, top, lft + cw_, top + ch_))
                else:
                    bg = Image.new("RGB", (cw_, ch_), (242, 242, 242))
                    thumb.thumbnail((cw_, ch_), Image.LANCZOS)
                    ox = (cw_ - thumb.width) // 2
                    oy = (ch_ - thumb.height) // 2
                    bg.paste(thumb.convert("RGB"), (ox, oy))
                    thumb = bg
                canvas.paste(thumb.convert("RGB"), (cx_, cy_))
        except Exception:
            d.rectangle([cx_, cy_, cx_ + cw_, cy_ + ch_], fill=(220, 230, 245))
            # Basit kamera ikon göstergesi
            mx, my = cx_ + cw_ // 2, cy_ + ch_ // 2
            r = max(5, min(cw_, ch_) // 5)
            d.ellipse([mx - r, my - r, mx + r, my + r],
                      outline=(160, 180, 210), width=1)

        d.rectangle([cx_, cy_, cx_ + cw_ - 1, cy_ + ch_ - 1],
                    outline=(170, 195, 220), width=1)

    return canvas


# ─── Açılış Ekranı ───────────────────────────────────────────────────────────
class SplashScreen(tk.Toplevel):
    _W, _H       = 560, 340
    _BG          = "#0B1929"
    _BG_RGB      = (11, 25, 41)
    _RING_RGB    = (37, 99, 235)
    _DOT_RGB     = (28, 55, 95)
    _RMIN, _RMAX = 44, 80

    _STATUSES = [
        (0.4, "Modüller yükleniyor..."),
        (1.0, "Yazı tipleri hazırlanıyor..."),
        (1.8, "Arayüz oluşturuluyor..."),
        (2.5, "Hazır!"),
    ]

    def __init__(self, master, on_done) -> None:
        super().__init__(master)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg=self._BG)
        self._on_done = on_done
        self._t0      = time.monotonic()
        self._done    = False

        rng = random.Random(7)
        self._dots = [
            (rng.randint(12, self._W - 12),
             rng.randint(12, self._H - 12),
             rng.random() * 6.2832)
            for _ in range(22)
        ]

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{self._W}x{self._H}+{(sw-self._W)//2}+{(sh-self._H)//2}")
        self.wm_attributes("-alpha", 0.0)

        self._cv = tk.Canvas(self, width=self._W, height=self._H,
                             bg=self._BG, highlightthickness=0)
        self._cv.pack(fill="both", expand=True)

        self._cx      = self._W // 2
        self._cy_logo = int(self._H * 0.38)

        pil = make_logo(90, pil_only=True)
        self._tk_logo = ImageTk.PhotoImage(pil)
        self._cv.create_image(self._cx, self._cy_logo, image=self._tk_logo,
                              anchor="center", tags="static")
        self._cv.create_text(self._cx, int(self._H * 0.60),
                             text="Bakım ve Onarım Şube Müdürlüğü",
                             font=("", 18, "bold"), fill="#FFFFFF",
                             anchor="center", tags="static")
        self._cv.create_text(self._cx, int(self._H * 0.70),
                             text="PDF Motor V1",
                             font=("", 10), fill="#2D5A8A",
                             anchor="center", tags="static")
        self._cv.create_text(self._W - 10, self._H - 8,
                             text="© Bekircan Güler",
                             font=("", 9), fill="#1B3250",
                             anchor="se", tags="static")
        self._status_id = self._cv.create_text(
            self._cx, int(self._H * 0.82),
            text="", font=("", 10), fill="#3D6A9E",
            anchor="center", tags="static")

        self._bx = (self._W - 440) // 2
        self._by = int(self._H * 0.88)
        self._bw, self._bh = 440, 4
        self.after(16, self._tick)

    def _lerp(self, c1, c2, t) -> str:
        t = max(0.0, min(1.0, t))
        return "#{:02x}{:02x}{:02x}".format(
            int(c1[0] + (c2[0]-c1[0])*t),
            int(c1[1] + (c2[1]-c1[1])*t),
            int(c1[2] + (c2[2]-c1[2])*t))

    def _tick(self) -> None:
        if self._done:
            return
        elapsed = time.monotonic() - self._t0
        if elapsed < 0.35:
            self.wm_attributes("-alpha", elapsed / 0.35)
        prog = max(0.0, min(1.0, (elapsed - 0.35) / 2.65))
        msg = ""
        for t_trig, text in self._STATUSES:
            if elapsed >= t_trig:
                msg = text
        self._cv.itemconfigure(self._status_id, text=msg)
        self._draw(elapsed, prog)
        if elapsed >= 3.0:
            self.wm_attributes("-alpha", max(0.0, 1.0 - (elapsed - 3.0) / 0.5))
        if elapsed >= 3.5:
            self._done = True
            self.destroy()
            self._on_done()
            return
        self.after(16, self._tick)

    def _draw(self, t, prog) -> None:
        cv = self._cv
        cv.delete("anim")
        cx, cy = self._cx, self._cy_logo
        for dx, dy, ph in self._dots:
            br  = 0.22 + 0.22 * math.sin(t * 1.1 + ph)
            col = self._lerp(self._BG_RGB, self._DOT_RGB, br)
            cv.create_oval(dx-1, dy-1, dx+1, dy+1, fill=col, outline="", tags="anim")
        for k in range(3):
            ph  = ((t * 0.38) + k / 3) % 1.0
            r   = self._RMIN + ph * (self._RMAX - self._RMIN)
            f   = 1.0 - ph
            col = self._lerp(self._BG_RGB, self._RING_RGB, f * 0.65)
            w   = max(1, int(f * 2.5))
            cv.create_oval(cx-r, cy-r, cx+r, cy+r, outline=col, width=w, tags="anim")
        bx, by, bw, bh = self._bx, self._by, self._bw, self._bh
        cv.create_rectangle(bx, by, bx+bw, by+bh, fill="#112030", outline="", tags="anim")
        fw = int(bw * prog)
        if fw > 0:
            cv.create_rectangle(bx, by, bx+fw, by+bh, fill=BTN_PRIMARY, outline="", tags="anim")
        cv.tag_raise("static")


# ─── Ana Sayfa ───────────────────────────────────────────────────────────────
class HomeScreen(ctk.CTkFrame):
    def __init__(self, parent, on_navigate) -> None:
        super().__init__(parent, fg_color=PAGE_BG)
        self._nav = on_navigate
        self._build()

    def _build(self) -> None:
        # Üst başlık
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(pady=(48, 4))
        ctk.CTkLabel(hdr, text="Ne yapmak istersiniz?",
                     font=fnt(24, True), text_color=TEXT_DARK).pack()
        ctk.CTkLabel(hdr, text="Bir modül seçin",
                     font=fnt(13), text_color=TEXT_MID).pack(pady=(5, 0))

        # Kart satırı
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(expand=True, padx=50, pady=30, fill="both")
        row.columnconfigure((0, 1, 2), weight=1, uniform="col")
        row.rowconfigure(0, weight=1)

        modules = [
            ("📷", "Fotoğraf → PDF", "Fotoğraflardan profesyonel\nalbüm PDF'i oluştur", "photo", True),
            ("🔗", "PDF Birleştir",  "Birden fazla PDF'i\nbir araya getir",              "merge", True),
            ("📝", "Bilgi Notu",     "Kurumsal bilgi notu\noluştur",                     "note",  True),
        ]
        for col, (icon, title, desc, key, enabled) in enumerate(modules):
            self._make_card(row, col, icon, title, desc, key, enabled)

    def _make_card(self, parent, col, icon, title, desc, key, enabled) -> None:
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=22,
                            border_width=1, border_color=CARD_BORDER)
        card.grid(row=0, column=col, padx=14, pady=8, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(expand=True, pady=36, padx=24)

        circle_bg = BTN_PRIMARY if enabled else "#CBD5E1"
        icon_f = ctk.CTkFrame(inner, fg_color=circle_bg if not enabled else "#EEF3FF",
                               corner_radius=40, width=76, height=76)
        icon_f.pack(pady=(0, 18))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text=icon, font=fnt(30),
                     text_color=BTN_PRIMARY if enabled else TEXT_LIGHT
                     ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(inner, text=title, font=fnt(16, True),
                     text_color=TEXT_DARK if enabled else TEXT_LIGHT).pack()
        ctk.CTkLabel(inner, text=desc, font=fnt(11), text_color=TEXT_MID,
                     justify="center").pack(pady=(7, 22))

        if enabled:
            ctk.CTkButton(inner, text="Aç  →", height=42, corner_radius=21,
                          fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                          text_color="white", font=fnt(13, True),
                          command=lambda k=key: self._nav(k)).pack(fill="x")
        else:
            ctk.CTkButton(inner, text="Yakında", height=42, corner_radius=21,
                          fg_color="#E2E8F0", hover_color="#E2E8F0",
                          text_color=TEXT_LIGHT, font=fnt(13),
                          state="disabled").pack(fill="x")


# ─── Fotoğraf Modülü ─────────────────────────────────────────────────────────
class PhotoModule(ctk.CTkFrame):
    def __init__(self, parent, cfg: dict, root) -> None:
        super().__init__(parent, fg_color=PAGE_BG)
        self.cfg    = cfg
        self.root   = root
        self._images: list         = []
        self._out_path: str | None = None
        self._q: queue.Queue       = queue.Queue()
        self._pages: list          = []
        self._cur_page: int        = 0
        self._preview_job          = None
        self._preview_tk           = None
        self._build()
        self._poll()

    def _poll(self) -> None:
        try:
            while True:
                kind, data = self._q.get_nowait()
                if kind == "ok":
                    self._on_success(data)
                elif kind == "preview":
                    self._on_preview_ready(data)
                else:
                    self._on_error(data)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=PAGE_BG)
        wrap.pack(fill="both", expand=True)

        # Sol panel
        left = ctk.CTkScrollableFrame(wrap, fg_color=PAGE_BG, corner_radius=0,
                                       scrollbar_button_color=CARD_BORDER,
                                       scrollbar_button_hover_color=BTN_PRIMARY)
        left.pack(side="left", fill="both", expand=True, padx=(14, 6), pady=12)

        # Sağ panel (sabit genişlik)
        right = ctk.CTkFrame(wrap, fg_color=CARD_BG, corner_radius=16,
                             border_width=1, border_color=CARD_BORDER,
                             width=PREVIEW_W + 44)
        right.pack(side="right", fill="y", padx=(0, 14), pady=12)
        right.pack_propagate(False)

        self._build_controls(left)
        self._build_preview(right)

    def _build_controls(self, parent) -> None:
        # ── Kart 1: Fotoğraf Seç ──────────────────────────────────────────
        c1 = make_card(parent)
        step_header(c1, "1", "Fotoğraf seçin")

        btn_row = ctk.CTkFrame(c1, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(btn_row, text="📁  Klasör Seç", height=38, corner_radius=20,
                      fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                      font=fnt(11, True), command=self._pick_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="🖼  Tek Tek Seç", height=38, corner_radius=20,
                      fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                      font=fnt(11), command=self._pick_files).pack(side="left")

        info = ctk.CTkFrame(c1, fg_color="#F0F6FF", corner_radius=8,
                            border_width=1, border_color=CARD_BORDER)
        info.pack(fill="x", padx=16, pady=(0, 8))
        self._path_lbl = ctk.CTkLabel(info, text="Henüz seçim yapılmadı",
                                      font=fnt(11), text_color=TEXT_LIGHT,
                                      anchor="w", wraplength=340)
        self._path_lbl.pack(padx=12, pady=8, fill="x")

        self._count_lbl = ctk.CTkLabel(c1, text="", font=fnt(11),
                                       text_color=TEXT_MID, anchor="w")
        self._count_lbl.pack(fill="x", padx=16, pady=(0, 10))

        # ── Kart 2: Sayfa Düzeni ──────────────────────────────────────────
        c2 = make_card(parent)
        step_header(c2, "2", "Sayfa düzeni")

        layout_row = ctk.CTkFrame(c2, fg_color="transparent")
        layout_row.pack(fill="x", padx=16, pady=(10, 6))
        ctk.CTkLabel(layout_row, text="Düzen", font=fnt(11), text_color=TEXT_MID,
                     width=70, anchor="w").pack(side="left")
        self._layout_var = tk.StringVar(value=LAYOUT_OPTIONS[0])
        ctk.CTkComboBox(layout_row, values=LAYOUT_OPTIONS,
                        variable=self._layout_var, font=fnt(11),
                        state="readonly", fg_color="#F8FAFF",
                        border_color=CARD_BORDER,
                        command=self._on_layout_change).pack(side="left", fill="x", expand=True)

        crop_row = ctk.CTkFrame(c2, fg_color="transparent")
        crop_row.pack(fill="x", padx=16, pady=(4, 14))
        self._crop_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(crop_row,
                        text="Fotoğrafları hücreye tam sığdır (Kırp)",
                        variable=self._crop_var, font=fnt(11),
                        text_color=TEXT_DARK, fg_color=BTN_PRIMARY,
                        hover_color=BTN_HOVER,
                        command=self._schedule_preview).pack(side="left")

        # ── Kart 3: Rapor Bilgileri ───────────────────────────────────────
        c3 = make_card(parent)
        step_header(c3, "3", "Rapor bilgileri")
        self._title_entry = labeled_entry(c3, "Başlık",
                                          placeholder="Klasör adından otomatik gelir")
        self._title_entry.bind("<KeyRelease>", lambda e: self._schedule_preview())
        self._wm_entry = labeled_entry(c3, "Alt yazı",
                                       default=self.cfg.get("watermark_text", ""))
        ctk.CTkLabel(c3,
                     text="Başlık: her sayfada kalın  ·  Alt yazı: silik küçük",
                     font=fnt(9), text_color=TEXT_LIGHT, anchor="w").pack(
            fill="x", padx=16, pady=(4, 12))

        # ── Kart 4: PDF Oluştur ───────────────────────────────────────────
        c4 = make_card(parent, pady=(0, 4))
        step_header(c4, "4", "PDF oluşturun")

        self._btn = ctk.CTkButton(c4, text="⚡  PDF Oluştur", height=48,
                                  corner_radius=24, fg_color=BTN_PRIMARY,
                                  hover_color=BTN_HOVER, font=fnt(14, True),
                                  state="disabled", command=self._start)
        self._btn.pack(fill="x", padx=16, pady=(12, 8))
        self._btn.bind("<Enter>",
                       lambda e, c=c4: c.configure(border_color=BTN_PRIMARY, border_width=2), add="+")
        self._btn.bind("<Leave>",
                       lambda e, c=c4: c.configure(border_color=CARD_BORDER, border_width=1), add="+")

        self._progress = ctk.CTkProgressBar(c4, mode="determinate",
                                            fg_color="#DCE8FF",
                                            progress_color=BTN_PRIMARY,
                                            height=6, corner_radius=3)
        self._progress.pack(fill="x", padx=16, pady=(0, 6))
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(c4, text="", font=fnt(11), text_color=TEXT_MID)
        self._status_lbl.pack(pady=(0, 4))

        self._result_row = ctk.CTkFrame(c4, fg_color="transparent", height=42)
        self._result_row.pack(fill="x", padx=16, pady=(4, 14))

    def _build_preview(self, parent) -> None:
        ctk.CTkLabel(parent, text="Canlı Önizleme",
                     font=fnt(12, True), text_color=TEXT_DARK).pack(pady=(16, 6))

        # Canvas çerçevesi
        cv_wrap = ctk.CTkFrame(parent, fg_color="#C8D8F0", corner_radius=6)
        cv_wrap.pack(padx=10, pady=(0, 8))

        self._preview_canvas = tk.Canvas(
            cv_wrap, width=PREVIEW_W, height=PREVIEW_H,
            bg="#C8D8F0", highlightthickness=0)
        self._preview_canvas.pack(padx=3, pady=3)

        self._draw_placeholder()

        # Sayfa navigasyonu
        nav = ctk.CTkFrame(parent, fg_color="transparent")
        nav.pack(pady=(0, 16))

        self._prev_btn = ctk.CTkButton(nav, text="<", width=34, height=28,
                                        corner_radius=8, fg_color="#DCE8FF",
                                        hover_color=BTN_PRIMARY, text_color=BTN_PRIMARY,
                                        font=fnt(13, True), state="disabled",
                                        command=self._prev_page)
        self._prev_btn.pack(side="left", padx=4)

        self._page_lbl = ctk.CTkLabel(nav, text="—", font=fnt(11),
                                       text_color=TEXT_MID, width=90)
        self._page_lbl.pack(side="left")

        self._next_btn = ctk.CTkButton(nav, text=">", width=34, height=28,
                                        corner_radius=8, fg_color="#DCE8FF",
                                        hover_color=BTN_PRIMARY, text_color=BTN_PRIMARY,
                                        font=fnt(13, True), state="disabled",
                                        command=self._next_page)
        self._next_btn.pack(side="left", padx=4)

    def _draw_placeholder(self) -> None:
        cv = self._preview_canvas
        cv.delete("all")
        cv.create_rectangle(8, 8, PREVIEW_W - 4, PREVIEW_H - 4,
                            fill="white", outline="#C0CDE8", width=1)
        cv.create_text(PREVIEW_W // 2, PREVIEW_H // 2,
                       text="Fotoğraf seçince\nönizleme görünür",
                       font=("", 11), fill="#94A3B8", justify="center")

    # ── Pagination ───────────────────────────────────────────────────────────
    def _get_pages(self) -> list:
        if not self._images:
            return []
        grid = LAYOUT_GRID.get(self._layout_var.get())
        if grid is None:
            from engine import paginate_oriented
            return paginate_oriented(self._images)
        cols, rows = grid
        per = cols * rows
        return [self._images[i: i + per] for i in range(0, len(self._images), per)]

    # ── Preview scheduling ───────────────────────────────────────────────────
    def _schedule_preview(self, *_) -> None:
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(160, self._launch_preview)

    def _launch_preview(self) -> None:
        self._preview_job = None
        self._pages = self._get_pages()
        if not self._pages:
            self._cur_page = 0
            self._draw_placeholder()
            self._page_lbl.configure(text="—")
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
            return
        self._cur_page = min(self._cur_page, len(self._pages) - 1)
        self._render_async()

    def _render_async(self) -> None:
        page_imgs = self._pages[self._cur_page] if self._pages else []
        grid      = LAYOUT_GRID.get(self._layout_var.get())
        crop      = self._crop_var.get()
        title     = self._title_entry.get().strip() or "Başlık"

        def work():
            img = _render_page_preview(page_imgs, grid, crop, title, PREVIEW_W, PREVIEW_H)
            self._q.put(("preview", img))

        threading.Thread(target=work, daemon=True).start()

    def _on_preview_ready(self, pil_img: Image.Image) -> None:
        tk_img = ImageTk.PhotoImage(pil_img)
        self._preview_tk = tk_img   # referansı tut
        cv = self._preview_canvas
        cv.delete("all")
        cv.create_image(0, 0, image=tk_img, anchor="nw")

        total = len(self._pages)
        cur   = self._cur_page + 1
        self._page_lbl.configure(text=f"Sayfa {cur} / {total}")
        self._prev_btn.configure(state="normal" if cur > 1    else "disabled")
        self._next_btn.configure(state="normal" if cur < total else "disabled")

    def _prev_page(self) -> None:
        if self._cur_page > 0:
            self._cur_page -= 1
            self._render_async()

    def _next_page(self) -> None:
        if self._cur_page < len(self._pages) - 1:
            self._cur_page += 1
            self._render_async()

    def _on_layout_change(self, *_) -> None:
        self._schedule_preview()

    # ── Seçim ────────────────────────────────────────────────────────────────
    def _apply_selection(self, images: list, label: str) -> None:
        self._images   = images
        self._out_path = None
        display = label if len(label) <= 60 else "…" + label[-57:]
        self._path_lbl.configure(text=display, text_color=TEXT_DARK)
        self._clear_result()
        self._status_lbl.configure(text="")
        self._progress.set(0)
        if not images:
            self._count_lbl.configure(text="⚠  Fotoğraf bulunamadı (PNG/JPG)", text_color=WARN)
            self._btn.configure(state="disabled")
        else:
            self._count_lbl.configure(text=f"✓  {len(images)} fotoğraf seçildi", text_color=SUCCESS)
            self._btn.configure(state="normal")
        self._cur_page = 0
        self._schedule_preview()

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Fotoğrafların bulunduğu klasörü seçin",
            initialdir=str(Path.home() / "Desktop"))
        if not folder:
            return
        if not self._title_entry.get().strip():
            self._title_entry.delete(0, "end")
            self._title_entry.insert(0, Path(folder).name)
        self._apply_selection(scan_images(folder), folder)

    def _pick_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Fotoğraf dosyalarını seçin",
            filetypes=IMAGE_FILTER,
            initialdir=str(Path.home() / "Desktop"))
        if not files:
            return
        images = sorted([Path(f) for f in files])
        self._apply_selection(images, f"{len(images)} fotoğraf seçildi")

    # ── PDF Üretimi ──────────────────────────────────────────────────────────
    def _start(self) -> None:
        if not self._images:
            return
        title     = self._title_entry.get().strip() or "Fotograf Raporu"
        watermark = self._wm_entry.get().strip()
        self._btn.configure(state="disabled", text="İşleniyor...")
        self._clear_result()
        self._status_lbl.configure(text="PDF oluşturuluyor...", text_color=TEXT_MID)
        self._progress.set(0.45)

        cfg = self.cfg.copy()
        cfg["title"]           = title
        cfg["output_filename"] = _safe_filename(title) + ".pdf"
        if watermark:
            cfg["watermark_text"] = watermark
        cfg["_fixed_grid"] = LAYOUT_GRID.get(self._layout_var.get())
        cfg["_crop_mode"]  = self._crop_var.get()

        threading.Thread(target=self._run, args=(cfg,), daemon=True).start()

    def _run(self, cfg: dict) -> None:
        try:
            out = build_pdf(self._images, cfg)
            self._q.put(("ok", out))
        except Exception as exc:
            self._q.put(("err", str(exc)))

    def _on_success(self, out: str) -> None:
        self._btn.configure(state="normal", text="⚡  PDF Oluştur")
        self._progress.set(1.0)
        self._out_path = out
        self._status_lbl.configure(text=f"Kaydedildi: {Path(out).name}", text_color=SUCCESS)
        self._show_result(out)

    def _on_error(self, msg: str) -> None:
        self._btn.configure(state="normal", text="⚡  PDF Oluştur")
        self._progress.set(0)
        self._status_lbl.configure(text=f"Hata: {msg[:80]}", text_color=ERROR)
        messagebox.showerror("Hata", msg)

    def _show_result(self, out: str) -> None:
        self._clear_result()
        ctk.CTkButton(self._result_row, text="📄  PDF'i Aç", height=40,
                      corner_radius=20, fg_color=BTN_SUCCESS, hover_color=BTN_SUC_H,
                      font=fnt(12, True),
                      command=lambda: open_path(out)).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(self._result_row, text="📁  Klasörü Aç", height=40,
                      corner_radius=20, fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                      font=fnt(12),
                      command=lambda: open_path(str(Path(out).parent))).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

    def _clear_result(self) -> None:
        for w in self._result_row.winfo_children():
            w.destroy()


# ─── PDF Birleştir Modülü ─────────────────────────────────────────────────────
class MergeModule(ctk.CTkFrame):
    def __init__(self, parent, root) -> None:
        super().__init__(parent, fg_color=PAGE_BG)
        self.root      = root
        self._pdfs: list[Path]     = []
        self._out_path: str | None = None
        self._q: queue.Queue       = queue.Queue()
        self._build()
        self._poll()

    def _poll(self) -> None:
        try:
            while True:
                kind, data = self._q.get_nowait()
                if kind == "ok":
                    self._on_success(data)
                else:
                    self._on_error(data)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _build(self) -> None:
        body = ctk.CTkScrollableFrame(self, fg_color=PAGE_BG, corner_radius=0)
        body.pack(fill="both", expand=True, padx=28, pady=18)

        c1 = make_card(body)
        step_header(c1, "1", "Birleştirilecek PDF'leri seçin")

        btn_row = ctk.CTkFrame(c1, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(btn_row, text="+ PDF Ekle", height=36, corner_radius=18,
                      fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                      font=fnt(11, True), command=self._add_files).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="📂 Klasörden Ekle", height=36, corner_radius=18,
                      fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                      font=fnt(11), command=self._add_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="✕  Temizle", height=36, corner_radius=18,
                      fg_color="#E5EAF4", hover_color="#D0DAEE",
                      text_color=TEXT_MID, font=fnt(11),
                      command=self._clear_list).pack(side="right")

        self._list_outer = ctk.CTkFrame(c1, fg_color="#F0F6FF", corner_radius=10,
                                        border_width=1, border_color=CARD_BORDER)
        self._list_outer.pack(fill="x", padx=16, pady=(0, 8))
        self._render_list()

        self._count_lbl = ctk.CTkLabel(c1, text="", font=fnt(11),
                                       text_color=TEXT_MID, anchor="w")
        self._count_lbl.pack(fill="x", padx=16, pady=(0, 12))

        c2 = make_card(body)
        step_header(c2, "2", "Çıktı dosya adı")
        self._name_entry = labeled_entry(c2, "Dosya adı",
                                         placeholder="birlesik_rapor.pdf",
                                         default="birlesik_rapor.pdf")
        ctk.CTkLabel(c2, text="Masaüstüne kaydedilir",
                     font=fnt(9), text_color=TEXT_LIGHT, anchor="w").pack(
            fill="x", padx=16, pady=(2, 14))

        c3 = make_card(body, pady=(0, 4))
        step_header(c3, "3", "Birleştirin")

        self._btn_merge = ctk.CTkButton(c3, text="🔗  PDF'leri Birleştir",
                                        height=48, corner_radius=24,
                                        fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                                        font=fnt(14, True), state="disabled",
                                        command=self._start_merge)
        self._btn_merge.pack(fill="x", padx=16, pady=(12, 10))
        self._btn_merge.bind("<Enter>",
                             lambda e, c=c3: c.configure(border_color=BTN_PRIMARY, border_width=2), add="+")
        self._btn_merge.bind("<Leave>",
                             lambda e, c=c3: c.configure(border_color=CARD_BORDER, border_width=1), add="+")

        self._progress = ctk.CTkProgressBar(c3, mode="determinate",
                                            fg_color="#DCE8FF",
                                            progress_color=BTN_PRIMARY,
                                            height=6, corner_radius=3)
        self._progress.pack(fill="x", padx=16, pady=(0, 6))
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(c3, text="", font=fnt(11), text_color=TEXT_MID)
        self._status_lbl.pack(pady=(0, 4))

        self._result_row = ctk.CTkFrame(c3, fg_color="transparent", height=42)
        self._result_row.pack(fill="x", padx=16, pady=(4, 14))

    def _render_list(self) -> None:
        for w in self._list_outer.winfo_children():
            w.destroy()
        if not self._pdfs:
            ctk.CTkLabel(self._list_outer, text="Henüz PDF eklenmedi",
                         font=fnt(11), text_color=TEXT_LIGHT).pack(pady=16)
            return
        for i, path in enumerate(self._pdfs):
            self._render_row(i, path)

    def _render_row(self, i: int, path: Path) -> None:
        n   = len(self._pdfs)
        bg  = "#FFFFFF" if i % 2 == 0 else "#F5F9FF"
        row = ctk.CTkFrame(self._list_outer, fg_color=bg, corner_radius=0, height=40)
        row.pack(fill="x")
        row.pack_propagate(False)

        ctk.CTkButton(row, text="^", width=30, height=26, corner_radius=6,
                      fg_color="#DCE8FF", hover_color=BTN_PRIMARY,
                      text_color=BTN_PRIMARY, font=fnt(11, True),
                      state="disabled" if i == 0 else "normal",
                      command=lambda j=i: self._move(j, -1)).pack(side="left", padx=(8, 2), pady=7)
        ctk.CTkButton(row, text="v", width=30, height=26, corner_radius=6,
                      fg_color="#DCE8FF", hover_color=BTN_PRIMARY,
                      text_color=BTN_PRIMARY, font=fnt(11, True),
                      state="disabled" if i == n - 1 else "normal",
                      command=lambda j=i: self._move(j, +1)).pack(side="left", padx=(0, 10), pady=7)

        name = path.name if len(path.name) <= 50 else path.name[:47] + "…"
        ctk.CTkLabel(row, text=f"{i+1}.  {name}",
                     font=fnt(11), text_color=TEXT_DARK, anchor="w").pack(
            side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="✕", width=28, height=26, corner_radius=6,
                      fg_color="#EEF2FF", hover_color=ERROR,
                      text_color=TEXT_LIGHT, font=fnt(11, True),
                      command=lambda j=i: self._remove(j)).pack(side="right", padx=8, pady=7)

    def _move(self, i: int, d: int) -> None:
        j = i + d
        if 0 <= j < len(self._pdfs):
            self._pdfs[i], self._pdfs[j] = self._pdfs[j], self._pdfs[i]
            self._render_list()

    def _remove(self, i: int) -> None:
        self._pdfs.pop(i)
        self._render_list()
        self._sync_state()

    def _clear_list(self) -> None:
        self._pdfs.clear()
        self._render_list()
        self._sync_state()

    def _sync_state(self) -> None:
        n = len(self._pdfs)
        if n == 0:
            self._count_lbl.configure(text="")
            self._btn_merge.configure(state="disabled")
        elif n == 1:
            self._count_lbl.configure(text="⚠  En az 2 PDF seçin", text_color=WARN)
            self._btn_merge.configure(state="disabled")
        else:
            self._count_lbl.configure(
                text=f"✓  {n} PDF seçildi  —  ^ v butonlarıyla sıralayın",
                text_color=SUCCESS)
            self._btn_merge.configure(state="normal")

    def _add_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="PDF dosyalarını seçin",
            filetypes=[("PDF Dosyaları", "*.pdf")],
            initialdir=str(Path.home() / "Desktop"))
        if not files:
            return
        existing = set(self._pdfs)
        for f in files:
            p = Path(f)
            if p not in existing:
                self._pdfs.append(p)
                existing.add(p)
        self._render_list()
        self._sync_state()

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="PDF'lerin bulunduğu klasörü seçin",
            initialdir=str(Path.home() / "Desktop"))
        if not folder:
            return
        existing = set(self._pdfs)
        added = 0
        for p in sorted(Path(folder).glob("*.pdf")):
            if p not in existing:
                self._pdfs.append(p)
                existing.add(p)
                added += 1
        if added == 0:
            messagebox.showinfo("Klasör Boş", "Bu klasörde PDF dosyası bulunamadı.")
            return
        self._render_list()
        self._sync_state()

    def _start_merge(self) -> None:
        if len(self._pdfs) < 2:
            return
        filename = self._name_entry.get().strip() or "birlesik_rapor.pdf"
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        self._btn_merge.configure(state="disabled", text="Birleştiriliyor...")
        self._clear_result()
        self._status_lbl.configure(text="PDF'ler birleştiriliyor...", text_color=TEXT_MID)
        self._progress.set(0.45)
        threading.Thread(target=self._run_merge,
                         args=(filename, list(self._pdfs)), daemon=True).start()

    def _run_merge(self, filename: str, pdfs: list) -> None:
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            for p in pdfs:
                writer.append(str(p))
            out = str(Path.home() / "Desktop" / filename)
            with open(out, "wb") as fh:
                writer.write(fh)
            self._q.put(("ok", out))
        except BaseException as exc:
            self._q.put(("err", str(exc)))

    def _on_success(self, out: str) -> None:
        self._btn_merge.configure(state="normal", text="🔗  PDF'leri Birleştir")
        self._progress.set(1.0)
        self._status_lbl.configure(text=f"Kaydedildi: {Path(out).name}", text_color=SUCCESS)
        self._show_result(out)

    def _on_error(self, msg: str) -> None:
        self._btn_merge.configure(state="normal", text="🔗  PDF'leri Birleştir")
        self._progress.set(0)
        self._status_lbl.configure(text=f"Hata: {msg[:80]}", text_color=ERROR)
        messagebox.showerror("Birleştirme Hatası", msg)

    def _show_result(self, out: str) -> None:
        self._clear_result()
        ctk.CTkButton(self._result_row, text="📄  PDF'i Aç", height=40,
                      corner_radius=20, fg_color=BTN_SUCCESS, hover_color=BTN_SUC_H,
                      font=fnt(12, True),
                      command=lambda: open_path(out)).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(self._result_row, text="📁  Klasörü Aç", height=40,
                      corner_radius=20, fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                      font=fnt(12),
                      command=lambda: open_path(str(Path(out).parent))).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

    def _clear_result(self) -> None:
        for w in self._result_row.winfo_children():
            w.destroy()


# ─── Kullanım Kılavuzu ───────────────────────────────────────────────────────

class AciklamaEditDialog(ctk.CTkToplevel):
    """Açıklamalar alanı için büyük zengin metin editörü modal penceresi."""

    def __init__(self, module, initial_data: list) -> None:
        super().__init__(module)
        self._module = module
        W, H = 760, 540
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
        self.title("Açıklamalar — Düzenle")
        self.resizable(True, True)
        self.minsize(600, 400)
        self.configure(fg_color=PAGE_BG)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build()
        module._load_rich_text(self._text, initial_data)
        self._text.mark_set("insert", "1.0")
        self._text.focus_set()

    def _build(self) -> None:
        # Başlık
        hdr = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Açıklamalar — Düzenle",
                     font=fnt(15, True), text_color="white").place(
            relx=0.5, rely=0.5, anchor="center")

        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="#EEF3FF",
                               corner_radius=0, border_width=0)
        toolbar.pack(fill="x", padx=12, pady=(10, 0))
        inner_tb = ctk.CTkFrame(toolbar, fg_color="#EEF3FF",
                                corner_radius=7, border_width=1,
                                border_color=CARD_BORDER)
        inner_tb.pack(fill="x")

        # Metin alanı
        txt_container = ctk.CTkFrame(self, fg_color="#F8FAFF",
                                     corner_radius=8, border_width=1,
                                     border_color=CARD_BORDER)
        txt_container.pack(fill="both", expand=True, padx=12, pady=8)

        scrollbar = tk.Scrollbar(txt_container, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self._text = tk.Text(txt_container, font=("Arial", 10),
                             bg="#F8FAFF", relief="flat", wrap="word",
                             bd=0, highlightthickness=0,
                             insertbackground=BTN_PRIMARY,
                             yscrollcommand=scrollbar.set)
        self._text.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        scrollbar.configure(command=self._text.yview)

        self._text.tag_configure("bold",   font=("Arial", 10, "bold"))
        self._text.tag_configure("italic", font=("Arial", 10, "italic"))

        # Toolbar butonları
        def _fmt_toggle(tag):
            try:
                s = self._text.index("sel.first")
                e = self._text.index("sel.last")
            except tk.TclError:
                return
            ranges = self._text.tag_ranges(tag)
            has_tag = any(
                self._text.compare(rs, "<", e) and
                self._text.compare(re_, ">", s)
                for rs, re_ in zip(ranges[::2], ranges[1::2])
            )
            if has_tag:
                self._text.tag_remove(tag, s, e)
            else:
                self._text.tag_add(tag, s, e)

        def _toggle_bullet():
            idx      = self._text.index("insert")
            line_no  = idx.split(".")[0]
            ls       = f"{line_no}.0"
            line_txt = self._text.get(ls, f"{line_no}.end")
            if line_txt.startswith("• "):
                self._text.delete(ls, f"{ls}+2c")
            else:
                self._text.insert(ls, "• ")
            return "break"

        for label, cmd, kbind, bold_lbl in [
            ("B",  lambda: _fmt_toggle("bold"),   "<Control-b>", True),
            ("I",  lambda: _fmt_toggle("italic"), "<Control-i>", False),
            ("•",  _toggle_bullet,                "<Control-l>", False),
        ]:
            ctk.CTkButton(inner_tb, text=label, width=30, height=22,
                          corner_radius=5, fg_color="#DCE8FF",
                          hover_color=BTN_PRIMARY, text_color=BTN_PRIMARY,
                          font=fnt(10, bold_lbl),
                          command=cmd).pack(side="left", padx=(4, 0), pady=3)

            def _bind_handler(e, _cmd=cmd):
                _cmd()
                return "break"
            self._text.bind(kbind, _bind_handler)

        ctk.CTkLabel(inner_tb, text="Ctrl+B  Ctrl+I  Ctrl+L",
                     font=fnt(8), text_color=TEXT_LIGHT).pack(
            side="right", padx=8)

        self._text.bind("<Control-Return>", lambda e: self._on_save())

        # Alt butonlar
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(footer, text="Kaydet", width=160, height=38,
                      corner_radius=19, fg_color=BTN_SUCCESS,
                      hover_color=BTN_SUC_H, font=fnt(12, True),
                      command=self._on_save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(footer, text="İptal", width=120, height=38,
                      corner_radius=19, fg_color=BTN_NEUTRAL,
                      hover_color=BTN_NEU_H, font=fnt(12),
                      command=self._on_cancel).pack(side="left")

    def _on_save(self) -> None:
        data = self._module._serialize_rich_text(self._text)
        self._module._load_rich_text(self._module._acik_text, data, readonly=True)
        self._module._acik_text.configure(state="normal")
        lines = int(self._module._acik_text.index("end-1c").split(".")[0])
        self._module._acik_text.configure(
            height=max(5, min(18, lines)), state="disabled")
        self.destroy()

    def _on_cancel(self) -> None:
        self.destroy()


class HelpDialog(ctk.CTkToplevel):
    _CONTENT = [
        ("📋  Genel İşleyiş", None),
        (None, "Formu doldurup 'Word + PDF Üret' butonuna bastığınızda hem PDF hem Word (.docx) otomatik olarak masaüstüne kaydedilir."),

        ("📝  1 — Temel Bilgiler", None),
        (None, "Konu  (zorunlu)\nBelgenin başlık konusu. Konu adından dosya adı otomatik oluşturulur."),
        (None, "Açıklamalar  (zorunlu)\nSaha ve teknik detayların yazıldığı alan. Kutuya tıklayınca büyük editör penceresi açılır.\nEditörde:\n  B  →  Kalın  |  I  →  İtalik  |  •  →  Madde işareti\nKısayollar: Ctrl+B / Ctrl+I / Ctrl+L  |  Ctrl+Enter → Kaydet"),
        (None, "Talep Eden Birim  (isteğe bağlı)\nTalebi oluşturan birimin adı. İşaretlenmezse belgede yer almaz."),

        ("💰  2 — Maliyet ve Kapsam", None),
        (None, "Disiplin Seçimi\nListeden ilgili disiplini işaretleyin — detay alanı açılır. Birden fazla disiplin seçilebilir."),
        (None, "KDV Hariç Tutar\nOndalık için virgül kullanın:  150.000,00\nKDV Dahil Toplam (%20) tablonun altında ayrı satır olarak gösterilir."),
        (None, "Alt Kalemler\nBir disiplin içinde birden fazla iş kalemi varsa '+ Alt Kalem Ekle' butonuyla ayrı satırlar oluşturabilirsiniz. Alt kalemler girilince ana tutar otomatik toplanır; elle düzenlenemez hâle gelir."),
        (None, "Özel Disiplin\nListede olmayan bir kalem için en alttaki 'Yeni Disiplin' kutusuna yazıp Ekle'ye basın veya Enter'a basın."),
        (None, "Toplam Satırı\nBirden fazla disiplin seçildiğinde tablonun altında TOPLAM satırı otomatik eklenir."),

        ("📷  3 — Fotoğraflar", None),
        (None, "Klasör seçince içindeki tüm JPG/PNG dosyalar eklenir. Sağ paneldeki önizleme fotoğraf düzenini anlık gösterir. Düzen açılır menüsünden sayfa başına fotoğraf adedi belirlenebilir."),

        ("📎  4 — Harici PDF Ekleri", None),
        (None, "Harita, vaziyet planı, keşif cetveli gibi hazır belgeler son sayfalara eklenir. '+ PDF Ekle' ile seçilen dosyalar sıraya göre eklenir."),

        ("📅  5 — Tarih ve Düzenleyen", None),
        (None, "PDF'de fotoğraflardan hemen önce, sağa hizalı biçimde yer alır. Tarih bugünün tarihiyle otomatik doldurulur; GG.AA.YYYY formatında değiştirilebilir."),

        ("💡  İpuçları", None),
        (None, "• Açıklamalar kutusuna tıklayınca büyük editör açılır; Kaydet'le önizlemeye döner.\n• Maliyet tablosunda uzun alt kalem adları için satır yüksekliği otomatik genişler.\n• Çıktılar otomatik olarak masaüstüne kaydedilir.\n• Konu ve Açıklamalar alanları boş bırakılırsa belge üretilemez."),
    ]

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("Kullanım Kılavuzu")
        W, H = 640, 560
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=PAGE_BG)
        self._build()

    def _build(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Bilgi Notu — Kullanım Kılavuzu",
                     font=fnt(15, True), text_color="white").place(
            relx=0.5, rely=0.5, anchor="center")

        scroll = ctk.CTkScrollableFrame(self, fg_color=PAGE_BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=18, pady=(10, 0))

        for heading, body in self._CONTENT:
            if heading:
                ctk.CTkLabel(scroll, text=heading, font=fnt(12, True),
                             text_color=BTN_PRIMARY, anchor="w").pack(
                    fill="x", pady=(14, 2))
                ctk.CTkFrame(scroll, fg_color=BTN_PRIMARY, height=1).pack(
                    fill="x", pady=(0, 5))
            else:
                card = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=8,
                                    border_width=1, border_color=CARD_BORDER)
                card.pack(fill="x", pady=(0, 5))
                ctk.CTkLabel(card, text=body, font=fnt(10),
                             text_color=TEXT_DARK, anchor="nw",
                             justify="left", wraplength=570).pack(
                    padx=12, pady=8, anchor="w")

        ctk.CTkButton(self, text="Kapat", height=38, corner_radius=19,
                      fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                      font=fnt(12, True), command=self.destroy).pack(
            pady=12, padx=80, fill="x")


# ─── Bilgi Notu Modülü ───────────────────────────────────────────────────────

# ─── Maliyet yardımcıları ────────────────────────────────────────────────────
def _parse_tl(text: str) -> float:
    """'150.000,50 TL' → 150000.5  (Türkçe format)"""
    t = text.strip().upper().replace(" TL", "").replace("₺", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(".", "")
    try:
        return float(t) if t else 0.0
    except ValueError:
        return 0.0


def _format_tl(value: float) -> str:
    """150000.5 → '150.000,50 TL'"""
    if value == 0:
        return ""
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " TL"


DISCIPLINES_DEFAULT = [
    "İnşaat İşleri",
    "Elektrik İşleri",
    "Mekanik / Tesisat İşleri",
    "Saha Ekipleri",
]

NOTE_LAYOUT_OPTIONS = [
    "Otomatik Düzen",
    "1×2  (Sayfada 2)",
    "2×2  (Sayfada 4)",
    "3×2  (Sayfada 6)",
]
NOTE_LAYOUT_GRID = {
    "Otomatik Düzen":   None,
    "1×2  (Sayfada 2)": (1, 2),
    "2×2  (Sayfada 4)": (2, 2),
    "3×2  (Sayfada 6)": (3, 2),
}


class NoteModule(ctk.CTkFrame):

    def __init__(self, parent, root) -> None:
        super().__init__(parent, fg_color=PAGE_BG)
        self.root     = root
        self._q       = queue.Queue()
        self._images  = []        # List[Path] — seçili fotoğraflar
        self._ext_pdfs = []       # List[str]
        self._disc_vars       = {}   # name → BooleanVar
        self._disc_rows       = {}   # name → detail frame
        self._disc_entries    = {}   # name → {maliyet, kapsam, alt_isi}
        self._custom_disciplines: list = []
        self._disc_card       = None
        self._preview_job  = None
        self._preview_tk   = None
        self._pages        = []
        self._cur_page     = 0
        self._build()
        self._poll()

    def _poll(self) -> None:
        try:
            while True:
                kind, data = self._q.get_nowait()
                if kind == "ok":
                    self._on_success(data)
                elif kind == "preview":
                    self._on_preview_ready(data)
                else:
                    self._on_error(data)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    # ── Ana layout ───────────────────────────────────────────────────────────
    def _build(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=PAGE_BG)
        wrap.pack(fill="both", expand=True)

        # Sol panel (form)
        left = ctk.CTkScrollableFrame(wrap, fg_color=PAGE_BG, corner_radius=0,
                                       scrollbar_button_color=CARD_BORDER,
                                       scrollbar_button_hover_color=BTN_PRIMARY)
        left.pack(side="left", fill="both", expand=True, padx=(14, 6), pady=12)

        # Sağ panel (fotoğraf önizleme — PhotoModule ile aynı)
        right = ctk.CTkFrame(wrap, fg_color=CARD_BG, corner_radius=16,
                             border_width=1, border_color=CARD_BORDER,
                             width=PREVIEW_W + 44)
        right.pack(side="right", fill="y", padx=(0, 14), pady=12)
        right.pack_propagate(False)

        self._left_scroll = left
        self._build_form(left)
        self._build_photo_panel(right)

    # ── Sol form ─────────────────────────────────────────────────────────────
    def _show_help(self) -> None:
        HelpDialog(self)

    def _build_form(self, parent) -> None:
        # Kılavuz butonu
        _hr = ctk.CTkFrame(parent, fg_color="transparent")
        _hr.pack(fill="x", padx=16, pady=(6, 2))
        ctk.CTkButton(_hr, text="ℹ  Kullanım Kılavuzu", width=170, height=26,
                      corner_radius=13, fg_color="#EEF3FF", hover_color="#DCE8FF",
                      text_color=BTN_PRIMARY, font=fnt(10),
                      command=self._show_help).pack(side="right")

        # ── Kart 1: Temel Bilgiler ────────────────────────────────────────
        c1 = make_card(parent)
        step_header(c1, "1", "Temel Bilgiler")

        konu_row = ctk.CTkFrame(c1, fg_color="transparent")
        konu_row.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(konu_row, text="Konu", font=fnt(11, True),
                     text_color=TEXT_DARK, width=110, anchor="w").pack(side="left")
        self._konu_entry = ctk.CTkEntry(konu_row, font=fnt(11),
                                         fg_color="#F8FAFF", border_color=CARD_BORDER,
                                         border_width=1, corner_radius=8,
                                         placeholder_text="Bilgi notunun konusu...")
        self._konu_entry.pack(side="left", fill="x", expand=True)

        # Açıklamalar — zengin metin editörü
        acik_row = ctk.CTkFrame(c1, fg_color="transparent")
        acik_row.pack(fill="x", padx=16, pady=(4, 4))
        ctk.CTkLabel(acik_row, text="Açıklamalar", font=fnt(11, True),
                     text_color=TEXT_DARK, width=110, anchor="nw").pack(
            side="left", anchor="n", pady=4)

        editor_col = ctk.CTkFrame(acik_row, fg_color="transparent")
        editor_col.pack(side="left", fill="x", expand=True, pady=2)

        # Metin kutusu (salt-okunur önizleme — düzenlemek için tıklanır)
        txt_wrap = ctk.CTkFrame(editor_col, fg_color="#F8FAFF",
                                corner_radius=8, border_width=1, border_color=CARD_BORDER)
        txt_wrap.pack(fill="x", expand=True)
        self._acik_text = tk.Text(txt_wrap, height=5, font=("Arial", 9),
                                   bg="#F8FAFF", relief="flat",
                                   wrap="word", bd=0, highlightthickness=0,
                                   cursor="hand2", state="disabled")
        self._acik_text.pack(fill="both", expand=True, padx=6, pady=4)

        self._acik_text.tag_configure("bold",   font=("Arial", 9, "bold"))
        self._acik_text.tag_configure("italic", font=("Arial", 9, "italic"))

        self._acik_text.bind("<Button-1>", lambda e: self._open_rich_text_modal())

        ctk.CTkLabel(editor_col, text="✎  Düzenlemek için tıklayın",
                     font=fnt(8), text_color=TEXT_LIGHT).pack(anchor="w", padx=2)

        def _acik_wheel(event):
            top, bottom = self._acik_text.yview()
            if top == 0.0 and bottom == 1.0:
                self._left_scroll._parent_canvas.yview_scroll(
                    -1 if event.delta > 0 else 1, "units")
                return "break"

        self._acik_text.bind("<MouseWheel>", _acik_wheel)

        # Talep Eden Birim
        talep_frame = ctk.CTkFrame(c1, fg_color="transparent")
        talep_frame.pack(fill="x", padx=16, pady=(6, 4))
        self._talep_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(talep_frame, text="Talep Eden Birim Var",
                        variable=self._talep_var, font=fnt(11),
                        text_color=TEXT_DARK, fg_color=BTN_PRIMARY,
                        hover_color=BTN_HOVER,
                        command=self._toggle_talep).pack(anchor="w")
        self._talep_sub = ctk.CTkFrame(c1, fg_color="#F0F6FF",
                                        corner_radius=8, border_width=1,
                                        border_color=CARD_BORDER)
        self._talep_sub.pack(fill="x", padx=32, pady=(2, 10))
        ctk.CTkLabel(self._talep_sub, text="Birim Adı", font=fnt(10),
                     text_color=TEXT_MID, width=80, anchor="w").pack(
            side="left", padx=(10, 4), pady=6)
        self._talep_entry = ctk.CTkEntry(self._talep_sub, font=fnt(11),
                                          fg_color="white", border_color=CARD_BORDER,
                                          border_width=1, corner_radius=8,
                                          placeholder_text="Talep eden birimin adı...")
        self._talep_entry.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=6)

        # ── Kart 2: Maliyet ve Kapsam ─────────────────────────────────────
        c2 = make_card(parent)
        self._disc_card = c2
        step_header(c2, "2", "Maliyet ve Kapsam")
        ctk.CTkLabel(c2, text="Disiplin seçin — seçilen her disiplin için alanları doldurun",
                     font=fnt(9), text_color=TEXT_LIGHT, anchor="w").pack(
            fill="x", padx=16, pady=(6, 4))
        for disc_name in DISCIPLINES_DEFAULT:
            self._add_discipline_row(c2, disc_name)

        # Tercihe bağlı yeni disiplin ekleme satırı
        add_disc_row = ctk.CTkFrame(c2, fg_color="#F8FAFF", corner_radius=8,
                                    border_width=1, border_color=CARD_BORDER)
        add_disc_row.pack(fill="x", padx=16, pady=(8, 12))
        ctk.CTkLabel(add_disc_row, text="+ Yeni Disiplin:", font=fnt(10),
                     text_color=TEXT_MID, width=100, anchor="w").pack(
            side="left", padx=(10, 4), pady=8)
        self._new_disc_entry = ctk.CTkEntry(add_disc_row, font=fnt(11),
                                             fg_color="white", border_color=CARD_BORDER,
                                             border_width=1, corner_radius=7,
                                             placeholder_text="Ör: Peyzaj İşleri...")
        self._new_disc_entry.pack(side="left", fill="x", expand=True, pady=8)
        self._new_disc_entry.bind("<Return>", lambda e: self._add_custom_discipline())
        ctk.CTkButton(add_disc_row, text="Ekle", width=70, height=30,
                      corner_radius=15, fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                      font=fnt(11, True),
                      command=self._add_custom_discipline).pack(
            side="right", padx=(6, 10), pady=8)

        # ── Kart 3: Fotoğraf Seç ─────────────────────────────────────────
        c3 = make_card(parent)
        step_header(c3, "3", "Fotoğraf Seçin")

        btn_row = ctk.CTkFrame(c3, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(btn_row, text="📁  Klasör Seç", height=36, corner_radius=18,
                      fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                      font=fnt(11, True), command=self._pick_photo_folder).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="🖼  Tek Tek Seç", height=36, corner_radius=18,
                      fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                      font=fnt(11), command=self._pick_photo_files).pack(side="left")

        info_box = ctk.CTkFrame(c3, fg_color="#F0F6FF", corner_radius=8,
                                border_width=1, border_color=CARD_BORDER)
        info_box.pack(fill="x", padx=16, pady=(0, 6))
        self._photo_path_lbl = ctk.CTkLabel(info_box, text="Henüz seçim yapılmadı",
                                             font=fnt(10), text_color=TEXT_LIGHT,
                                             anchor="w", wraplength=320)
        self._photo_path_lbl.pack(padx=10, pady=6, fill="x")
        self._photo_count_lbl = ctk.CTkLabel(c3, text="", font=fnt(10),
                                              text_color=TEXT_MID, anchor="w")
        self._photo_count_lbl.pack(fill="x", padx=16, pady=(0, 4))

        # Düzen
        layout_row = ctk.CTkFrame(c3, fg_color="transparent")
        layout_row.pack(fill="x", padx=16, pady=(2, 4))
        ctk.CTkLabel(layout_row, text="Fotoğraf Düzeni", font=fnt(10), text_color=TEXT_MID,
                     width=110, anchor="w").pack(side="left")
        self._note_layout_var = tk.StringVar(value=NOTE_LAYOUT_OPTIONS[0])
        ctk.CTkComboBox(layout_row, values=NOTE_LAYOUT_OPTIONS,
                        variable=self._note_layout_var, font=fnt(10),
                        state="readonly", fg_color="#F8FAFF", border_color=CARD_BORDER,
                        command=self._schedule_preview).pack(side="left", fill="x", expand=True)

        crop_row = ctk.CTkFrame(c3, fg_color="transparent")
        crop_row.pack(fill="x", padx=16, pady=(2, 12))
        self._note_crop_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(crop_row, text="Fotoğrafları hücreye tam sığdır (Kırp)",
                        variable=self._note_crop_var, font=fnt(10),
                        text_color=TEXT_DARK, fg_color=BTN_PRIMARY,
                        hover_color=BTN_HOVER,
                        command=self._schedule_preview).pack(side="left")

        # ── Kart 4: Harici PDF ────────────────────────────────────────────
        c4 = make_card(parent)
        step_header(c4, "4", "Harici PDF Ekleri")
        ext_top = ctk.CTkFrame(c4, fg_color="transparent")
        ext_top.pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(ext_top, text="Harita, plan vb. PDF'ler son sayfaya eklenir",
                     font=fnt(9), text_color=TEXT_LIGHT, anchor="w").pack(side="left")
        ctk.CTkButton(ext_top, text="📎  PDF Ekle", width=100, height=28,
                      corner_radius=14, fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                      font=fnt(10), command=self._add_ext_pdf).pack(side="right")
        self._ext_pdf_frame = ctk.CTkFrame(c4, fg_color="#F0F6FF",
                                            corner_radius=8, border_width=1,
                                            border_color=CARD_BORDER)
        self._ext_pdf_frame.pack(fill="x", padx=16, pady=(4, 12))
        self._render_ext_list()

        # ── Kart 5: Tarih ve Düzenleyen ──────────────────────────────────
        c_dt = make_card(parent)
        step_header(c_dt, "5", "Tarih ve Düzenleyen")

        duz_row = ctk.CTkFrame(c_dt, fg_color="transparent")
        duz_row.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(duz_row, text="Düzenleyen", font=fnt(11, True),
                     text_color=TEXT_DARK, width=110, anchor="w").pack(side="left")
        self._duzenleyen_entry = ctk.CTkEntry(duz_row, font=fnt(11),
                                               fg_color="#F8FAFF", border_color=CARD_BORDER,
                                               border_width=1, corner_radius=8,
                                               placeholder_text="Ad Soyad (ör: Bekircan Güler)")
        self._duzenleyen_entry.pack(side="left", fill="x", expand=True)

        tarih_row = ctk.CTkFrame(c_dt, fg_color="transparent")
        tarih_row.pack(fill="x", padx=16, pady=(4, 12))
        ctk.CTkLabel(tarih_row, text="Tarih", font=fnt(11, True),
                     text_color=TEXT_DARK, width=110, anchor="w").pack(side="left")
        self._tarih_entry = ctk.CTkEntry(tarih_row, font=fnt(11),
                                          fg_color="#F8FAFF", border_color=CARD_BORDER,
                                          border_width=1, corner_radius=8, width=140)
        self._tarih_entry.pack(side="left")
        from datetime import date as _date
        self._tarih_entry.insert(0, _date.today().strftime("%d.%m.%Y"))
        ctk.CTkLabel(tarih_row, text="  (GG.AA.YYYY formatında)", font=fnt(9),
                     text_color=TEXT_LIGHT).pack(side="left")

        # ── Kart 6: Üret ─────────────────────────────────────────────────
        c5 = make_card(parent, pady=(0, 4))
        step_header(c5, "6", "Raporu Üret")
        self._gen_btn = ctk.CTkButton(c5, text="📄  Word + PDF Üret",
                                       height=50, corner_radius=25,
                                       fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                                       font=fnt(15, True), command=self._start)
        self._gen_btn.pack(fill="x", padx=16, pady=(14, 8))
        self._gen_btn.bind("<Enter>",
                           lambda e, fr=c5: fr.configure(border_color=BTN_PRIMARY, border_width=2),
                           add="+")
        self._gen_btn.bind("<Leave>",
                           lambda e, fr=c5: fr.configure(border_color=CARD_BORDER, border_width=1),
                           add="+")
        self._progress = ctk.CTkProgressBar(c5, mode="determinate",
                                             fg_color="#DCE8FF", progress_color=BTN_PRIMARY,
                                             height=6, corner_radius=3)
        self._progress.pack(fill="x", padx=16, pady=(0, 6))
        self._progress.set(0)
        self._status_lbl = ctk.CTkLabel(c5, text="", font=fnt(11), text_color=TEXT_MID)
        self._status_lbl.pack(pady=(0, 4))
        self._result_row = ctk.CTkFrame(c5, fg_color="transparent", height=42)
        self._result_row.pack(fill="x", padx=16, pady=(4, 14))

    # ── Sağ panel: fotoğraf önizleme (PhotoModule ile aynı yapı) ─────────────
    def _build_photo_panel(self, parent) -> None:
        ctk.CTkLabel(parent, text="Fotoğraf Önizleme",
                     font=fnt(12, True), text_color=TEXT_DARK).pack(pady=(16, 6))
        cv_wrap = ctk.CTkFrame(parent, fg_color="#C8D8F0", corner_radius=6)
        cv_wrap.pack(padx=10, pady=(0, 8))
        self._preview_canvas = tk.Canvas(
            cv_wrap, width=PREVIEW_W, height=PREVIEW_H,
            bg="#C8D8F0", highlightthickness=0)
        self._preview_canvas.pack(padx=3, pady=3)
        self._draw_placeholder()

        nav = ctk.CTkFrame(parent, fg_color="transparent")
        nav.pack(pady=(0, 16))
        self._prev_btn = ctk.CTkButton(nav, text="<", width=34, height=28,
                                        corner_radius=8, fg_color="#DCE8FF",
                                        hover_color=BTN_PRIMARY, text_color=BTN_PRIMARY,
                                        font=fnt(13, True), state="disabled",
                                        command=self._prev_page)
        self._prev_btn.pack(side="left", padx=4)
        self._page_lbl = ctk.CTkLabel(nav, text="—", font=fnt(11),
                                       text_color=TEXT_MID, width=90)
        self._page_lbl.pack(side="left")
        self._next_btn = ctk.CTkButton(nav, text=">", width=34, height=28,
                                        corner_radius=8, fg_color="#DCE8FF",
                                        hover_color=BTN_PRIMARY, text_color=BTN_PRIMARY,
                                        font=fnt(13, True), state="disabled",
                                        command=self._next_page)
        self._next_btn.pack(side="left", padx=4)

    def _draw_placeholder(self) -> None:
        cv = self._preview_canvas
        cv.delete("all")
        cv.create_rectangle(8, 8, PREVIEW_W - 4, PREVIEW_H - 4,
                            fill="white", outline="#C0CDE8", width=1)
        cv.create_text(PREVIEW_W // 2, PREVIEW_H // 2,
                       text="Fotoğraf seçince\nönizleme görünür",
                       font=("", 11), fill="#94A3B8", justify="center")

    # ── Talep toggle ──────────────────────────────────────────────────────────
    def _toggle_talep(self) -> None:
        if self._talep_var.get():
            self._talep_sub.pack(fill="x", padx=32, pady=(2, 10))
        else:
            self._talep_sub.pack_forget()

    # ── Disiplin satırları ────────────────────────────────────────────────────
    def _add_discipline_row(self, parent, name) -> None:
        var = tk.BooleanVar(value=False)
        self._disc_vars[name] = var

        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", padx=16, pady=2)
        ctk.CTkCheckBox(outer, text=name, variable=var, font=fnt(11),
                        text_color=TEXT_DARK, fg_color=BTN_PRIMARY,
                        hover_color=BTN_HOVER,
                        command=lambda n=name: self._toggle_disc(n)).pack(anchor="w", pady=2)

        detail = ctk.CTkFrame(parent, fg_color="#F0F6FF",
                               corner_radius=8, border_width=1, border_color=CARD_BORDER)
        self._disc_rows[name] = detail

        # ── Satır 1: KDV Hariç + KDV Dahil (auto) ──────────────────────────
        r2 = ctk.CTkFrame(detail, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(r2, text="KDV Hariç Tutar", font=fnt(10), text_color=TEXT_MID,
                     width=110, anchor="w").pack(side="left")
        mal = ctk.CTkEntry(r2, font=fnt(11), width=170,
                           fg_color="white", border_color=CARD_BORDER,
                           border_width=1, corner_radius=7,
                           placeholder_text="Ör: 150.000,00")
        mal.pack(side="left", padx=(0, 10))
        dahil_lbl = ctk.CTkLabel(r2, text="→ KDV Dahil: —",
                                  font=fnt(10), text_color=BTN_PRIMARY, anchor="w")
        dahil_lbl.pack(side="left")

        def _update_kdv(*_, _mal=mal, _lbl=dahil_lbl, _n=name):
            ak_list = self._disc_entries.get(_n, {}).get("alt_kalemler", [])
            if ak_list:
                return   # alt kalemler varsa toplamı onlar belirler
            v = _parse_tl(_mal.get())
            if v:
                _lbl.configure(text=f"→ KDV Dahil: {_format_tl(v * 1.2)}")
                self._disc_entries[_n]["maliyet_dahil_val"] = v * 1.2
                self._disc_entries[_n]["maliyet_hariç_val"] = v
            else:
                _lbl.configure(text="→ KDV Dahil: —")
                self._disc_entries[_n]["maliyet_dahil_val"] = 0.0
                self._disc_entries[_n]["maliyet_hariç_val"] = 0.0

        mal.bind("<KeyRelease>", _update_kdv)
        mal.bind("<FocusOut>", _update_kdv)

        # ── Satır 3: Alt Kalemler ────────────────────────────────────────────
        alt_header = ctk.CTkFrame(detail, fg_color="transparent")
        alt_header.pack(fill="x", padx=10, pady=(2, 2))
        ctk.CTkLabel(alt_header, text="Alt Kalemler (isteğe bağlı)",
                     font=fnt(9), text_color=TEXT_LIGHT, anchor="w").pack(side="left")
        alt_kalemler_list: list = []

        alt_frame = ctk.CTkFrame(detail, fg_color="transparent")
        alt_frame.pack(fill="x", padx=10)

        def _add_alt_kalem(_n=name, _mal=mal, _dahil_lbl=dahil_lbl,
                           _alt_frame=alt_frame, _ak_list=alt_kalemler_list):
            row = ctk.CTkFrame(_alt_frame, fg_color="#E8F0FE",
                               corner_radius=6, border_width=1, border_color=CARD_BORDER)
            row.pack(fill="x", pady=2)

            ad_ent = ctk.CTkEntry(row, font=fnt(10), width=130,
                                   fg_color="white", border_color=CARD_BORDER,
                                   border_width=1, corner_radius=6,
                                   placeholder_text="Kalem adı (tel çit, parke…)")
            ad_ent.pack(side="left", padx=(6, 4), pady=5)

            hariç_ent = ctk.CTkEntry(row, font=fnt(10), width=120,
                                      fg_color="white", border_color=CARD_BORDER,
                                      border_width=1, corner_radius=6,
                                      placeholder_text="KDV Hariç tutar")
            hariç_ent.pack(side="left", padx=(0, 4), pady=5)

            ak_dahil_lbl = ctk.CTkLabel(row, text="→ —",
                                         font=fnt(9), text_color=BTN_PRIMARY, width=100, anchor="w")
            ak_dahil_lbl.pack(side="left", padx=(0, 4))

            ak_data = {"ad": ad_ent, "hariç": hariç_ent, "dahil_lbl": ak_dahil_lbl}
            _ak_list.append(ak_data)

            def _upd_ak(*_, _h=hariç_ent, _l=ak_dahil_lbl):
                v = _parse_tl(_h.get())
                _l.configure(text=f"→ {_format_tl(v * 1.2)}" if v else "→ —")
                _recalc_total(_n, _mal, _dahil_lbl, _ak_list)

            def _remove_ak(_row=row, _ak=ak_data, _ak_list=_ak_list):
                if _ak in _ak_list:
                    _ak_list.remove(_ak)
                _row.destroy()
                _recalc_total(_n, _mal, _dahil_lbl, _ak_list)
                _toggle_main_entry_state(_mal, _ak_list)

            hariç_ent.bind("<KeyRelease>", _upd_ak)
            hariç_ent.bind("<FocusOut>", _upd_ak)

            ctk.CTkButton(row, text="✕", width=26, height=26, corner_radius=5,
                          fg_color="#EEF2FF", hover_color=ERROR,
                          text_color=TEXT_LIGHT, font=fnt(10),
                          command=_remove_ak).pack(side="right", padx=6, pady=5)

            _toggle_main_entry_state(_mal, _ak_list)

        def _recalc_total(_n, _mal, _dahil_lbl, _ak_list):
            if not _ak_list:
                return
            total_h = sum(_parse_tl(ak["hariç"].get()) for ak in _ak_list)
            self._disc_entries[_n]["maliyet_hariç_val"] = total_h
            self._disc_entries[_n]["maliyet_dahil_val"] = total_h * 1.2
            if total_h:
                _mal.configure(state="normal")
                _mal.delete(0, "end")
                _mal.insert(0, _format_tl(total_h))
                _mal.configure(state="disabled",
                               fg_color="#F0F0F0", text_color=TEXT_MID)
                _dahil_lbl.configure(text=f"→ KDV Dahil: {_format_tl(total_h * 1.2)}")
            else:
                _toggle_main_entry_state(_mal, _ak_list)

        def _toggle_main_entry_state(_mal, _ak_list):
            if _ak_list:
                _mal.configure(state="disabled",
                               fg_color="#F0F0F0", text_color=TEXT_MID)
            else:
                _mal.configure(state="normal",
                               fg_color="white", text_color=TEXT_DARK)

        add_ak_btn_row = ctk.CTkFrame(detail, fg_color="transparent")
        add_ak_btn_row.pack(fill="x", padx=10, pady=(2, 8))
        ctk.CTkButton(add_ak_btn_row, text="+ Alt Kalem Ekle", width=140, height=26,
                      corner_radius=13, fg_color="#DCE8FF", hover_color=BTN_PRIMARY,
                      text_color=BTN_PRIMARY, font=fnt(10),
                      command=_add_alt_kalem).pack(side="left")

        self._disc_entries[name] = {
            "maliyet":           mal,
            "maliyet_dahil_lbl": dahil_lbl,
            "alt_frame":         alt_frame,
            "alt_kalemler":      alt_kalemler_list,
            "maliyet_hariç_val": 0.0,
            "maliyet_dahil_val": 0.0,
        }

    def _add_custom_discipline(self) -> None:
        name = self._new_disc_entry.get().strip()
        if not name or name in self._disc_vars:
            return
        self._custom_disciplines.append(name)
        self._add_discipline_row(self._disc_card, name)
        self._new_disc_entry.delete(0, "end")

    def _toggle_disc(self, name) -> None:
        if self._disc_vars[name].get():
            self._disc_rows[name].pack(fill="x", padx=32, pady=(0, 6))
        else:
            self._disc_rows[name].pack_forget()

    # ── Fotoğraf seçimi ───────────────────────────────────────────────────────
    def _pick_photo_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Fotoğrafların bulunduğu klasörü seçin",
            initialdir=str(Path.home() / "Desktop"))
        if not folder:
            return
        imgs = scan_images(folder)
        self._apply_photos(imgs, folder)

    def _pick_photo_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Fotoğraf dosyalarını seçin",
            filetypes=IMAGE_FILTER,
            initialdir=str(Path.home() / "Desktop"))
        if not files:
            return
        imgs = sorted([Path(f) for f in files])
        self._apply_photos(imgs, f"{len(imgs)} fotoğraf seçildi")

    def _apply_photos(self, imgs, label) -> None:
        self._images  = imgs
        self._cur_page = 0
        short = str(label) if len(str(label)) <= 55 else "…" + str(label)[-52:]
        self._photo_path_lbl.configure(text=short,
                                        text_color=TEXT_DARK if imgs else TEXT_LIGHT)
        if not imgs:
            self._photo_count_lbl.configure(text="⚠  Fotoğraf bulunamadı", text_color=WARN)
        else:
            self._photo_count_lbl.configure(
                text=f"✓  {len(imgs)} fotoğraf seçildi", text_color=SUCCESS)
        self._schedule_preview()

    # ── Önizleme ─────────────────────────────────────────────────────────────
    def _get_pages(self):
        if not self._images:
            return []
        grid = NOTE_LAYOUT_GRID.get(self._note_layout_var.get())
        if grid is None:
            from engine import paginate_oriented
            return paginate_oriented(self._images)
        cols, rows = grid
        per = cols * rows
        return [self._images[i: i + per] for i in range(0, len(self._images), per)]

    def _schedule_preview(self, *_) -> None:
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(160, self._launch_preview)

    def _launch_preview(self) -> None:
        self._preview_job = None
        self._pages = self._get_pages()
        if not self._pages:
            self._cur_page = 0
            self._draw_placeholder()
            self._page_lbl.configure(text="—")
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
            return
        self._cur_page = min(self._cur_page, len(self._pages) - 1)
        self._render_async()

    def _render_async(self) -> None:
        page_imgs = self._pages[self._cur_page] if self._pages else []
        grid      = NOTE_LAYOUT_GRID.get(self._note_layout_var.get())
        crop      = self._note_crop_var.get()

        def work():
            img = _render_page_preview(page_imgs, grid, crop, "Bilgi Notu",
                                       PREVIEW_W, PREVIEW_H)
            self._q.put(("preview", img))

        threading.Thread(target=work, daemon=True).start()

    def _on_preview_ready(self, pil_img) -> None:
        tk_img = ImageTk.PhotoImage(pil_img)
        self._preview_tk = tk_img
        cv = self._preview_canvas
        cv.delete("all")
        cv.create_image(0, 0, image=tk_img, anchor="nw")
        total = len(self._pages)
        cur   = self._cur_page + 1
        self._page_lbl.configure(text=f"Sayfa {cur} / {total}")
        self._prev_btn.configure(state="normal" if cur > 1    else "disabled")
        self._next_btn.configure(state="normal" if cur < total else "disabled")

    def _prev_page(self) -> None:
        if self._cur_page > 0:
            self._cur_page -= 1
            self._render_async()

    def _next_page(self) -> None:
        if self._cur_page < len(self._pages) - 1:
            self._cur_page += 1
            self._render_async()

    # ── Harici PDF ────────────────────────────────────────────────────────────
    def _add_ext_pdf(self) -> None:
        files = filedialog.askopenfilenames(
            title="Harici PDF dosyalarını seçin",
            filetypes=[("PDF", "*.pdf")],
            initialdir=str(Path.home() / "Desktop"))
        for f in files:
            if f not in self._ext_pdfs:
                self._ext_pdfs.append(f)
        self._render_ext_list()

    def _render_ext_list(self) -> None:
        for w in self._ext_pdf_frame.winfo_children():
            w.destroy()
        if not self._ext_pdfs:
            ctk.CTkLabel(self._ext_pdf_frame, text="Harici PDF eklenmedi",
                         font=fnt(10), text_color=TEXT_LIGHT).pack(pady=8)
            return
        for i, path in enumerate(self._ext_pdfs):
            row = ctk.CTkFrame(self._ext_pdf_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)
            short = Path(path).name
            if len(short) > 55:
                short = short[:52] + "…"
            ctk.CTkLabel(row, text=f"📎  {short}", font=fnt(10),
                         text_color=TEXT_DARK, anchor="w").pack(
                side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=26, height=22, corner_radius=5,
                          fg_color="#EEF2FF", hover_color=ERROR,
                          text_color=TEXT_LIGHT, font=fnt(10),
                          command=lambda j=i: self._remove_ext(j)).pack(side="right")

    def _remove_ext(self, i) -> None:
        self._ext_pdfs.pop(i)
        self._render_ext_list()

    # ── Serializasyon ─────────────────────────────────────────────────────────
    def _serialize_rich_text(self, widget=None) -> list:
        w       = widget if widget is not None else self._acik_text
        content = w.get("1.0", "end-1c")
        if not content:
            return []

        lines_text = content.split("\n")

        # Satır başlangıç offsetleri (mutlak karakter konumu)
        line_starts = [0]
        for lt in lines_text[:-1]:
            line_starts.append(line_starts[-1] + len(lt) + 1)

        def tk_to_abs(idx_str: str) -> int:
            norm = w.index(idx_str)
            ln, col = norm.split(".")
            ln = int(ln) - 1  # 0-tabanlı
            if ln >= len(line_starts):
                return len(content)
            return line_starts[ln] + int(col)

        n = len(content)
        bold_arr   = bytearray(n)
        italic_arr = bytearray(n)

        for tag, arr in [("bold", bold_arr), ("italic", italic_arr)]:
            ranges = w.tag_ranges(tag)
            for i in range(0, len(ranges), 2):
                s = tk_to_abs(str(ranges[i]))
                e = min(tk_to_abs(str(ranges[i + 1])), n)
                for j in range(s, e):
                    arr[j] = 1

        result = []
        pos = 0
        for line_text in lines_text:
            n_line    = len(line_text)
            is_bullet = line_text.startswith("• ")
            t_start   = 2 if is_bullet else 0

            runs: list = []
            if n_line > t_start:
                j0    = pos + t_start
                cur_b = bool(bold_arr[j0])
                cur_i = bool(italic_arr[j0])
                cur_t = ""
                for j in range(j0, pos + n_line):
                    b  = bool(bold_arr[j])
                    it = bool(italic_arr[j])
                    if b == cur_b and it == cur_i:
                        cur_t += content[j]
                    else:
                        if cur_t:
                            runs.append({"text": cur_t, "bold": cur_b, "italic": cur_i})
                        cur_b, cur_i, cur_t = b, it, content[j]
                if cur_t:
                    runs.append({"text": cur_t, "bold": cur_b, "italic": cur_i})

            result.append({"bullet": is_bullet, "runs": runs})
            pos += n_line + 1

        return result

    def _load_rich_text(self, widget: tk.Text, data: list, readonly: bool = False) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for i, para in enumerate(data):
            if i > 0:
                widget.insert("end", "\n")
            if para["bullet"]:
                widget.insert("end", "• ")
            for run in para["runs"]:
                tags = tuple(t for t, v in [("bold", run["bold"]), ("italic", run["italic"])] if v)
                widget.insert("end", run["text"], tags)
        if readonly:
            widget.configure(state="disabled")

    def _open_rich_text_modal(self) -> None:
        data = self._serialize_rich_text()
        AciklamaEditDialog(self, data)

    # ── Üretim ───────────────────────────────────────────────────────────────
    def _collect_data(self) -> dict:
        konu  = self._konu_entry.get().strip() or "Bilgi Notu"
        talep = None
        if self._talep_var.get():
            v = self._talep_entry.get().strip()
            if v:
                talep = v

        disciplines = []
        for name in DISCIPLINES_DEFAULT + self._custom_disciplines:
            if self._disc_vars.get(name) and self._disc_vars[name].get():
                ents = self._disc_entries[name]
                ak_list = ents.get("alt_kalemler", [])

                # Alt kalemler
                alt_out = []
                for ak in ak_list:
                    ad_str    = ak["ad"].get().strip()
                    hariç_str = ak["hariç"].get().strip()
                    hariç_v   = _parse_tl(hariç_str)
                    dahil_v   = hariç_v * 1.2
                    if ad_str or hariç_str:
                        alt_out.append({
                            "ad":           ad_str,
                            "maliyet_hariç": _format_tl(hariç_v) if hariç_v else hariç_str,
                            "maliyet_dahil": _format_tl(dahil_v) if dahil_v else "",
                        })

                hariç_v = ents.get("maliyet_hariç_val", 0.0)
                dahil_v = ents.get("maliyet_dahil_val", 0.0)
                # Alt kalem yoksa ana entry'den oku
                if not alt_out:
                    hariç_v = _parse_tl(ents["maliyet"].get())
                    dahil_v = hariç_v * 1.2

                disciplines.append({
                    "name":             name,
                    "maliyet_hariç":    _format_tl(hariç_v) if hariç_v else "",
                    "maliyet_dahil":    _format_tl(dahil_v) if dahil_v else "",
                    "maliyet_hariç_val": hariç_v,
                    "maliyet_dahil_val": dahil_v,
                    "alt_kalemler":     alt_out,
                    "alt_isi":          "",
                })

        grid = NOTE_LAYOUT_GRID.get(self._note_layout_var.get())
        return {
            "konu":             konu,
            "aciklamalar_rich": self._serialize_rich_text(),
            "talep_eden":       talep,
            "disciplines":  disciplines,
            "images":       list(self._images),
            "photo_grid":   grid,
            "photo_crop":   self._note_crop_var.get(),
            "ext_pdfs":     list(self._ext_pdfs),
            "duzenleyen":   self._duzenleyen_entry.get().strip(),
            "tarih":        self._tarih_entry.get().strip(),
        }

    def _start(self) -> None:
        # Doğrulama
        if not self._konu_entry.get().strip():
            messagebox.showwarning("Eksik Bilgi", "Konu alanı boş bırakılamaz.")
            self._konu_entry.focus_set()
            return
        _rich = self._serialize_rich_text()
        if not any(run["text"].strip() for para in _rich for run in para["runs"]):
            messagebox.showwarning("Eksik Bilgi", "Açıklamalar alanı boş bırakılamaz.")
            return

        try:
            data = self._collect_data()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            print(tb)
            messagebox.showerror("Veri Hatası", tb)
            return

        self._gen_btn.configure(state="disabled", text="Üretiliyor...")
        self._clear_result()
        self._status_lbl.configure(text="Word ve PDF oluşturuluyor...", text_color=TEXT_MID)
        self._progress.set(0.35)
        threading.Thread(target=self._run, args=(data,), daemon=True).start()

    def _run(self, data) -> None:
        try:
            from note_engine import build_note
            result = build_note(data)
            self._q.put(("ok", result))
        except Exception:
            import traceback
            tb = traceback.format_exc()
            print(tb)
            self._q.put(("err", tb))

    def _on_success(self, result) -> None:
        self._gen_btn.configure(state="normal", text="📄  Word + PDF Üret")
        self._progress.set(1.0)
        pdf_p  = result.get("pdf", "")
        docx_p = result.get("docx", "")
        name   = Path(pdf_p).name if pdf_p else "çıktı"
        self._status_lbl.configure(text=f"Kaydedildi: {name}", text_color=SUCCESS)
        self._show_result(pdf_p, docx_p)

    def _on_error(self, msg) -> None:
        self._gen_btn.configure(state="normal", text="📄  Word + PDF Üret")
        self._progress.set(0)
        short = msg.strip().split("\n")[-1][:120]
        self._status_lbl.configure(text=f"Hata: {short}", text_color=ERROR)
        messagebox.showerror("Üretim Hatası", msg)

    def _show_result(self, pdf_p, docx_p) -> None:
        self._clear_result()
        if pdf_p:
            ctk.CTkButton(self._result_row, text="📄  PDF Aç", height=40,
                          corner_radius=20, fg_color=BTN_SUCCESS, hover_color=BTN_SUC_H,
                          font=fnt(12, True),
                          command=lambda: open_path(pdf_p)).pack(
                side="left", fill="x", expand=True, padx=(0, 5))
        if docx_p:
            ctk.CTkButton(self._result_row, text="📝  Word Aç", height=40,
                          corner_radius=20, fg_color="#7C3AED", hover_color="#6D28D9",
                          font=fnt(12, True),
                          command=lambda: open_path(docx_p)).pack(
                side="left", fill="x", expand=True, padx=(0, 5))
        if pdf_p or docx_p:
            ctk.CTkButton(self._result_row, text="📁  Klasör", height=40,
                          corner_radius=20, fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                          font=fnt(12),
                          command=lambda: open_path(
                              str(Path(pdf_p or docx_p).parent))).pack(
                side="left", fill="x", expand=True)

    def _clear_result(self) -> None:
        for w in self._result_row.winfo_children():
            w.destroy()


# ─── Ana Pencere ─────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.withdraw()
        self.cfg       = load_config()
        self._logo_img = make_logo(56)
        self._modules: dict = {}
        self._build_ui()
        SplashScreen(self, on_done=self._reveal)

    def _setup_window(self) -> None:
        self.title("Bakım ve Onarım Şube Müdürlüğü")
        self.resizable(True, True)
        self.minsize(900, 600)
        self.configure(fg_color=PAGE_BG)
        self.attributes("-alpha", 0.0)
        W, H = 1120, 740
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

    def _reveal(self) -> None:
        self._setup_window()
        self.deiconify()
        self.after(20, self._fade_in)

    def _fade_in(self, alpha: float = 0.0) -> None:
        alpha = min(1.0, alpha + 0.07)
        self.attributes("-alpha", alpha)
        if alpha < 1.0:
            self.after(14, self._fade_in, alpha)

    def _build_ui(self) -> None:
        # Header (değişken içerik)
        self._hdr = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=72)
        self._hdr.pack(fill="x")
        self._hdr.pack_propagate(False)

        # İçerik alanı
        self._content = ctk.CTkFrame(self, fg_color=PAGE_BG, corner_radius=0)
        self._content.pack(fill="both", expand=True)

        # Footer
        foot = ctk.CTkFrame(self, fg_color="#D8E4F7", corner_radius=0, height=26)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        ctk.CTkLabel(foot, text="PDF Motor V1",
                     font=fnt(9), text_color=TEXT_LIGHT).pack(side="left", padx=14)
        ctk.CTkLabel(foot, text="© Bekircan Güler",
                     font=fnt(9), text_color=TEXT_LIGHT).pack(side="right", padx=14)

        # Ana sayfa
        self._home_frame = HomeScreen(self._content, on_navigate=self._nav_to)
        self._home_frame.pack(fill="both", expand=True)
        self._build_hdr_home()

    # ── Header ───────────────────────────────────────────────────────────────
    def _clear_hdr(self) -> None:
        for w in self._hdr.winfo_children():
            w.destroy()

    def _build_hdr_home(self) -> None:
        self._clear_hdr()
        ctk.CTkLabel(self._hdr, image=self._logo_img, text="").place(x=20, rely=0.5, anchor="w")
        tf = ctk.CTkFrame(self._hdr, fg_color="transparent")
        tf.place(x=58, rely=0.5, anchor="w")
        ctk.CTkLabel(tf, text="Bakım ve Onarım Şube Müdürlüğü",
                     font=fnt(19, True), text_color="#FFFFFF").pack(anchor="w")
        ctk.CTkLabel(tf, text="PDF Motor  V1",
                     font=fnt(10), text_color="#6B9ECC").pack(anchor="w")
        ctk.CTkLabel(self._hdr, text="Bekircan Güler",
                     font=fnt(9), text_color="#3D6A9E").place(
            relx=1.0, rely=0.0, anchor="ne", x=-14, y=10)

    def _build_hdr_module(self, title: str) -> None:
        self._clear_hdr()
        ctk.CTkButton(self._hdr, text="← Geri", width=82, height=32,
                      corner_radius=16, fg_color="#243F6A", hover_color="#182D50",
                      text_color="#A0C0E8", font=fnt(11),
                      command=self._nav_home).place(x=18, rely=0.5, anchor="w")
        ctk.CTkLabel(self._hdr, text=title, font=fnt(17, True),
                     text_color="#FFFFFF").place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(self._hdr, text="Bekircan Güler",
                     font=fnt(9), text_color="#3D6A9E").place(
            relx=1.0, rely=0.0, anchor="ne", x=-14, y=10)

    # ── Navigasyon ───────────────────────────────────────────────────────────
    MODULE_TITLES = {
        "photo": "📷  Fotoğraf → PDF",
        "merge": "🔗  PDF Birleştir",
        "note":  "📝  Bilgi Notu",
    }

    def _nav_to(self, key: str) -> None:
        for w in self._content.winfo_children():
            w.pack_forget()

        if key == "home":
            self._build_hdr_home()
            self._home_frame.pack(fill="both", expand=True)
        else:
            self._build_hdr_module(self.MODULE_TITLES.get(key, key))
            if key not in self._modules:
                self._modules[key] = self._make_module(key)
            self._modules[key].pack(fill="both", expand=True)

    def _nav_home(self) -> None:
        self._nav_to("home")

    def _make_module(self, key: str) -> ctk.CTkFrame:
        if key == "photo":
            return PhotoModule(self._content, self.cfg, root=self)
        if key == "merge":
            return MergeModule(self._content, root=self)
        if key == "note":
            return NoteModule(self._content, root=self)
        f = ctk.CTkFrame(self._content, fg_color=PAGE_BG)
        ctk.CTkLabel(f, text="Yakında...",
                     font=fnt(20, True), text_color=TEXT_LIGHT).pack(expand=True)
        return f


# ─── Yardımcı ────────────────────────────────────────────────────────────────
def open_path(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        import subprocess; subprocess.run(["open", path])
    else:
        import subprocess; subprocess.run(["xdg-open", path])


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
