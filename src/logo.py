#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kurumsal logo — tek kaynak çizim modülü.

Uygulama içi başlık, pencere/görev çubuğu ikonu (app.ico), EXE dosya simgesi
ve PDF/Word belge başlığı (logo.png) hepsi bu modüldeki `draw_mark()`'tan
üretilir — böylece marka görseli tek yerden değişir, hepsi senkron kalır.
"""

import math
from PIL import Image, ImageDraw


def draw_mark(size: int, simple: bool = False) -> Image.Image:
    """Dişli çark + belge logosu. `simple=True`, küçük ikon boyutları
    (<=32px) için daha az diş / kalın hat / çizgisiz belge kullanır."""
    s  = size
    sc = s / 56
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Arka plan: koyu lacivert daire
    d.ellipse([1, 1, s - 2, s - 2], fill=(26, 46, 74, 255))

    # İç ince halka (çok küçük boyutlarda atlanır)
    if not simple or s >= 32:
        ir = max(2, int(3 * sc))
        d.ellipse([ir + 1, ir + 1, s - ir - 2, s - ir - 2],
                  outline=(50, 85, 140, 180), width=max(1, int(1 * sc)))

    cx, cy = s / 2, s / 2

    # ── Dişli çark (sol-üst bölge) ──
    gc_x = cx - int(3 * sc)
    gc_y = cy - int(4 * sc)
    r_out = int(14 * sc * (1.06 if simple else 1.0))
    r_inn = int(9 * sc)
    n_t   = 6 if simple else 8
    period = 2 * math.pi / n_t
    half_tooth = period * (0.46 if simple else 0.40) / 2

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
    hole_r = max(3, int(5 * sc * (1.15 if simple else 1.0)))
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

    # Belge çizgileri (mavi) — sadeleştirilmiş varyantta çizilmez
    if not simple:
        lx1 = doc_x + max(2, int(3 * sc))
        lx2 = doc_x + doc_w - fold - max(2, int(3 * sc))
        for ly_off in [int(7 * sc), int(10 * sc), int(13 * sc), int(16 * sc)]:
            ly = doc_y + ly_off
            if ly < doc_y + doc_h - 1:
                d.line([lx1, ly, lx2, ly], fill=(37, 99, 235, 200),
                       width=max(1, int(1.2 * sc)))

    return img
