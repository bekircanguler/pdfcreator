#!/usr/bin/env python3
"""
Flask web interface for the PDF Report Engine.

Çalıştırma:  python src/web_app.py
Erişim:      http://localhost:5000  veya  http://<ağ-ip>:5000
"""

import shutil
import socket
import tempfile
import sys
from io import BytesIO
from pathlib import Path

from flask import Flask, render_template, request, send_file, jsonify
from pypdf import PdfWriter, PdfReader

# Engine modülü aynı dizinde
sys.path.insert(0, str(Path(__file__).parent))
from engine import load_config, build_pdf_to_buffer, IMAGE_EXTS

# ---------------------------------------------------------------------------
# Flask setup
# ---------------------------------------------------------------------------

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024   # 500 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def safe_filename(text: str) -> str:
    """Removes characters that are invalid in filenames across platforms."""
    return "".join(c for c in text if c not in r'\/:*?"<>|').strip() or "rapor"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    cfg = load_config()
    return render_template("index.html",
                           local_ip=get_local_ip(),
                           default_subtitle=cfg.get("watermark_text", ""))


@app.route("/generate", methods=["POST"])
def generate():
    title    = (request.form.get("title")    or "Fotoğraf Raporu").strip()
    subtitle = (request.form.get("subtitle") or "").strip()
    files = request.files.getlist("images")

    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "Resim yüklenmedi"}), 400

    tmp = tempfile.mkdtemp()
    try:
        paths = []
        for f in files:
            suffix = Path(f.filename).suffix.lower() if f.filename else ""
            if suffix in IMAGE_EXTS:
                # Use only the basename — prevents directory traversal
                dest = Path(tmp) / Path(f.filename).name
                f.save(str(dest))
                paths.append(dest)

        paths.sort(key=lambda p: p.name.lower())

        if not paths:
            return jsonify({"error": "Geçerli resim dosyası bulunamadı (JPG/PNG)"}), 400

        cfg = load_config()
        cfg["title"] = title
        if subtitle:
            cfg["watermark_text"] = subtitle

        pdf_buf = build_pdf_to_buffer(paths, cfg)

        print(f"[OK] '{title}' — {len(paths)} resim, PDF oluşturuldu")

        return send_file(
            pdf_buf,
            as_attachment=True,
            download_name=f"{safe_filename(title)}.pdf",
            mimetype="application/pdf",
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.route("/merge", methods=["POST"])
def merge():
    files = request.files.getlist("pdfs")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "PDF dosyası yüklenmedi"}), 400

    output_name = (request.form.get("output_name") or "birlesik").strip()

    writer = PdfWriter()
    tmp = tempfile.mkdtemp()
    try:
        for f in files:
            if not f.filename.lower().endswith(".pdf"):
                continue
            dest = Path(tmp) / Path(f.filename).name
            f.save(str(dest))
            reader = PdfReader(str(dest))
            for page in reader.pages:
                writer.add_page(page)

        if len(writer.pages) == 0:
            return jsonify({"error": "Geçerli PDF sayfası bulunamadı"}), 400

        buf = BytesIO()
        writer.write(buf)
        buf.seek(0)

        print(f"[OK] PDF birleştirme — {len(writer.pages)} sayfa, '{output_name}'")

        return send_file(
            buf,
            as_attachment=True,
            download_name=f"{safe_filename(output_name)}.pdf",
            mimetype="application/pdf",
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    local_ip = get_local_ip()
    bar = "=" * 52
    print(bar)
    print("  PDF Rapor Motoru — Web Arayüzü")
    print(bar)
    print(f"  Yerel bilgisayar :  http://localhost:5000")
    print(f"  Ağdaki diğer PC  :  http://{local_ip}:5000")
    print(bar)
    print("  Durdurmak için Ctrl+C")
    print()
    app.run(host="0.0.0.0", port=5000, debug=False)
