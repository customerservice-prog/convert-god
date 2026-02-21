import re
from dataclasses import dataclass


@dataclass
class SniffResult:
    ok: bool
    media_url: str | None = None
    kind: str | None = None  # mp4|m3u8|mpd
    reason: str = ""


_MP4 = re.compile(r"\.mp4(\?|$)", re.IGNORECASE)
_M3U8 = re.compile(r"\.m3u8(\?|$)", re.IGNORECASE)
_MPD = re.compile(r"\.mpd(\?|$)", re.IGNORECASE)


def _kind(url: str) -> str | None:
    if _M3U8.search(url):
        return "m3u8"
    if _MPD.search(url):
        return "mpd"
    if _MP4.search(url):
        return "mp4"
    return None


def sniff_media_url(page_url: str, *, timeout_ms: int = 20000) -> SniffResult:
    """Best-effort headless browser sniff.

    Loads the page and watches network requests for .m3u8/.mpd/.mp4.
    Does not guarantee success on all sites (JS-only, DRM, auth, geo, etc.).
    """

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return SniffResult(ok=False, reason="playwright_not_available")

    hits: list[str] = []

    def on_request(req):
        try:
            u = req.url
            k = _kind(u)
            if k:
                hits.append(u)
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context()
        page = ctx.new_page()
        page.on("request", on_request)

        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            # Even if goto times out, some requests may have been captured
            pass

        # Try to trigger lazy players
        try:
            page.mouse.wheel(0, 800)
        except Exception:
            pass

        # Wait a short window for media requests
        try:
            page.wait_for_timeout(3500)
        except Exception:
            pass

        ctx.close()
        browser.close()

    if not hits:
        return SniffResult(ok=False, reason="no_media_requests_seen")

    # Prefer m3u8 > mpd > mp4 (streaming formats are more common in players)
    def score(u: str) -> int:
        k = _kind(u) or ""
        return {"m3u8": 3, "mpd": 2, "mp4": 1}.get(k, 0)

    hits2 = sorted(list(dict.fromkeys(hits)), key=score, reverse=True)
    best = hits2[0]
    return SniffResult(ok=True, media_url=best, kind=_kind(best), reason="sniffed_from_network")
