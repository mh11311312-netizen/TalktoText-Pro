import os
import sys

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app


class VercelPathMiddleware:
    """
    Vercel rewrites route everything to /api/index.
    This WSGI middleware extracts the real request path from headers
    (e.g., X-Forwarded-Uri, X-Matched-Path, or X-Invoke-Path)
    so Flask routes /, /login, /register, /history correctly.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        orig_path = (
            environ.get("HTTP_X_FORWARDED_URI")
            or environ.get("HTTP_X_FORWARDED_PATH")
            or environ.get("HTTP_X_MATCHED_PATH")
            or environ.get("HTTP_X_INVOKE_PATH")
            or environ.get("HTTP_X_NOW_ROUTE_MATCHES")
        )
        if orig_path:
            if "?" in orig_path:
                orig_path, qs = orig_path.split("?", 1)
                if not environ.get("QUERY_STRING"):
                    environ["QUERY_STRING"] = qs
            environ["PATH_INFO"] = orig_path

        return self.wsgi_app(environ, start_response)


# Wrap Flask with the Vercel path middleware
app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

handler = app


