import os
import time
import json
import shutil
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from app.models import Job
from app.disk_storage import ensure_dirs, input_path, output_path


def ffmpeg_bin() -> str:
    return os.environ.get("FFMPEG_BIN", "ffmpeg")


def poll_seconds() -> float:
    try:
        return float(os.environ.get("WORKER_POLL_SECONDS", "2"))
    except Exception:
        return 2.0


def preset_args(preset: str):
    # Always produce MP4 H.264 + AAC with faststart.
    base = [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
    ]

    if preset == Job.PRESET_ORIGINAL:
        return base

    # Downscale only (never upscale)
    if preset == Job.PRESET_1080:
        scale = "scale='min(1920,iw)':-2"
    elif preset == Job.PRESET_720:
        scale = "scale='min(1280,iw)':-2"
    else:
        scale = "scale='min(854,iw)':-2"

    return ["-vf", scale] + base


def parse_progress_line(line: str):
    # ffmpeg -progress pipe:1 emits key=value lines
    if "=" not in line:
        return None, None
    k, v = line.strip().split("=", 1)
    return k.strip(), v.strip()


class Command(BaseCommand):
    help = "Run the conversion worker (polls DB for queued jobs)."

    def handle(self, *args, **opts):
        ensure_dirs()

        if shutil.which(ffmpeg_bin()) is None:
            self.stderr.write(self.style.ERROR(f"ffmpeg not found (FFMPEG_BIN={ffmpeg_bin()})"))
            self.stderr.write("Install ffmpeg in the worker environment or use a docker image that includes it.")

        self.stdout.write(self.style.SUCCESS("Worker started"))

        while True:
            job = None
            with transaction.atomic():
                job = (
                    Job.objects.select_for_update(skip_locked=True)
                    .filter(status=Job.STATUS_QUEUED)
                    .order_by("created_at")
                    .first()
                )
                if job:
                    job.status = Job.STATUS_PROCESSING
                    job.progress = 0
                    job.error = ""
                    job.save(update_fields=["status", "progress", "error", "updated_at"])

            if not job:
                time.sleep(poll_seconds())
                continue

            try:
                self.process_job(job)
            except Exception as e:
                Job.objects.filter(id=job.id).update(
                    status=Job.STATUS_FAILED,
                    error=f"exception:{type(e).__name__}:{e}",
                    updated_at=timezone.now(),
                )

    def process_job(self, job: Job):
        in_key = job.input_key
        out_key = f"outputs/{job.id}.mp4"

        in_path = input_path(in_key)
        out_path = output_path(out_key)

        Path(os.path.dirname(out_path)).mkdir(parents=True, exist_ok=True)

        # ffmpeg progress
        # Allow URL pointer files: first line is URL:<media_url>
        ffmpeg_input = in_path
        try:
            if os.path.isfile(in_path) and os.path.getsize(in_path) < 4096:
                with open(in_path, "r", encoding="utf-8", errors="ignore") as f:
                    head = (f.readline() or "").strip()
                if head.startswith("URL:"):
                    ffmpeg_input = head.split(":", 1)[1].strip()
        except Exception:
            ffmpeg_input = in_path

        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            ffmpeg_input,
            "-progress",
            "pipe:1",
            "-nostats",
        ] + preset_args(job.preset) + [out_path]

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        # We can't always know duration reliably for arbitrary inputs without probing.
        # We'll approximate progress by counting 'out_time_ms' up to a cap once we see it.
        last_pct = 0
        while True:
            line = p.stdout.readline() if p.stdout else ""
            if not line:
                if p.poll() is not None:
                    break
                continue

            k, v = parse_progress_line(line)
            if k == "progress" and v == "end":
                break

            # Lightweight progress: bump slowly when we see activity.
            if k == "out_time_ms":
                # Without duration, just bump up to 95% while running.
                last_pct = min(95, last_pct + 1)
                Job.objects.filter(id=job.id).update(progress=last_pct, updated_at=timezone.now())

        rc = p.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg_failed rc={rc}")

        Job.objects.filter(id=job.id).update(
            status=Job.STATUS_DONE,
            progress=100,
            output_key=out_key,
            updated_at=timezone.now(),
        )
