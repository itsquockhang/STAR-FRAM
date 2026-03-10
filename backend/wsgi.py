"""
WSGI entrypoint for production servers (Gunicorn, uWSGI, etc).
"""

from app import app  # noqa: F401

