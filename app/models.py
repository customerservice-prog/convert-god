import uuid
from django.db import models


class Job(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
    ]

    PRESET_ORIGINAL = "original"
    PRESET_1080 = "1080p"
    PRESET_720 = "720p"
    PRESET_480 = "480p"

    PRESET_CHOICES = [
        (PRESET_ORIGINAL, "Original"),
        (PRESET_1080, "1080p"),
        (PRESET_720, "720p"),
        (PRESET_480, "480p"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True)
    progress = models.PositiveIntegerField(default=0)  # 0..100

    preset = models.CharField(max_length=16, choices=PRESET_CHOICES, default=PRESET_720)

    input_key = models.CharField(max_length=512)
    input_size_bytes = models.BigIntegerField(default=0)

    output_key = models.CharField(max_length=512, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    error = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.id} {self.status} {self.preset}"
