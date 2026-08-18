#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Uzaktan güncelleme bildirimi + kill-switch.

GitHub'daki `update_manifest.json` dosyasını okuyarak üç durumdan birine
karar verir: yeni sürüm bildirimi, kullanımı zorla engelleme ("block" —
yapımcının uygulamayı uzaktan devre dışı bırakabilmesi için), veya sessiz
geçiş. Ağ hatası/timeout durumunda her zaman sessizce "none" döner —
internete erişimi olmayan PC'lerde uygulamanın açılışını asla engellemez.
"""

import json
import urllib.request
from typing import Any, Dict, Optional

MANIFEST_URL = (
    "https://raw.githubusercontent.com/bekircanguler/pdfcreator/main/"
    "update_manifest.json"
)
DEFAULT_DOWNLOAD_URL = "https://github.com/bekircanguler/pdfcreator/releases/latest"


def fetch_manifest(timeout: float = 4.0) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(
            MANIFEST_URL, headers={"User-Agent": "pdfcreator-update-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _parse_version(v: str) -> tuple:
    parts = []
    for p in str(v).strip().lstrip("vV").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def evaluate(current_version: str, manifest: Dict[str, Any]) -> Dict[str, str]:
    """{"action": "none"|"notify"|"block", "message": str, "download_url": str}"""
    download_url = manifest.get("download_url") or DEFAULT_DOWNLOAD_URL
    cur = _parse_version(current_version)

    if manifest.get("disabled"):
        return {
            "action": "block",
            "message": manifest.get("message")
                or "Bu uygulama yapımcısı tarafından kullanımdan kaldırılmıştır.",
            "download_url": download_url,
        }

    min_supported = manifest.get("min_supported_version")
    if min_supported and cur < _parse_version(min_supported):
        return {
            "action": "block",
            "message": manifest.get("message")
                or "Bu sürüm artık desteklenmiyor. Lütfen güncel sürümü indirin.",
            "download_url": download_url,
        }

    latest = manifest.get("latest_version")
    if latest and cur < _parse_version(latest):
        return {
            "action": "notify",
            "message": f"Yeni sürüm mevcut: v{latest}",
            "download_url": download_url,
        }

    return {"action": "none", "message": "", "download_url": download_url}
