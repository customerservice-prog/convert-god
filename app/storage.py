import os
import boto3
from django.conf import settings


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        region_name=os.environ.get("S3_REGION", "auto"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
    )


def bucket_name() -> str:
    return os.environ.get("S3_BUCKET", "")


def signed_url_expires() -> int:
    try:
        return int(os.environ.get("SIGNED_URL_EXPIRES", "3600"))
    except Exception:
        return 3600


def max_upload_bytes() -> int:
    try:
        return int(os.environ.get("MAX_UPLOAD_BYTES", str(1024**3)))
    except Exception:
        return 1024**3
