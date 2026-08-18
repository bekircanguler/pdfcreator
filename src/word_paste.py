#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Word'den kopyala-yapıştır — Windows panosundaki CF_HTML biçimini okuyup
madde işareti / numaralı liste / kalın / italik / altı çizili / renk
bilgisini koruyarak paragraf listesine çevirir.

Çıktı biçimi (AciklamaEditDialog._load_rich_text ile uyumlu):
    [{"bullet": bool, "numbered": bool,
      "runs": [{"text": str, "bold": bool, "italic": bool,
                "underline": bool, "color": Optional[str]}]}, ...]
"""

import re
from html.parser import HTMLParser
from typing import List, Optional

try:
    import win32clipboard
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False

_BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}
_BOLD_TAGS = {"b", "strong"}
_ITALIC_TAGS = {"i", "em"}
_UNDERLINE_TAGS = {"u"}
_COLOR_RE = re.compile(r"color\s*:\s*(#[0-9a-fA-F]{6}|rgb\([^)]+\))")
_MSO_LIST_RE = re.compile(r"mso-list\s*:\s*l(\d+)\s+level(\d+)")


def _css_color_to_hex(style: str) -> Optional[str]:
    m = _COLOR_RE.search(style or "")
    if not m:
        return None
    val = m.group(1)
    if val.startswith("#"):
        return val.upper()
    nums = re.findall(r"\d+", val)
    if len(nums) >= 3:
        r, g, b = (int(n) for n in nums[:3])
        return f"#{r:02X}{g:02X}{b:02X}"
    return None


def read_clipboard_html() -> Optional[str]:
    """Windows panosundaki CF_HTML verisini metin olarak döndürür (yoksa None)."""
    if not _HAS_WIN32:
        return None
    try:
        cf_html = win32clipboard.RegisterClipboardFormat("HTML Format")
    except Exception:
        return None

    raw: Optional[bytes] = None
    for _ in range(3):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(cf_html):
                    raw = win32clipboard.GetClipboardData(cf_html)
            finally:
                win32clipboard.CloseClipboard()
            break
        except Exception:
            import time
            time.sleep(0.05)
    if raw is None:
        return None

    if isinstance(raw, str):
        raw_bytes = raw.encode("latin-1", errors="ignore")
    else:
        raw_bytes = raw

    text = None
    for enc in ("utf-8", "cp1254", "latin-1"):
        try:
            text = raw_bytes.decode(enc, errors="replace" if enc == "latin-1" else "strict")
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw_bytes.decode("latin-1", errors="replace")

    # CF_HTML zarfı: "Version:...\r\nStartHTML:...\r\n...\r\n<html>...".
    # StartFragment/EndFragment ofsetleri byte bazlı olduğundan, güvenli
    # tarafta kalmak için doğrudan <!--StartFragment--> işaretini ararız.
    frag_start = text.find("<!--StartFragment-->")
    frag_end = text.find("<!--EndFragment-->")
    if frag_start != -1 and frag_end != -1:
        return text[frag_start + len("<!--StartFragment-->"): frag_end]
    return text


class _WordHTMLParser(HTMLParser):
    """Basit blok/satır-içi ayrıştırıcı — Word'ün ürettiği HTML'e göre
    paragraf/madde/numara/kalın/italik/altı-çizili/renk bilgisini çıkarır."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: List[dict] = []
        self._cur_para: Optional[dict] = None
        self._run_stack: List[dict] = [{"bold": False, "italic": False,
                                         "underline": False, "color": None}]
        self._list_stack: List[str] = []   # "ul" / "ol" iç içe
        self._ignore_depth = 0             # mso-list:Ignore span'ı (bullet glifi)

    # ── yardımcılar ──────────────────────────────────────────────────────
    def _open_para(self, bullet: bool = False, numbered: bool = False) -> None:
        self._flush_para()
        self._cur_para = {"bullet": bullet, "numbered": numbered, "runs": []}

    def _flush_para(self) -> None:
        if self._cur_para is not None:
            # tamamen boş paragrafları da tut (paragraf arası boşluk anlamına gelir)
            self.paragraphs.append(self._cur_para)
        self._cur_para = None

    def _add_text(self, text: str) -> None:
        if self._ignore_depth > 0:
            return
        if not text:
            return
        if self._cur_para is None:
            self._open_para()
        style = self._run_stack[-1]
        runs = self._cur_para["runs"]
        if runs and runs[-1]["bold"] == style["bold"] and \
                runs[-1]["italic"] == style["italic"] and \
                runs[-1]["underline"] == style["underline"] and \
                runs[-1]["color"] == style["color"]:
            runs[-1]["text"] += text
        else:
            runs.append({"text": text, **style})

    # ── HTMLParser callback'leri ─────────────────────────────────────────
    def handle_starttag(self, tag, attrs) -> None:
        attrs_d = dict(attrs)
        style = attrs_d.get("style", "") or ""

        if tag in ("ul", "ol"):
            self._list_stack.append(tag)
            return
        if tag == "li":
            numbered = bool(self._list_stack) and self._list_stack[-1] == "ol"
            self._open_para(bullet=not numbered, numbered=numbered)
            return
        if tag in _BLOCK_TAGS:
            mso = _MSO_LIST_RE.search(style)
            self._open_para()
            if mso:
                # Word'ün klasik liste deseni; gerçek işaret aşağıda
                # mso-list:Ignore span'ından anlaşılacak (varsayılan madde).
                self._cur_para["_mso_pending"] = True
            return
        if tag == "br":
            self._add_text("\n")
            return

        if "mso-list:ignore" in style.lower():
            self._ignore_depth += 1
            return

        top = dict(self._run_stack[-1])
        if tag in _BOLD_TAGS:
            top["bold"] = True
        if tag in _ITALIC_TAGS:
            top["italic"] = True
        if tag in _UNDERLINE_TAGS:
            top["underline"] = True
        color = _css_color_to_hex(style)
        if color:
            top["color"] = color
        if style:
            if "font-weight:bold" in style.replace(" ", "").lower() or \
                    "font-weight:700" in style.replace(" ", "").lower():
                top["bold"] = True
            if "font-style:italic" in style.replace(" ", "").lower():
                top["italic"] = True
            if "text-decoration:underline" in style.replace(" ", "").lower():
                top["underline"] = True
        self._run_stack.append(top)

    def handle_startendtag(self, tag, attrs) -> None:
        if tag == "br":
            self._add_text("\n")

    def handle_endtag(self, tag) -> None:
        if tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            return
        if tag in _BLOCK_TAGS:
            if self._cur_para is not None and self._cur_para.get("_mso_pending"):
                # Ignore span görülmediyse bile mso-list paragrafını madde say
                self._cur_para.setdefault("bullet", True)
                self._cur_para.pop("_mso_pending", None)
            return
        if self._ignore_depth > 0 and tag == "span":
            self._ignore_depth -= 1
            return
        if len(self._run_stack) > 1:
            self._run_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return
        # Word HTML'inde etiketler arası whitespace anlam taşımaz;
        # sadece mevcut paragrafta içerik varsa tek boşluğa indirgenir.
        text = data.replace("\r", "").replace("\n", " ")
        if not text.strip():
            if text and self._cur_para and self._cur_para["runs"]:
                self._add_text(" ")
            return
        self._add_text(text)

    def close(self) -> None:
        super().close()
        self._flush_para()


def parse_html_to_paragraphs(html: str) -> List[dict]:
    parser = _WordHTMLParser()
    parser.feed(html)
    parser.close()

    result = []
    for para in parser.paragraphs:
        clean_runs = []
        for r in para["runs"]:
            t = r["text"]
            if not t:
                continue
            clean_runs.append({"text": t, "bold": r["bold"], "italic": r["italic"],
                                "underline": r["underline"], "color": r["color"]})
        result.append({"bullet": bool(para.get("bullet")),
                        "numbered": bool(para.get("numbered")),
                        "runs": clean_runs})
    return result


_PLAIN_BULLET_RE = re.compile(r"^\s*[-*•·]\s+")
_PLAIN_NUMBER_RE = re.compile(r"^\s*\d{1,3}[.)]\s+")


def parse_plain_to_paragraphs(text: str) -> List[dict]:
    """CF_HTML yoksa düz metinden basit madde/numara algılaması."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    result = []
    for line in text.split("\n"):
        bullet = False
        numbered = False
        content = line
        if _PLAIN_BULLET_RE.match(line):
            bullet = True
            content = _PLAIN_BULLET_RE.sub("", line, count=1)
        elif _PLAIN_NUMBER_RE.match(line):
            numbered = True
            content = _PLAIN_NUMBER_RE.sub("", line, count=1)
        runs = [{"text": content, "bold": False, "italic": False,
                 "underline": False, "color": None}] if content else []
        result.append({"bullet": bullet, "numbered": numbered, "runs": runs})
    return result
