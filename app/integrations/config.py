"""
Integration credentials — read from env or hardcoded defaults for this deployment.
Production: set via environment variables.
"""
import os

FLOWINTEL_BASE_URL = os.getenv("FLOWINTEL_URL", "http://127.0.0.1:7006")
FLOWINTEL_API_KEY  = os.getenv("FLOWINTEL_API_KEY",
                                "aO4EEcQ50S1ouVaobz6okouwpsBUjNIqXgjyD0hP7IZuEwYkdQ94m55y2fR7")

MISP_BASE_URL      = os.getenv("MISP_URL", "https://ronda.iww.web.id")
MISP_API_KEY       = os.getenv("MISP_API_KEY",
                                "clDzr5Nf6ZGzstnU8Mxn7VEQq2FGIHvEaS67BoLc")
MISP_VERIFY_SSL    = os.getenv("MISP_VERIFY_SSL", "false").lower() == "true"
