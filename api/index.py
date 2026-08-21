import os
import sys

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from urllib.parse import urlparse
from app import app


class VercelPathMiddleware:
    """
    Vercel rewrites route everything to /api/index.
    This WSGI middleware extracts the real request path from headers
    (e.g., X-Forwarded-Uri, X-Matched-Path, X-Invoke-Path, or Referer)
    so Flask routes /, /login, /register, /history correctly for both GET and POST.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        orig_path = (
            environ.get("HTTP_X_FORWARDED_URI")
            or environ.get("HTTP_X_FORWARDED_PATH")
            or environ.get("HTTP_X_INVOKE_PATH")
            or environ.get("HTTP_X_MATCHED_PATH")
        )

        # If orig_path is missing or generic /api/index, check referer for form posts
        if not orig_path or orig_path in ("/api/index", "/api/index/", "/api", "/api/"):
            ref = environ.get("HTTP_REFERER")
            if ref:
                try:
                    parsed = urlparse(ref)
                    if parsed.path and parsed.path not in ("/", "/api", "/api/index"):
                        orig_path = parsed.path
                except Exception:
                    pass

        if orig_path and orig_path not in ("/api/index", "/api/index/"):
            if "?" in orig_path:
                orig_path, qs = orig_path.split("?", 1)
                if not environ.get("QUERY_STRING"):
                    environ["QUERY_STRING"] = qs
            environ["PATH_INFO"] = orig_path

        return self.wsgi_app(environ, start_response)


# Wrap Flask with the Vercel path middleware
app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

handler = app


