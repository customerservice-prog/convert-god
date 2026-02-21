import json
import os
import uuid
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import Job
from .storage import s3_client, bucket_name, signed_url_expires, max_upload_bytes


def index(request):
    return render(request, "index.html", {})


@csrf_exempt
@require_http_methods(["POST"])
def presign_upload(request):
    """Create a presigned PUT url for direct upload."""
    b = bucket_name()
    if not b:
        return JsonResponse({"ok": False, "error": "S3_BUCKET not set"}, status=500)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}

    filename = (body.get("filename") or "upload").strip()[:180]
    size = int(body.get("size") or 0)
    if size <= 0:
        return JsonResponse({"ok": False, "error": "Invalid size"}, status=400)

    if size > max_upload_bytes():
        return JsonResponse({"ok": False, "error": "File too large"}, status=413)

    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"):
        # allow, but warn; ffmpeg may still handle it
        pass

    key = f"inputs/{uuid.uuid4().hex}{ext or ''}"

    c = s3_client()
    url = c.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": b,
            "Key": key,
            "ContentType": "application/octet-stream",
        },
        ExpiresIn=60 * 15,
        HttpMethod="PUT",
    )

    # Provide a simple GET URL for later (not public if bucket is private)
    return JsonResponse({"ok": True, "key": key, "put_url": url})


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
        b = bucket_name()
        if b:
            c = s3_client()
            download_url = c.generate_presigned_url(
                "get_object",
                Params={"Bucket": b, "Key": j.output_key},
                ExpiresIn=signed_url_expires(),
                HttpMethod="GET",
            )

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
