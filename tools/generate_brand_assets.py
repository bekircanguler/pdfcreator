#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Marka varlıklarını (app.ico, logo.png) src/logo.py'deki tek kaynak çizim
algoritmasından üretir. GitHub Actions build adımında PyInstaller'dan önce
çalıştırılır; yerel geliştirme için de repo kökünden çalıştırılabilir:

    python tools/generate_brand_assets.py

Çıktılar repo köküne yazılır (logo.png, app.ico) — bu, gui_app.py'nin
`_app_icon_path()` ve note_engine.py'nin `_logo_path()` fonksiyonlarının
geliştirme (non-frozen) modunda aradığı konumla birebir eşleşir.
"""

import io
import struct
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import logo  # noqa: E402


def _png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def write_ico(path: Path, frames: List[Tuple[int, bytes]]) -> None:
    """frames: [(boyut, png_bytes), ...].

    ICO container'ı elle paketler (ICONDIR + ICONDIRENTRY + PNG blob'ları).
    Pillow'un ICO yazıcısı tek kaynaktan otomatik küçültme yaptığı için
    (her boyuta farklı sanat veremiyor), bu elle paketleme boyuta göre
    farklı çizim (küçük boyutlarda sadeleştirilmiş varyant) kullanılmasına
    izin veriyor. Windows Vista+ PNG-sıkıştırılmış ICO frame'lerini
    native destekler.
    """
    n = len(frames)
    header = struct.pack("<HHH", 0, 1, n)
    entries = b""
    offset = 6 + 16 * n
    for size, png in frames:
        wh = size if size < 256 else 0
        entries += struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(entries)
        for _, png in frames:
            fh.write(png)


def main() -> None:
    logo_img = logo.draw_mark(512, simple=False)
    logo_path = ROOT / "logo.png"
    logo_img.save(logo_path, format="PNG")

    frames: List[Tuple[int, bytes]] = []
    for size in (256, 128, 64, 48):
        frames.append((size, _png_bytes(logo.draw_mark(size, simple=False))))
    for size in (32, 24, 16):
        frames.append((size, _png_bytes(logo.draw_mark(size, simple=True))))

    ico_path = ROOT / "app.ico"
    write_ico(ico_path, frames)

    print(f"Üretildi: {logo_path}")
    print(f"Üretildi: {ico_path}")


if __name__ == "__main__":
    main()
