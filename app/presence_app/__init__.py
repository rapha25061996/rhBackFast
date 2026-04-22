"""HR presence/attendance management module.

Provides presence tracking (ENTRY/EXIT), late detection, absence reporting
and statistics. Designed as a self-contained module that plugs into the
existing application without modifying existing tables (``users`` included).
"""
from app.presence_app.routes import router

__all__ = ["router"]