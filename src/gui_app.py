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
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw, ImageFilter, ImageTk

sys.path.insert(0, str(Path(__file__).parent))
from engine import load_config, scan_images, build_pdf

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


def _safe_filename(title: str) -> str:
    invalid = r'\/:*?"<>|'
    name = "".join(c if c not in invalid else "_" for c in title)
    return name.strip(". ") or "fotograf_raporu"


# ─── Logo ────────────────────────────────────────────────────────────────────

def make_logo(size: int = 56, pil_only: bool = False):
    s  = size
    sc = s / 56  # scale factor relative to 56px reference design
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Doküman gövdesi — beyaz kağıt
    doc_r = int(s * 0.70)
    d.rounded_rectangle([2, 2, doc_r, s - 2], radius=max(2, int(6 * sc)),
                         fill=(255, 255, 255, 255), outline=(200, 215, 235, 255), width=1)

    # Katlanan köşe
    fold = max(5, int(13 * sc))
    d.polygon([(doc_r - fold, 2), (doc_r, 2 + fold), (doc_r, 2),
               (doc_r - fold, 2)], fill=(37, 99, 235, 160))
    d.line([(doc_r - fold, 2), (doc_r, 2 + fold)],
           fill=(255, 255, 255, 200), width=1)

    # Metin satırları
    lx1 = max(4, int(8 * sc))
    lx2 = doc_r - max(3, int(6 * sc))
    for y_ref, length in [(20, 1.0), (27, 0.85), (34, 0.65)]:
        y  = max(6, int(y_ref * sc))
        h  = max(1, int(3 * sc))
        ex = int(lx1 + (lx2 - lx1) * length)
        d.rounded_rectangle([lx1, y, ex, y + h], radius=1,
                             fill=(189, 207, 232, 255))

    # Kamera dairesi — sağ alt
    cx = s - max(7, int(14 * sc))
    cy = s - max(7, int(14 * sc))
    cr = max(6, int(13 * sc))
    d.ellipse([cx-cr+1, cy-cr+1, cx+cr+1, cy+cr+1], fill=(0, 0, 0, 40))
    d.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=(37, 99, 235, 255))
    lr = max(3, int(7 * sc))
    d.ellipse([cx-lr, cy-lr, cx+lr, cy+lr], fill=(255, 255, 255, 255))
    li = max(2, int(4 * sc))
    d.ellipse([cx-li, cy-li, cx+li, cy+li], fill=(37, 99, 235, 255))
    fa, fb = max(3, int(6*sc)), max(5, int(10*sc))
    d.ellipse([cx+fa, cy-fb, cx+fb, cy-fa], fill=(255, 255, 255, 200))

    if pil_only:
        return img
    return ctk.CTkImage(light_image=img, dark_image=img, size=(s // 2, s // 2))


# ─── UI yardımcıları ─────────────────────────────────────────────────────────

def fnt(size: int, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight="bold" if bold else "normal")


def make_card(parent, pady: tuple = (0, 12)) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=14,
                        border_width=1, border_color=CARD_BORDER)
    card.pack(fill="x", pady=pady)
    return card


def step_header(card: ctk.CTkFrame, num: str, title: str) -> None:
    """Kart başlığı: renkli numara rozeti + başlık metni."""
    row = ctk.CTkFrame(card, fg_color="transparent")
    row.pack(fill="x", padx=18, pady=(14, 8))

    badge = ctk.CTkFrame(row, fg_color=STEP_BADGE, corner_radius=12,
                         width=26, height=26)
    badge.pack(side="left", padx=(0, 10))
    badge.pack_propagate(False)
    ctk.CTkLabel(badge, text=num, font=fnt(11, True),
                 text_color="white").place(relx=0.5, rely=0.5, anchor="center")

    ctk.CTkLabel(row, text=title, font=fnt(13, True),
                 text_color=TEXT_DARK, anchor="w").pack(side="left")

    # İnce çizgi
    ctk.CTkFrame(card, fg_color=CARD_BORDER, height=1).pack(fill="x", padx=18)


def labeled_entry(card: ctk.CTkFrame, label: str,
                  placeholder: str = "", default: str = "") -> ctk.CTkEntry:
    row = ctk.CTkFrame(card, fg_color="transparent")
    row.pack(fill="x", padx=18, pady=5)
    ctk.CTkLabel(row, text=label, font=fnt(11), text_color=TEXT_MID,
                 width=90, anchor="w").pack(side="left")
    ent = ctk.CTkEntry(row, placeholder_text=placeholder, font=fnt(11),
                       fg_color="#F8FAFF", border_color=CARD_BORDER,
                       border_width=1, corner_radius=8)
    ent.pack(side="left", fill="x", expand=True)
    if default:
        ent.insert(0, default)
    return ent


# ─── Açılış Ekranı ───────────────────────────────────────────────────────────

class SplashScreen(tk.Toplevel):
    """6.8 saniyelik animasyonlu açılış ekranı."""
    _W, _H    = 560, 340
    _BG       = "#0B1929"
    _BG_RGB   = (11,  25,  41)
    _RING_RGB = (37,  99,  235)
    _DOT_RGB  = (28,  55,  95)
    _RMIN, _RMAX = 50, 132

    _STATUSES = [
        (0.9, "Modüller yükleniyor..."),
        (2.4, "Yazı tipleri hazırlanıyor..."),
        (3.8, "Arayüz oluşturuluyor..."),
        (5.4, "Hazır!"),
    ]

    def __init__(self, master, on_done: callable) -> None:
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
        self.geometry(
            f"{self._W}x{self._H}"
            f"+{(sw - self._W) // 2}+{(sh - self._H) // 2}")
        self.wm_attributes("-alpha", 0.0)

        # Canvas tüm pencereyi kaplar — animasyon buraya çizilir
        self._cv = tk.Canvas(self, width=self._W, height=self._H,
                              bg=self._BG, highlightthickness=0)
        self._cv.pack(fill="both", expand=True)

        self._cx      = self._W // 2
        self._cy_logo = int(self._H * 0.32)

        # Logo → canvas üzerine doğrudan (z-order kontrolü için)
        pil = make_logo(220, pil_only=True)
        self._tk_logo = ImageTk.PhotoImage(pil)
        self._cv.create_image(self._cx, self._cy_logo,
                               image=self._tk_logo,
                               anchor="center", tags="static")

        # Statik yazılar
        self._cv.create_text(
            self._cx, int(self._H * 0.60),
            text="Fotoğraf  ·  PDF Dönüştürücü",
            font=("", 18, "bold"), fill="#FFFFFF",
            anchor="center", tags="static")
        self._cv.create_text(
            self._cx, int(self._H * 0.71),
            text="PDF Motor V1",
            font=("", 10), fill="#2D5A8A",
            anchor="center", tags="static")
        self._cv.create_text(
            self._W - 10, self._H - 8,
            text="© Bekircan Güler",
            font=("", 9), fill="#1B3250",
            anchor="se", tags="static")

        # Dinamik durum yazısı (static tag ile üstte kalır)
        self._status_id = self._cv.create_text(
            self._cx, int(self._H * 0.82),
            text="", font=("", 10), fill="#3D6A9E",
            anchor="center", tags="static")

        # Progress bar koordinatları (canvas üzerinde elle çizilir)
        self._bx = (self._W - 440) // 2
        self._by = int(self._H * 0.90)
        self._bw = 440
        self._bh = 4

        self.after(16, self._tick)

    # ── Yardımcılar ───────────────────────────────────────────────────────────

    def _lerp(self, c1: tuple, c2: tuple, t: float) -> str:
        t = max(0.0, min(1.0, t))
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ── Ana döngü ─────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        if self._done:
            return
        elapsed = time.monotonic() - self._t0

        # Açılış fade-in (0 → 0.7s)
        if elapsed < 0.7:
            self.wm_attributes("-alpha", elapsed / 0.7)

        # Progress değeri (0.8s → 6.0s)
        prog = max(0.0, min(1.0, (elapsed - 0.8) / 5.2))

        # Durum metni
        msg = ""
        for t_trig, text in self._STATUSES:
            if elapsed >= t_trig:
                msg = text
        self._cv.itemconfigure(self._status_id, text=msg)

        # Animasyonlu çizim
        self._draw(elapsed, prog)

        # Kapanış fade-out (6.1s → 6.8s)
        if elapsed >= 6.1:
            self.wm_attributes("-alpha", max(0.0, 1.0 - (elapsed - 6.1) / 0.7))

        # Tamamlandı
        if elapsed >= 6.8:
            self._done = True
            self.destroy()
            self._on_done()
            return

        self.after(16, self._tick)

    # ── Çizim ─────────────────────────────────────────────────────────────────

    def _draw(self, t: float, prog: float) -> None:
        cv  = self._cv
        BG  = self._BG_RGB
        RNG = self._RING_RGB
        DOT = self._DOT_RGB

        cv.delete("anim")   # sadece "anim" etiketli öğeler temizlenir

        cx, cy = self._cx, self._cy_logo

        # Arka plan nefes alan noktalar
        for dx, dy, ph in self._dots:
            br  = 0.22 + 0.22 * math.sin(t * 1.1 + ph)
            col = self._lerp(BG, DOT, br)
            cv.create_oval(dx-1, dy-1, dx+1, dy+1,
                           fill=col, outline="", tags="anim")

        # Logo merkezinden genişleyen 3 halka
        for k in range(3):
            ph  = ((t * 0.38) + k / 3) % 1.0
            r   = self._RMIN + ph * (self._RMAX - self._RMIN)
            f   = 1.0 - ph
            col = self._lerp(BG, RNG, f * 0.65)
            w   = max(1, int(f * 2.5))
            cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                           outline=col, width=w, tags="anim")

        # Progress bar arkaplanı
        bx, by, bw, bh = self._bx, self._by, self._bw, self._bh
        cv.create_rectangle(bx, by, bx+bw, by+bh,
                             fill="#112030", outline="", tags="anim")
        # Progress bar dolumu
        fw = int(bw * prog)
        if fw > 0:
            cv.create_rectangle(bx, by, bx+fw, by+bh,
                                 fill=BTN_PRIMARY, outline="", tags="anim")

        # "static" etiketli öğeleri (logo, yazılar) en üste taşı
        cv.tag_raise("static")


# ─── Ana pencere ─────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.withdraw()   # Splash bitmeden ana pencereyi gizle
        self.cfg = load_config()
        self._logo_img = make_logo(56)
        self._setup_window()
        self._build_ui()
        SplashScreen(self, on_done=self._reveal)

    def _setup_window(self) -> None:
        self.title("Fotoğraf - PDF Dönüştürücü")
        self.resizable(True, True)
        self.minsize(540, 680)
        self.configure(fg_color=PAGE_BG)
        self.attributes("-alpha", 0.0)  # Fade-in için başlangıç
        W, H = 660, 840
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")

    def _reveal(self) -> None:
        """Splash bittikten sonra ana pencereyi göster."""
        self.attributes("-alpha", 0.0)
        self.deiconify()
        self.after(20, self._fade_in)

    def _fade_in(self, alpha: float = 0.0) -> None:
        alpha = min(1.0, alpha + 0.07)
        self.attributes("-alpha", alpha)
        if alpha < 1.0:
            self.after(14, self._fade_in, alpha)

    def _build_ui(self) -> None:
        self._build_header()
        self._build_tabs()
        self._build_footer()

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=82)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Logo
        logo_lbl = ctk.CTkLabel(hdr, image=self._logo_img, text="")
        logo_lbl.place(x=20, rely=0.5, anchor="w")

        # Başlık
        title_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frame.place(x=58, rely=0.5, anchor="w")
        ctk.CTkLabel(title_frame, text="Fotoğraf · PDF Dönüştürücü",
                     font=fnt(19, True), text_color="#FFFFFF").pack(anchor="w")
        ctk.CTkLabel(title_frame, text="PDF Motor  V1",
                     font=fnt(10), text_color="#6B9ECC").pack(anchor="w")

        # Sağ üst — imza
        ctk.CTkLabel(hdr, text="Bekircan Güler",
                     font=fnt(9), text_color="#3D6A9E").place(
            relx=1.0, rely=0.0, anchor="ne", x=-14, y=10)

    def _build_tabs(self) -> None:
        tabs = ctk.CTkTabview(
            self, fg_color=PAGE_BG, corner_radius=0,
            segmented_button_fg_color="#D5E0F5",
            segmented_button_selected_color=BTN_PRIMARY,
            segmented_button_selected_hover_color=BTN_HOVER,
            segmented_button_unselected_color="#D5E0F5",
            segmented_button_unselected_hover_color="#C4D4EF",
            text_color=TEXT_MID,
            text_color_disabled=TEXT_LIGHT,
        )
        tabs.pack(fill="both", expand=True, padx=0, pady=0)
        tabs.add("  📷  Fotoğraf → PDF  ")
        tabs.add("  🔗  PDF Birleştir  ")

        PhotoTab(tabs.tab("  📷  Fotoğraf → PDF  "), self.cfg, root=self)
        MergeTab(tabs.tab("  🔗  PDF Birleştir  "), root=self)

    def _build_footer(self) -> None:
        foot = ctk.CTkFrame(self, fg_color="#D8E4F7", corner_radius=0, height=26)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        ctk.CTkLabel(foot, text="PDF Motor V1",
                     font=fnt(9), text_color=TEXT_LIGHT).pack(side="left", padx=14)
        ctk.CTkLabel(foot, text="© Bekircan Güler",
                     font=fnt(9), text_color=TEXT_LIGHT).pack(side="right", padx=14)


# ─── Sekme 1: Fotoğraf → PDF ─────────────────────────────────────────────────

class PhotoTab(ctk.CTkFrame):
    def __init__(self, parent, cfg: dict, root: ctk.CTk) -> None:
        super().__init__(parent, fg_color=PAGE_BG)
        self.pack(fill="both", expand=True)
        self.cfg    = cfg
        self.root   = root
        self._images: list = []
        self._out_path: str | None = None
        self._q: queue.Queue = queue.Queue()
        self._build()
        self._poll()   # thread→UI köprüsü başlıyor

    def _poll(self) -> None:
        """Her 80ms ana thread'de kuyruk kontrol eder — root.after'dan daha güvenilir."""
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

        # ── Kart 1: Fotoğraf Seç ────────────────────────────────────────────
        c1 = make_card(body)
        step_header(c1, "1", "Fotoğraf seçin")

        btn_row = ctk.CTkFrame(c1, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=10)

        ctk.CTkButton(btn_row, text="📁  Klasör Seç", height=38, corner_radius=20,
                      fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                      font=fnt(11, True), command=self._pick_folder).pack(
            side="left", padx=(0, 8))

        ctk.CTkButton(btn_row, text="🖼  Tek Tek Seç", height=38, corner_radius=20,
                      fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                      font=fnt(11), command=self._pick_files).pack(side="left")

        # Bilgi satırı
        info = ctk.CTkFrame(c1, fg_color="#F0F6FF", corner_radius=8,
                            border_width=1, border_color=CARD_BORDER)
        info.pack(fill="x", padx=18, pady=(0, 14))
        self._path_lbl = ctk.CTkLabel(info, text="Henüz seçim yapılmadı",
                                      font=fnt(11), text_color=TEXT_LIGHT,
                                      anchor="w", wraplength=450)
        self._path_lbl.pack(padx=12, pady=9, fill="x")

        self._count_lbl = ctk.CTkLabel(c1, text="", font=fnt(11),
                                       text_color=TEXT_MID, anchor="w")
        self._count_lbl.pack(fill="x", padx=18, pady=(0, 12))

        # ── Kart 2: Rapor Bilgileri ──────────────────────────────────────────
        c2 = make_card(body)
        step_header(c2, "2", "Rapor bilgilerini düzenleyin")

        self._title_entry = labeled_entry(c2, "Başlık",
                                          placeholder="Klasör adından otomatik gelir")
        self._wm_entry = labeled_entry(c2, "Alt yazı",
                                       default=self.cfg.get("watermark_text", ""))
        ctk.CTkLabel(c2,
                     text="Başlık: her sayfada kalın  ·  Alt yazı: her sayfada silik küçük",
                     font=fnt(9), text_color=TEXT_LIGHT, anchor="w").pack(
            fill="x", padx=18, pady=(4, 14))

        # ── Kart 3: PDF Oluştur ─────────────────────────────────────────────
        c3 = make_card(body, pady=(0, 4))
        step_header(c3, "3", "PDF oluşturun")

        self._btn = ctk.CTkButton(c3, text="⚡  PDF Oluştur", height=48,
                                  corner_radius=24, fg_color=BTN_PRIMARY,
                                  hover_color=BTN_HOVER, font=fnt(14, True),
                                  state="disabled", command=self._start)
        self._btn.pack(fill="x", padx=18, pady=(12, 10))

        self._progress = ctk.CTkProgressBar(c3, mode="determinate",
                                            fg_color="#DCE8FF",
                                            progress_color=BTN_PRIMARY,
                                            height=6, corner_radius=3)
        self._progress.pack(fill="x", padx=18, pady=(0, 6))
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(c3, text="", font=fnt(11),
                                        text_color=TEXT_MID)
        self._status_lbl.pack(pady=(0, 4))

        # Sonuç butonları (dinamik — destroy/recreate ile güvenli)
        self._result_row = ctk.CTkFrame(c3, fg_color="transparent", height=42)
        self._result_row.pack(fill="x", padx=18, pady=(4, 14))

    # ── Seçim ─────────────────────────────────────────────────────────────────

    def _apply_selection(self, images: list, label: str) -> None:
        self._images  = images
        self._out_path = None
        display = label if len(label) <= 64 else "…" + label[-61:]
        self._path_lbl.configure(text=display, text_color=TEXT_DARK)
        self._clear_result()
        self._status_lbl.configure(text="")
        self._progress.set(0)

        if not images:
            self._count_lbl.configure(
                text="⚠  Fotoğraf bulunamadı (PNG / JPG / JPEG)",
                text_color=WARN)
            self._btn.configure(state="disabled")
        else:
            self._count_lbl.configure(
                text=f"✓  {len(images)} fotoğraf seçildi",
                text_color=SUCCESS)
            self._btn.configure(state="normal")

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

    # ── PDF Oluşturma ─────────────────────────────────────────────────────────

    def _start(self) -> None:
        if not self._images:
            return

        title     = self._title_entry.get().strip() or "Fotograf Raporu"
        watermark = self._wm_entry.get().strip()

        self._btn.configure(state="disabled", text="Isleniyor...")
        self._clear_result()
        self._status_lbl.configure(
            text="PDF olusturuluyor, lutfen bekleyin...", text_color=TEXT_MID)
        self._progress.set(0.45)

        cfg = self.cfg.copy()
        cfg["title"] = title
        cfg["output_filename"] = _safe_filename(title) + ".pdf"
        if watermark:
            cfg["watermark_text"] = watermark

        threading.Thread(target=self._run, args=(cfg,), daemon=True).start()

    def _run(self, cfg: dict) -> None:
        """Arka plan thread — sonucu queue'ya yazar, UI'ye dokunmaz."""
        try:
            out = build_pdf(self._images, cfg)
            self._q.put(("ok", out))
        except Exception as exc:
            self._q.put(("err", str(exc)))

    def _on_success(self, out: str) -> None:
        self._btn.configure(state="normal", text="PDF Olustur")
        self._progress.set(1.0)
        self._out_path = out
        self._status_lbl.configure(
            text=f"Kaydedildi: {Path(out).name}", text_color=SUCCESS)
        self._show_result(out)

    def _on_error(self, msg: str) -> None:
        self._btn.configure(state="normal", text="PDF Olustur")
        self._progress.set(0)
        self._status_lbl.configure(text=f"Hata: {msg[:80]}", text_color=ERROR)
        messagebox.showerror("PDF Olusturma Hatasi", msg)

    def _show_result(self, out: str) -> None:
        self._clear_result()
        ctk.CTkButton(self._result_row, text="📄  PDF'i Aç", height=40,
                      corner_radius=20, fg_color=BTN_SUCCESS,
                      hover_color=BTN_SUC_H, font=fnt(12, True),
                      command=lambda: open_path(out)).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(self._result_row, text="📁  Klasörü Aç", height=40,
                      corner_radius=20, fg_color=BTN_NEUTRAL,
                      hover_color=BTN_NEU_H, font=fnt(12),
                      command=lambda: open_path(str(Path(out).parent))).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

    def _clear_result(self) -> None:
        for w in self._result_row.winfo_children():
            w.destroy()

    def _open_pdf(self) -> None:
        if self._out_path:
            open_path(self._out_path)


# ─── Sekme 2: PDF Birleştir ───────────────────────────────────────────────────

class MergeTab(ctk.CTkFrame):
    def __init__(self, parent, root: ctk.CTk) -> None:
        super().__init__(parent, fg_color=PAGE_BG)
        self.pack(fill="both", expand=True)
        self.root  = root
        self._pdfs: list[Path] = []
        self._out_path: str | None = None
        self._q: queue.Queue = queue.Queue()
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

        # ── Kart 1: PDF Listesi ─────────────────────────────────────────────
        c1 = make_card(body)
        step_header(c1, "1", "Birleştirilecek PDF'leri seçin")

        btn_row = ctk.CTkFrame(c1, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=10)
        ctk.CTkButton(btn_row, text="+ PDF Ekle", height=36, corner_radius=18,
                      fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                      font=fnt(11, True), command=self._add_files).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="📂 Klasörden Ekle", height=36, corner_radius=18,
                      fg_color=BTN_NEUTRAL, hover_color=BTN_NEU_H,
                      font=fnt(11), command=self._add_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="X  Temizle", height=36, corner_radius=18,
                      fg_color="#E5EAF4", hover_color="#D0DAEE",
                      text_color=TEXT_MID, font=fnt(11),
                      command=self._clear_list).pack(side="right")

        self._list_outer = ctk.CTkFrame(c1, fg_color="#F0F6FF", corner_radius=10,
                                        border_width=1, border_color=CARD_BORDER)
        self._list_outer.pack(fill="x", padx=18, pady=(0, 8))
        self._render_list()

        self._count_lbl = ctk.CTkLabel(c1, text="", font=fnt(11),
                                       text_color=TEXT_MID, anchor="w")
        self._count_lbl.pack(fill="x", padx=18, pady=(0, 12))

        # ── Kart 2: Çıktı Adı ───────────────────────────────────────────────
        c2 = make_card(body)
        step_header(c2, "2", "Çıktı dosya adı")
        self._name_entry = labeled_entry(c2, "Dosya adı",
                                         placeholder="birlesik_rapor.pdf",
                                         default="birlesik_rapor.pdf")
        ctk.CTkLabel(c2, text="Masaüstüne kaydedilir",
                     font=fnt(9), text_color=TEXT_LIGHT, anchor="w").pack(
            fill="x", padx=18, pady=(2, 14))

        # ── Kart 3: Birleştir ────────────────────────────────────────────────
        c3 = make_card(body, pady=(0, 4))
        step_header(c3, "3", "Birleştirin")

        self._btn_merge = ctk.CTkButton(c3, text="🔗  PDF'leri Birleştir",
                                        height=48, corner_radius=24,
                                        fg_color=BTN_PRIMARY, hover_color=BTN_HOVER,
                                        font=fnt(14, True), state="disabled",
                                        command=self._start_merge)
        self._btn_merge.pack(fill="x", padx=18, pady=(12, 10))

        self._progress = ctk.CTkProgressBar(c3, mode="determinate",
                                            fg_color="#DCE8FF",
                                            progress_color=BTN_PRIMARY,
                                            height=6, corner_radius=3)
        self._progress.pack(fill="x", padx=18, pady=(0, 6))
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(c3, text="", font=fnt(11),
                                        text_color=TEXT_MID)
        self._status_lbl.pack(pady=(0, 4))

        self._result_row = ctk.CTkFrame(c3, fg_color="transparent", height=42)
        self._result_row.pack(fill="x", padx=18, pady=(4, 14))

    # ── Liste ─────────────────────────────────────────────────────────────────

    def _render_list(self) -> None:
        for w in self._list_outer.winfo_children():
            w.destroy()
        if not self._pdfs:
            ctk.CTkLabel(self._list_outer,
                         text="Henüz PDF eklenmedi",
                         font=fnt(11), text_color=TEXT_LIGHT).pack(pady=16)
            return
        for i, path in enumerate(self._pdfs):
            self._render_row(i, path)

    def _render_row(self, i: int, path: Path) -> None:
        n   = len(self._pdfs)
        bg  = "#FFFFFF" if i % 2 == 0 else "#F5F9FF"
        row = ctk.CTkFrame(self._list_outer, fg_color=bg,
                           corner_radius=0, height=40)
        row.pack(fill="x")
        row.pack_propagate(False)

        # Yukarı
        ctk.CTkButton(row, text="^", width=30, height=26,
                      corner_radius=6, fg_color="#DCE8FF",
                      hover_color=BTN_PRIMARY, text_color=BTN_PRIMARY,
                      font=fnt(11, True),
                      state="disabled" if i == 0 else "normal",
                      command=lambda j=i: self._move(j, -1)).pack(
            side="left", padx=(8, 2), pady=7)

        # Aşağı
        ctk.CTkButton(row, text="v", width=30, height=26,
                      corner_radius=6, fg_color="#DCE8FF",
                      hover_color=BTN_PRIMARY, text_color=BTN_PRIMARY,
                      font=fnt(11, True),
                      state="disabled" if i == n - 1 else "normal",
                      command=lambda j=i: self._move(j, +1)).pack(
            side="left", padx=(0, 10), pady=7)

        # Dosya adı
        name = path.name if len(path.name) <= 50 else path.name[:47] + "…"
        ctk.CTkLabel(row, text=f"{i + 1}.  {name}",
                     font=fnt(11), text_color=TEXT_DARK, anchor="w").pack(
            side="left", fill="x", expand=True)

        # Sil
        ctk.CTkButton(row, text="X", width=28, height=26,
                      corner_radius=6, fg_color="#EEF2FF",
                      hover_color=ERROR, text_color=TEXT_LIGHT,
                      font=fnt(11, True),
                      command=lambda j=i: self._remove(j)).pack(
            side="right", padx=8, pady=7)

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
            self._count_lbl.configure(
                text="⚠  En az 2 PDF seçin", text_color=WARN)
            self._btn_merge.configure(state="disabled")
        else:
            self._count_lbl.configure(
                text=f"  {n} PDF secildi  -  ^ v butonlariyla siralayin",
                text_color=SUCCESS)
            self._btn_merge.configure(state="normal")

    # ── Dosya Ekleme ──────────────────────────────────────────────────────────

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

    # ── Birleştirme ───────────────────────────────────────────────────────────

    def _start_merge(self) -> None:
        if len(self._pdfs) < 2:
            return
        filename = self._name_entry.get().strip() or "birlesik_rapor.pdf"
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        self._btn_merge.configure(state="disabled", text="Birlestiriliyor...")
        self._clear_result()
        self._status_lbl.configure(
            text="PDF'ler birlestiriliyor, lutfen bekleyin...", text_color=TEXT_MID)
        self._progress.set(0.45)
        threading.Thread(target=self._run_merge, args=(filename, list(self._pdfs)),
                         daemon=True).start()

    def _run_merge(self, filename: str, pdfs: list) -> None:
        """Arka plan thread — sonucu queue'ya yazar."""
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
        self._btn_merge.configure(state="normal", text="PDF'leri Birlestir")
        self._progress.set(1.0)
        self._out_path = out
        self._status_lbl.configure(
            text=f"Kaydedildi: {Path(out).name}", text_color=SUCCESS)
        self._show_result(out)

    def _on_error(self, msg: str) -> None:
        self._btn_merge.configure(state="normal", text="PDF'leri Birlestir")
        self._progress.set(0)
        self._status_lbl.configure(text=f"Hata: {msg[:80]}", text_color=ERROR)
        messagebox.showerror("Birlestirme Hatasi", msg)

    def _show_result(self, out: str) -> None:
        self._clear_result()
        ctk.CTkButton(self._result_row, text="📄  PDF'i Aç", height=40,
                      corner_radius=20, fg_color=BTN_SUCCESS,
                      hover_color=BTN_SUC_H, font=fnt(12, True),
                      command=lambda: open_path(out)).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(self._result_row, text="📁  Klasörü Aç", height=40,
                      corner_radius=20, fg_color=BTN_NEUTRAL,
                      hover_color=BTN_NEU_H, font=fnt(12),
                      command=lambda: open_path(str(Path(out).parent))).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

    def _clear_result(self) -> None:
        for w in self._result_row.winfo_children():
            w.destroy()


# ─── Yardımcı ────────────────────────────────────────────────────────────────

def open_path(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        import subprocess; subprocess.run(["open", path])
    else:
        import subprocess; subprocess.run(["xdg-open", path])


# ─── Giriş ───────────────────────────────────────────────────────────────────

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
