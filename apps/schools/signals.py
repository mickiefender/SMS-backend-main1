def _invalidate_school_lookup_cache(school_id):
    """Delete the cached school sentinel used by MultiTenantMiddleware."""
    if not school_id:
        return
    try:
        from django.core.cache import cache
        from core.middleware import _school_cache_key
        cache.delete(_school_cache_key(school_id))
    except Exception:
        pass


def register_signal_handlers():
    """
    Register Django signal handlers for the schools app.
    """
    from django.db.models.signals import post_save, post_delete
    from django.dispatch import receiver

    from apps.schools.models import School

    @receiver(post_save, sender=School)
    def school_saved(sender, instance, **kwargs):
        # Keep the middleware's per-school cache consistent whenever a school
        # record changes (name, logo_url, status...).
        _invalidate_school_lookup_cache(instance.pk)

    @receiver(post_delete, sender=School)
    def school_deleted(sender, instance, **kwargs):
        _invalidate_school_lookup_cache(instance.pk)
