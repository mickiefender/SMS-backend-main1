"""Shared Supabase client factory for the feed app."""
from django.conf import settings


def get_supabase_client():
    """Return a Supabase client using the existing storage configuration.

    For server-side storage operations (when USE_SUPABASE_STORAGE=True) a Supabase
    service role key (SUPABASE_SERVICE_KEY) must be configured. Using the public
    anon key for server uploads will result in Storage API 403 errors (Invalid
    Compact JWS). This helper enforces the service key when storage is enabled
    and provides a clearer error message.
    """
    from supabase import create_client
    url = getattr(settings, 'SUPABASE_URL', None)

    # Prefer the service role key for server-side uploads. Only fall back to
    # the public key when storage is not enabled and code is running in a
    # non-storage context.
    service_key = getattr(settings, 'SUPABASE_SERVICE_KEY', None)
    public_key = getattr(settings, 'SUPABASE_KEY', None)

    # If storage is enabled, require the service role key.
    if getattr(settings, 'USE_SUPABASE_STORAGE', False):
        key = service_key
        if not url or not key:
            raise RuntimeError(
                'Supabase storage is enabled (USE_SUPABASE_STORAGE=True) but SUPABASE_SERVICE_KEY is not configured. '
                'Set SUPABASE_SERVICE_KEY to your Supabase service role key (never commit this to source control).'
            )
    else:
        # Storage not enabled: allow using public key for read-only operations.
        key = service_key or public_key
        if not url or not key:
            raise RuntimeError('SUPABASE_URL and SUPABASE_SERVICE_KEY/SUPABASE_KEY must be configured.')

    return create_client(url, key)


def get_public_url(bucket: str, path: str) -> str:
    """Return the public Supabase Storage URL for a given bucket/path."""
    base = settings.SUPABASE_URL.rstrip('/')
    return f"{base}/storage/v1/object/public/{bucket}/{path.lstrip('/')}"
