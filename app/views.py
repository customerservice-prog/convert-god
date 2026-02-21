import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import urllib.parse

from django.conf import settings
from django.http import JsonResponse, FileResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import Job
from .disk_storage import ensure_dirs, input_path, output_path, sign_download, verify_download
from .extractors import extract_best_effort, extract_src_from_embed


def _is_youtube_url(u: str) -> bool:
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host in ("youtube.com", "m.youtube.com", "youtu.be") or host.endswith(".youtube.com")
    except Exception:
        return False


def _is_http_url(u: str) -> bool:
    try:
        p = urlparse(u)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _safe_ext_from_url(u: str) -> str:
    try:
        path = urlparse(u).path or ""
        ext = os.path.splitext(path)[1].lower()
        if ext and len(ext) <= 8:
            return ext
    except Exception:
        pass
    return ""


def healthz(request):
    return JsonResponse({"ok": True})


def contact(request):
    return render(request, "contact.html", {"title": "Contact"})


def copyright_claims(request):
    return render(request, "copyright_claims.html", {"title": "Copyright Claims"})


def privacy_policy(request):
    return render(request, "privacy_policy.html", {"title": "Privacy Policy"})


def terms_of_use(request):
    return render(request, "terms_of_use.html", {"title": "Terms of Use"})


def index(request):
    return render(request, "index.html", {})


def _max_upload_bytes() -> int:
    try:
        return int(os.environ.get("MAX_UPLOAD_BYTES", str(1024**3)))
    except Exception:
        return 1024**3


def _signed_url_expires() -> int:
    try:
        return int(os.environ.get("SIGNED_URL_EXPIRES", "3600"))
    except Exception:
        return 3600


@csrf_exempt
@require_http_methods(["POST"])
def upload_file(request):
    """Upload a file directly to the server (disk-backed).

    Private-only mode. For public scale, switch to R2/S3 presigned uploads.
    """
    ensure_dirs()

    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"ok": False, "error": "Missing file"}, status=400)

    if f.size and int(f.size) > _max_upload_bytes():
        return JsonResponse({"ok": False, "error": "File too large"}, status=413)

    filename = (getattr(f, "name", "upload") or "upload")[:180]
    ext = os.path.splitext(filename)[1].lower()
    key = f"inputs/{uuid.uuid4().hex}{ext or ''}"
    dst = input_path(key)

    Path(os.path.dirname(dst)).mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)

    return JsonResponse({"ok": True, "key": key, "size": int(f.size or 0)})


@csrf_exempt
@require_http_methods(["POST"])
def input_from_url(request):
    """Fetch an input file from a direct URL.

    Supports:
      - direct media file URLs (preferred)
      - best-effort webpage extraction (HTML -> find embedded mp4/m3u8)
      - pasted embed code (iframe/video/source) by extracting its src

    Not guaranteed for all sites.
    """
    ensure_dirs()

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}

    raw = (body.get("url") or "").strip()
    if not raw:
        return JsonResponse({"ok": False, "error": "Invalid URL"}, status=400)

    # Allow users to paste full embed markup.
    url = raw
    if "<" in raw and "src" in raw.lower():
        src = extract_src_from_embed(raw)
        if src:
            url = src

    if not url or not _is_http_url(url):
        return JsonResponse({"ok": False, "error": "Invalid URL"}, status=400)

    # Note: we accept any http(s) URL, but this endpoint only works for *direct file* URLs.
    # If you paste a webpage (YouTube/Rumble/etc), it will usually return text/html and we will reject it.

    # Download with a hard cap (1GB default)
    cap = _max_upload_bytes()
    ext = _safe_ext_from_url(url)
    key = f"inputs/{uuid.uuid4().hex}{ext}"
    dst = input_path(key)
    Path(os.path.dirname(dst)).mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(url, headers={"User-Agent": "ConvertGod/1.0"})

    size = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ct = (resp.headers.get("Content-Type") or "").lower()
            if ct.startswith("text/html"):
                # Best-effort webpage extraction: try to find a direct MP4/M3U8 in the HTML.
                try:
                    html = resp.read(cap if cap < (3 * 1024 * 1024) else (3 * 1024 * 1024)).decode("utf-8", errors="ignore")
                except Exception:
                    html = ""

                ex = extract_best_effort(html, url)
                if not ex.get("ok"):
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "This URL appears to be a webpage. Convert God can only convert direct media URLs (MP4/MOV/etc).\n\nBest-effort page scan did not find an embedded MP4/HLS link.\n\nTip: look for a direct file URL (often ends in .mp4) or download the source file and upload it here.",
                            "error_code": "webpage_no_media_found",
                            "content_type": ct,
                        },
                        status=400,
                    )

                media_url = str(ex.get("media_url") or "").strip()
                kind = str(ex.get("kind") or "").strip()
                if not media_url:
                    return JsonResponse({"ok": False, "error": "Extraction failed"}, status=400)

                # Write a small URL pointer file. Worker will let ffmpeg ingest the URL directly.
                url_key = f"inputs/{uuid.uuid4().hex}.url"
                url_dst = input_path(url_key)
                Path(os.path.dirname(url_dst)).mkdir(parents=True, exist_ok=True)
                with open(url_dst, "w", encoding="utf-8") as f:
                    f.write(f"URL:{media_url}\n")
                    f.write(f"KIND:{kind}\n")
                    f.write(f"SRC:{url}\n")

                return JsonResponse({"ok": True, "key": url_key, "size": 0, "note": "extracted_media_url"})

            # Optional early reject if content-length is present
            cl = resp.headers.get("Content-Length")
            if cl:
                try:
                    if int(cl) > cap:
                        return JsonResponse({"ok": False, "error": "File too large"}, status=413)
                except Exception:
                    pass

            with open(dst, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > cap:
                        try:
                            out.close()
                        finally:
                            try:
                                os.remove(dst)
                            except Exception:
                                pass
                        return JsonResponse({"ok": False, "error": "File too large"}, status=413)
                    out.write(chunk)
    except Exception:
        try:
            if os.path.exists(dst):
                os.remove(dst)
        except Exception:
            pass
        return JsonResponse({"ok": False, "error": "Failed to fetch URL"}, status=400)

    return JsonResponse({"ok": True, "key": key, "size": int(size)})


@require_http_methods(["GET"])
def youtube_preview(request):
    """Preview only (safe): fetch title+thumbnail using YouTube oEmbed."""
    url = (request.GET.get("url") or "").strip()
    if not url or not _is_http_url(url) or not _is_youtube_url(url):
        return JsonResponse({"ok": False, "error": "Invalid YouTube URL"}, status=400)

    # YouTube oEmbed endpoint (no API key required)
    oembed = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
    try:
        with urllib.request.urlopen(oembed, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"ok": False, "error": "Preview failed"}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "preview": {
                "title": data.get("title") or "",
                "thumbnail_url": data.get("thumbnail_url") or "",
                "author_name": data.get("author_name") or "",
                "provider_name": data.get("provider_name") or "YouTube",
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def create_job(request):
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}

    preset = (body.get("preset") or Job.PRESET_720).strip()
    input_key = (body.get("input_key") or "").strip()
    input_size = int(body.get("input_size_bytes") or 0)

    if preset not in dict(Job.PRESET_CHOICES):
        return JsonResponse({"ok": False, "error": "Invalid preset"}, status=400)
    if not input_key.startswith("inputs/"):
        return JsonResponse({"ok": False, "error": "Invalid input_key"}, status=400)

    # Validate input exists
    p = input_path(input_key)
    if not os.path.exists(p):
        return JsonResponse({"ok": False, "error": "Input not found"}, status=400)

    j = Job.objects.create(
        status=Job.STATUS_QUEUED,
        preset=preset,
        input_key=input_key,
        input_size_bytes=max(0, input_size),
        progress=0,
    )
    return JsonResponse({"ok": True, "id": str(j.id)})


@require_http_methods(["GET"])
def job_status(request, job_id):
    j = Job.objects.filter(id=job_id).first()
    if not j:
        return JsonResponse({"ok": False, "error": "Not found"}, status=404)

    download_url = None
    if j.status == Job.STATUS_DONE and j.output_key:
        exp = int(time.time()) + _signed_url_expires()
        sig = sign_download(str(j.id), j.output_key, exp)
        download_url = f"/api/jobs/{j.id}/download?exp={exp}&sig={sig}"

    return JsonResponse(
        {
            "ok": True,
            "job": {
                "id": str(j.id),
                "status": j.status,
                "progress": int(j.progress or 0),
                "preset": j.preset,
                "error": j.error,
                "download_url": download_url,
            }
        }
    )


@require_http_methods(["GET"])
def download_output(request, job_id):
    j = Job.objects.filter(id=job_id).first()
    if not j or j.status != Job.STATUS_DONE or not j.output_key:
        return JsonResponse({"ok": False, "error": "Not found"}, status=404)

    exp = request.GET.get("exp")
    sig = request.GET.get("sig")
    try:
        exp_i = int(exp)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid exp"}, status=400)

    if not verify_download(str(j.id), j.output_key, exp_i, sig or ""):
        return JsonResponse({"ok": False, "error": "Invalid signature"}, status=403)

    fp = output_path(j.output_key)
    if not os.path.exists(fp):
        return JsonResponse({"ok": False, "error": "Missing file"}, status=404)

    return FileResponse(open(fp, "rb"), as_attachment=True, filename=f"{j.id}.mp4", content_type="video/mp4")
