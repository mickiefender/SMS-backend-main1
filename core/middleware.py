"""
Multi-tenant middleware for isolating data by school.
"""
import logging
import time

from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache

logger = logging.getLogger(__name__)

# TTL for cached School objects (seconds). School settings change rarely; a
# 30-minute TTL with cache invalidation on School.save is production-safe.
SCHOOL_CACHE_TTL = 1800
_SCHOOL_CACHE_PREFIX = "school_lookup"


def _school_cache_key(school_id):
    return f"{_SCHOOL_CACHE_PREFIX}:{school_id}"


class MultiTenantMiddleware(MiddlewareMixin):
    """
    Resolves the tenant School for a request from the ``X-School-Id`` header
    or ``school_id`` query parameter.

    IMPORTANT (performance): the original implementation ran
    ``School.objects.get(id=...)`` against PostgreSQL on EVERY request. With a
    Supabase transaction pooler capped at ~15 connections and many concurrent
    requests, that per-request query materially contributed to connection
    exhaustion. The school is now read from Redis first (tenant-safe key,
    scoped by school id) and only falls back to the database on a cache miss.
    """

    def process_request(self, request):
        # Extract school_id from header or query parameter
        school_id = request.META.get("HTTP_X_SCHOOL_ID") or request.GET.get("school_id")

        request.school = None

        if not school_id:
            return None

        try:
            school_id = int(school_id)
        except (TypeError, ValueError):
            return None

        # ── Redis cache fast path (no database query) ───────────────────
        cache_key = _school_cache_key(school_id)
        try:
            cached_logo_url = cache.get(cache_key)
        except Exception:
            cached_logo_url = None

        if cached_logo_url is not None:
            # A lightweight sentinel (school name + logo URL) is enough for
            # authentication/authorization decisions that only need the id.
            # If performance-critical code requires the full object it must
            # fetch it explicitly (most views use user.school, not request.school).
            request.school = cached_logo_url
            return None

        # ── Database fallback (cache miss) ─────────────────────────────
        try:
            from apps.schools.models import School

            school = School.objects.only("id", "name", "logo_url", "status").get(id=school_id)
            # Cache the resolved school (sentinel) so repeat requests for the
            # same school do not touch PostgreSQL.
            sentinel = {
                "id": school.id,
                "name": school.name,
                "logo_url": school.logo_url,
                "status": school.status,
            }
            request.school = sentinel
            try:
                cache.set(cache_key, sentinel, SCHOOL_CACHE_TTL)
            except Exception:
                pass
        except School.DoesNotExist:
            request.school = None
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("School lookup failed for %s: %s", school_id, exc)
            request.school = None

        return None


class PerformanceLoggingMiddleware(MiddlewareMixin):
    """Log the duration of each request for performance monitoring."""

    def process_request(self, request):
        request._perf_start_time = time.monotonic()
        return None

    def process_response(self, request, response):
        start_time = getattr(request, "_perf_start_time", None)
        if start_time is not None:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                'Request: %s %s took %.1fms',
                request.method,
                request.get_full_path(),
                duration_ms,
            )
        return response
