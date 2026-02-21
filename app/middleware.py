import base64
from django.conf import settings
from django.http import HttpResponse


class BasicAuthMiddleware:
    """Simple private gate.

    Enabled when BASIC_AUTH_USER and BASIC_AUTH_PASS are set.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(settings, "BASIC_AUTH_USER", None)
        pw = getattr(settings, "BASIC_AUTH_PASS", None)
        if not user or not pw:
            return self.get_response(request)

        # Allow healthchecks if you add one later.
        if request.path.startswith("/health"):
            return self.get_response(request)

        auth = request.META.get("HTTP_AUTHORIZATION") or ""
        if auth.startswith("Basic "):
            try:
                raw = base64.b64decode(auth.split(" ", 1)[1].strip()).decode("utf-8")
                u, p = raw.split(":", 1)
                if u == user and p == pw:
                    return self.get_response(request)
            except Exception:
                pass

        resp = HttpResponse("Authentication required", status=401)
        resp["WWW-Authenticate"] = 'Basic realm="Convert God"'
        return resp
