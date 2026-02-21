import re
from urllib.parse import urljoin


_MP4_RE = re.compile(r"https?://[^\s'\"<>]+?\.mp4(?:\?[^\s'\"<>]*)?", re.IGNORECASE)
_M3U8_RE = re.compile(r"https?://[^\s'\"<>]+?\.m3u8(?:\?[^\s'\"<>]*)?", re.IGNORECASE)


def extract_best_effort(html: str, base_url: str) -> dict:
    """Best-effort extraction of a direct media URL from an HTML page.

    Not guaranteed. Returns:
      { ok: bool, kind: 'mp4'|'m3u8'|None, media_url: str|None, reason: str }

    We intentionally keep this conservative:
      - only return explicit absolute URLs found in HTML
      - do not run JS
      - no site-specific scraping in this generic extractor
    """

    text = html or ""

    # Absolute MP4 links
    m = _MP4_RE.search(text)
    if m:
        return {"ok": True, "kind": "mp4", "media_url": m.group(0), "reason": "found_mp4_in_html"}

    # Absolute HLS master/playlist links
    m = _M3U8_RE.search(text)
    if m:
        return {"ok": True, "kind": "m3u8", "media_url": m.group(0), "reason": "found_m3u8_in_html"}

    # Relative src="...mp4" patterns
    rel_mp4 = re.search(r"src\s*=\s*['\"]([^'\"]+\.mp4[^'\"]*)['\"]", text, re.IGNORECASE)
    if rel_mp4:
        u = urljoin(base_url, rel_mp4.group(1))
        return {"ok": True, "kind": "mp4", "media_url": u, "reason": "found_rel_mp4"}

    rel_m3u8 = re.search(r"src\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", text, re.IGNORECASE)
    if rel_m3u8:
        u = urljoin(base_url, rel_m3u8.group(1))
        return {"ok": True, "kind": "m3u8", "media_url": u, "reason": "found_rel_m3u8"}

    return {"ok": False, "kind": None, "media_url": None, "reason": "no_media_url_found_in_html"}
