import os
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.models import Job
from app.storage import s3_client, bucket_name


class Command(BaseCommand):
    help = "Delete old inputs/outputs and DB rows."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=3, help="Delete jobs older than N days")

    def handle(self, *args, **opts):
        days = int(opts["days"])
        cutoff = timezone.now() - timedelta(days=days)

        b = bucket_name()
        c = s3_client() if b else None

        qs = Job.objects.filter(created_at__lt=cutoff)
        n = qs.count()

        for j in qs.iterator():
            if c and b:
                # Best effort deletes
                try:
                    if j.input_key:
                        c.delete_object(Bucket=b, Key=j.input_key)
                except Exception:
                    pass
                try:
                    if j.output_key:
                        c.delete_object(Bucket=b, Key=j.output_key)
                except Exception:
                    pass
            j.delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {n} jobs older than {days} days"))
