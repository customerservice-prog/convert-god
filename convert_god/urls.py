from django.contrib import admin
from django.urls import path
from app import views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Healthcheck (no auth)
    path("healthz", views.healthz, name="healthz"),

    # UI
    path("", views.index, name="index"),

    # API
    path("api/uploads", views.upload_file, name="upload_file"),
    path("api/jobs", views.create_job, name="create_job"),
    path("api/jobs/<uuid:job_id>", views.job_status, name="job_status"),
    path("api/jobs/<uuid:job_id>/download", views.download_output, name="download_output"),
]
