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


# Paths that should never be recorded as staff activity.
_STAFF_ACTIVITY_EXCLUDED = (
    "/staff-activity",       # the activity API itself
    "/token/refresh",        # silent token renewal
)


class StaffActivityMiddleware(MiddlewareMixin):
    """
    Record real admin-staff activity for the dashboard charts.

    DRF (SimpleJWT) authenticates per-view, so ``request.user`` is NOT
    resolved at middleware time. Instead, in the response phase we decode
    the Bearer JWT ourselves to identify admin-staff callers, then log
    successful write requests (POST/PUT/PATCH/DELETE) as activity entries.

    Dedupe: identical user+path writes are logged at most once per minute
    (cache-guarded) so bulk UI polling cannot flood the chart.
    """

    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    APPROVAL_KEYWORDS = ("approve", "publish", "mark_paid", "verify", "confirm")

    def process_response(self, request, response):
        try:
            if request.method not in self.WRITE_METHODS:
                return response
            if not (200 <= response.status_code < 300):
                return response

            path = request.path or ""
            if any(marker in path for marker in _STAFF_ACTIVITY_EXCLUDED):
                return response

            user = self._resolve_staff_user(request)
            if user is None:
                return response

            # Dedupe identical writes within a 60s window.
            from django.core.cache import cache
            dedupe_key = f"staff_activity:{user.id}:{request.method}:{path}"
            if not cache.add(dedupe_key, 1, 60):
                return response

            action_type = (
                "approval"
                if any(kw in path.lower() for kw in self.APPROVAL_KEYWORDS)
                else "task"
            )
            title = self._human_title(request.method, path)

            from .models import log_staff_activity
            log_staff_activity(user, action_type=action_type, title=title, path=path)
        except Exception:
            # Activity logging must never break the actual request.
            logger.debug("StaffActivityMiddleware failed", exc_info=True)
        return response

    def _resolve_staff_user(self, request):
        """Return the User for admin-staff JWT callers, else None."""
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()

        from rest_framework_simplejwt.tokens import AccessToken
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            validated = AccessToken(token)
            user = User.objects.filter(
                id=validated.get("user_id"),
                is_active=True,
            ).first()
        except Exception:
            return None

        if user is None:
            return None
        staff_roles = {"academic_admin", "exam_officer", "finance_officer", "ct_admin_support"}
        if getattr(user, "role", None) not in staff_roles:
            return None
        return user

    @staticmethod
    def _human_title(method, path):
        """Turn '/api/billing/manual-payments/' + POST into 'Created manual-payments'."""
        verb_map = {
            "POST": "Created",
            "PUT": "Updated",
            "PATCH": "Updated",
            "DELETE": "Deleted",
        }
        verb = verb_map.get(method, method.title())
        segment = path.rstrip("/").split("/")[-1] if path else ""
        readable = segment.replace("-", " ").replace("_", " ")
        return f"{verb} {readable}".strip() or f"{verb} resource"


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
