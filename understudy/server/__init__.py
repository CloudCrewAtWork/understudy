"""Local FastAPI server for the Understudy memory-graph UI.

Binds 127.0.0.1 only. Requires CSRF token on every mutating request.
Rejects Origin / Host that isn't the session's own.
"""

from .app import create_app

__all__ = ["create_app"]
