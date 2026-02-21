import os
import time
import hmac
import hashlib
from pathlib import Path
from django.conf import settings


def ensure_dirs():
    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    (Path(settings.MEDIA_ROOT) / "inputs").mkdir(parents=True, exist_ok=True)
    (Path(settings.MEDIA_ROOT) / "outputs").mkdir(parents=True, exist_ok=True)


def input_path(key: str) -> str:
    # key like inputs/<name>
    p = Path(settings.MEDIA_ROOT) / key
    return str(p)


def output_path(key: str) -> str:
    p = Path(settings.MEDIA_ROOT) / key
    return str(p)


def sign_download(job_id: str, output_key: str, exp: int) -> str:
    msg = f"{job_id}|{output_key}|{exp}".encode("utf-8")
    secret = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify_download(job_id: str, output_key: str, exp: int, sig: str) -> bool:
    try:
        if int(exp) < int(time.time()):
            return False
    except Exception:
        return False
    want = sign_download(job_id, output_key, int(exp))
    return hmac.compare_digest(want, str(sig or ""))
