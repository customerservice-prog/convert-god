from django.contrib import admin
from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "preset", "progress", "created_at", "updated_at")
    list_filter = ("status", "preset")
    search_fields = ("id", "input_key", "output_key")
