from django.contrib import admin
from django.urls import path
from app import views

urlpatterns = [
    path("admin/", admin.site.urls),

    # UI
    path("", views.index, name="index"),

    # API
    path("api/uploads/presign", views.presign_upload, name="presign_upload"),
    path("api/jobs", views.create_job, name="create_job"),
    path("api/jobs/<uuid:job_id>", views.job_status, name="job_status"),
]
