import structlog
from supabase import create_client, Client
from core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


def get_supabase_client() -> Client:
    """Return an authenticated Supabase client."""
    client = create_client(
        settings.supabase_url,
        settings.supabase_service_key,
    )
    return client


supabase: Client = get_supabase_client()