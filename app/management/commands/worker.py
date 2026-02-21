import os
import time
import json
import shutil
import subprocess
import tempfile

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from app.models import Job
from app.storage import s3_client, bucket_name


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
        b = bucket_name()
        if not b:
            raise SystemExit("S3_BUCKET not set")

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
        c = s3_client()
        b = bucket_name()

        in_key = job.input_key
        out_key = f"outputs/{job.id}.mp4"

        with tempfile.TemporaryDirectory() as td:
            in_path = os.path.join(td, "input")
            out_path = os.path.join(td, "output.mp4")

            # Download input
            c.download_file(b, in_key, in_path)

            # ffmpeg progress
            cmd = [
                ffmpeg_bin(),
                "-y",
                "-i",
                in_path,
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

            # Upload output
            c.upload_file(out_path, b, out_key, ExtraArgs={"ContentType": "video/mp4"})

        Job.objects.filter(id=job.id).update(
            status=Job.STATUS_DONE,
            progress=100,
            output_key=out_key,
            updated_at=timezone.now(),
        )
