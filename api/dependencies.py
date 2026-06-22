"""
api/dependencies.py — AI Radar
Shared FastAPI dependencies injected into route handlers.
"""
from functools import lru_cache
from supabase import create_client, Client
from config import settings


@lru_cache(maxsize=1)
def get_db() -> Client:
    """Singleton Supabase client — reused across all requests."""
    return create_client(settings.supabase_url, settings.supabase_service_key)
