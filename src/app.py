#!/usr/bin/env python3
"""
CLI entry point — tkinter klasör seçici ile PDF üretir.
Web arayüzü için: python src/web_app.py
"""

import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from engine import load_config, scan_images, build_pdf


def _msgbox(kind: str, title: str, msg: str) -> None:
    root = tk.Tk()
    root.withdraw()
    getattr(messagebox, kind)(title, msg)
    root.destroy()


def select_folder() -> str | None:
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(
        title="Fotoğrafların bulunduğu klasörü seçin",
        initialdir=str(Path.home() / "Desktop"),
    )
    root.destroy()
    return path or None


def main() -> None:
    cfg = load_config()

    folder = select_folder()
    if not folder:
        print("Klasör seçilmedi. Çıkılıyor.")
        return

    images = scan_images(folder)
    if not images:
        _msgbox("showwarning", "Resim Bulunamadı",
                f"Klasörde PNG/JPG/JPEG dosyası bulunamadı:\n{folder}")
        return

    # Klasör adını başlık olarak kullan
    cfg["title"] = Path(folder).name
    print(f"{len(images)} resim bulundu — başlık: '{cfg['title']}'")
    print("PDF oluşturuluyor…")

    try:
        out = build_pdf(images, cfg)
        _msgbox("showinfo", "Tamamlandı", f"PDF başarıyla oluşturuldu!\n\n{out}")
        print(f"Kaydedildi: {out}")
    except Exception as e:
        _msgbox("showerror", "Hata", f"PDF oluşturulurken hata:\n{e}")
        print(f"[HATA] {e}")
        raise


if __name__ == "__main__":
    main()
