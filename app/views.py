import json
import os
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse, FileResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import Job
from .disk_storage import ensure_dirs, input_path, output_path, sign_download, verify_download


def healthz(request):
    return JsonResponse({"ok": True})


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
