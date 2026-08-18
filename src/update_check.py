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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

MANIFEST_URL = (
    "https://raw.githubusercontent.com/bekircanguler/pdfcreator/main/"
    "update_manifest.json"
)
DEFAULT_DOWNLOAD_URL = "https://github.com/bekircanguler/pdfcreator/releases/latest"

# Tanı kaydı — güncelleme kontrolü sessizce başarısız olduğunda (ağ/proxy/
# güvenlik duvarı sorunları) nedenini görebilmek için kullanıcının ev
# klasörüne küçük bir log dosyası yazılır. Bu dosya isteğe bağlıdır;
# yazma başarısız olursa da güncelleme kontrolü etkilenmez.
LOG_PATH = Path.home() / "pdfcreator_update_check.log"


def _log(msg: str) -> None:
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def fetch_manifest(timeout: float = 4.0) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(
            MANIFEST_URL, headers={"User-Agent": "pdfcreator-update-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
        if isinstance(data, dict):
            _log(f"OK latest_version={data.get('latest_version')} "
                 f"disabled={data.get('disabled')}")
            return data
        _log(f"OK ama beklenmeyen içerik (dict değil): {raw[:200]!r}")
        return None
    except Exception as e:
        _log(f"HATA {type(e).__name__}: {e}")
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
