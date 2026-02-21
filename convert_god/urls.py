from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from app import views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Healthcheck (no auth)
    path("healthz", views.healthz, name="healthz"),

    # Favicon
    path("favicon.ico", RedirectView.as_view(url="/static/app/favicon.ico", permanent=True)),

    # UI
    path("", views.index, name="index"),
    path("contact", views.contact, name="contact"),
    path("copyright-claims", views.copyright_claims, name="copyright_claims"),
    path("privacy-policy", views.privacy_policy, name="privacy_policy"),
    path("terms-of-use", views.terms_of_use, name="terms_of_use"),

    # API
    path("api/uploads", views.upload_file, name="upload_file"),
    path("api/inputs/from-url", views.input_from_url, name="input_from_url"),
    path("api/youtube/preview", views.youtube_preview, name="youtube_preview"),

    path("api/jobs", views.create_job, name="create_job"),
    path("api/jobs/<uuid:job_id>", views.job_status, name="job_status"),
    path("api/jobs/<uuid:job_id>/download", views.download_output, name="download_output"),
]
