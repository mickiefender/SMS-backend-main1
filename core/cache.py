"""
Redis Cache Service for School Management System

Provides caching utilities for:
- Dashboard data caching
- Query result caching
- Session management
- Rate limiting data
- Tenant-safe multi-school caching
"""
import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable, Optional

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Cache key prefixes
CACHE_KEYS = {
    'dashboard_stats': 'dashboard:stats:{school_id}',
    'dashboard_earnings': 'dashboard:earnings:{school_id}',
    'student_count': 'counts:students:{school_id}',
    'teacher_count': 'counts:teachers:{school_id}',
    'class_count': 'counts:classes:{school_id}',
    'subject_count': 'counts:subjects:{school_id}',
    'user_session': 'session:{user_id}',
    'api_rate_limit': 'rate_limit:{user_id}:{endpoint}',
    'notification_count': 'notifications:{user_id}:unread',
    'recent_activities': 'activities:{school_id}:recent',
    'school': 'school:{school_id}',
    'school_settings': 'school:settings:{school_id}',
    'plan': 'plan:{plan_id}',
    'announcements': 'announcements:{school_id}',
    'news': 'news:{school_id}',
    'news_list': 'news:list:{school_id}',
    'notices': 'notices:{school_id}',
    'class_performance': 'academics:class_performance:{school_id}',
    'teacher_dashboard': 'academics:teacher_dashboard:{school_id}:{user_id}',
    'teacher_performance': 'academics:teacher_performance:{school_id}:{user_id}',
    'overall_attendance': 'attendance:overall:{school_id}',
    'student_classes': 'academics:student_classes:{school_id}',
    'super_admin_usage': 'super_admin:usage',
    'super_admin_analytics': 'super_admin:analytics',
    'billing_fees': 'billing:fees:{school_id}',
    'billing_payments_school': 'billing:payments:school:{school_id}',
    'academic_sessions': 'academics:sessions:{school_id}',
    'grading_scales': 'academics:grading_scales:{school_id}',
    'assessment_types': 'academics:assessment_types:{school_id}',
    'notice_board': 'notices:board:{school_id}',
}

# Cache TTL values (in seconds)
CACHE_TTL = {
    'dashboard_stats': 300,          # 5 minutes
    'counts': 600,                   # 10 minutes
    'user_session': 3600,            # 1 hour
    'api_rate_limit': 60,            # 1 minute
    'notification_count': 30,        # 30 seconds
    'recent_activities': 120,        # 2 minutes
    'school': 1800,                  # 30 minutes
    'school_settings': 1800,         # 30 minutes
    'plan': 3600,                    # 60 minutes
    'announcements': 600,            # 10 minutes
    'news': 600,                     # 10 minutes
    'notices': 600,                  # 10 minutes
    'class_performance': 300,        # 5 minutes
    'teacher_dashboard': 300,        # 5 minutes
    'teacher_performance': 300,      # 5 minutes
    'overall_attendance': 300,       # 5 minutes
    'student_classes': 600,          # 10 minutes
    'super_admin_usage': 600,        # 10 minutes
    'super_admin_analytics': 600,    # 10 minutes
    'billing_fees': 300,             # 5 minutes
    'billing_payments_school': 120,  # 2 minutes
    'academic_sessions': 600,        # 10 minutes
    'grading_scales': 600,           # 10 minutes
    'assessment_types': 600,         # 10 minutes
    'notice_board': 300,             # 5 minutes
}


def make_key(*parts: Any) -> str:
    """Build a safe, colon-separated cache key from parts.

    Numeric tenant/user ids are passed through; arbitrary strings are
    slugified so no cache key can ever collide across tenants.
    """
    safe_parts = []
    for part in parts:
        if isinstance(part, (int, float)):
            safe_parts.append(str(part))
        else:
            s = str(part).strip().lower()
            # Collapse whitespace/punctuation into a single underscore
            s = ''.join(c if c.isalnum() else '_' for c in s)
            s = '_'.join(filter(None, s.split('_')))
            safe_parts.append(s or 'none')
    return ':'.join(safe_parts)


def get_or_set_json(key: str, default: Callable[[], Any], ttl: Optional[int] = None) -> Any:
    """Fetch JSON-serializable value from cache, computing with ``default`` on miss.

    Returns the cached Python object (deserialized from JSON). This keeps the
    cache storage compact and avoids pickling unexpected types.
    """
    ttl = ttl if ttl is not None else CACHE_TTL['dashboard_stats']
    try:
        raw = cache.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception as e:
        logger.debug(f"Cache get failed for {key}: {e}")

    value = default()
    try:
        cache.set(key, json.dumps(value, default=str), ttl)
    except Exception as e:
        logger.debug(f"Cache set failed for {key}: {e}")
    return value


def invalidate_keys(*keys: str) -> None:
    """Delete one or more cache keys, swallowing Redis errors."""
    try:
        cache.delete_many([k for k in keys if k])
    except Exception as e:
        logger.debug(f"Cache invalidation failed: {e}")


class DashboardCache:
    """Dashboard-specific caching utilities"""

    @staticmethod
    def get_stats_cache_key(school_id: int) -> str:
        """Get cache key for school dashboard stats"""
        return CACHE_KEYS['dashboard_stats'].format(school_id=school_id)

    @staticmethod
    def get_earnings_cache_key(school_id: int) -> str:
        """Get cache key for school earnings"""
        return CACHE_KEYS['dashboard_earnings'].format(school_id=school_id)

    @staticmethod
    def get_school_counts_cache_keys(school_id: int) -> dict:
        """Get all count cache keys for a school"""
        return {
            'students': CACHE_KEYS['student_count'].format(school_id=school_id),
            'teachers': CACHE_KEYS['teacher_count'].format(school_id=school_id),
            'classes': CACHE_KEYS['class_count'].format(school_id=school_id),
            'subjects': CACHE_KEYS['subject_count'].format(school_id=school_id),
        }

    @staticmethod
    def cache_stats(school_id: int, data: dict, ttl: int = None) -> bool:
        """Cache dashboard stats for a school"""
        key = DashboardCache.get_stats_cache_key(school_id)
        ttl = ttl or CACHE_TTL['dashboard_stats']
        try:
            cache.set(key, json.dumps(data, default=str), ttl)
            logger.debug(f"Cached dashboard stats for school {school_id}")
            return True
        except Exception as e:
            logger.error(f"Error caching dashboard stats: {e}")
            return False

    @staticmethod
    def get_stats(school_id: int) -> Optional[dict]:
        """Get cached dashboard stats for a school"""
        key = DashboardCache.get_stats_cache_key(school_id)
        try:
            raw = cache.get(key)
            if raw is not None:
                return json.loads(raw)
        except Exception as e:
            logger.error(f"Error getting cached dashboard stats: {e}")
            return None
        return None

    @staticmethod
    def invalidate_stats(school_id: int) -> bool:
        """Invalidate all dashboard caches for a school"""
        keys = [
            DashboardCache.get_stats_cache_key(school_id),
            DashboardCache.get_earnings_cache_key(school_id),
        ]
        keys.extend(DashboardCache.get_school_counts_cache_keys(school_id).values())
        # Attendance + performance feeds the dashboard too
        keys.append(CACHE_KEYS['overall_attendance'].format(school_id=school_id))
        keys.append(CACHE_KEYS['class_performance'].format(school_id=school_id))

        try:
            cache.delete_many(keys)
            logger.debug(f"Invalidated dashboard caches for school {school_id}")
            return True
        except Exception as e:
            logger.error(f"Error invalidating dashboard cache: {e}")
            return False

    @staticmethod
    def cache_counts(school_id: int, counts: dict, ttl: int = None) -> bool:
        """Cache school counts (students, teachers, etc.)"""
        keys = DashboardCache.get_school_counts_cache_keys(school_id)
        ttl = ttl or CACHE_TTL['counts']

        try:
            cache.set_many({
                keys['students']: json.dumps(counts.get('students', 0)),
                keys['teachers']: json.dumps(counts.get('teachers', 0)),
                keys['classes']: json.dumps(counts.get('classes', 0)),
                keys['subjects']: json.dumps(counts.get('subjects', 0)),
            }, ttl)
            return True
        except Exception as e:
            logger.error(f"Error caching counts: {e}")
            return False


class RateLimitCache:
    """Rate limiting using Redis"""

    @staticmethod
    def get_rate_limit_key(user_id: int, endpoint: str) -> str:
        """Generate rate limit cache key"""
        # Create a hash of the endpoint to keep key length manageable
        endpoint_hash = hashlib.md5(endpoint.encode()).hexdigest()[:8]
        return CACHE_KEYS['api_rate_limit'].format(
            user_id=user_id,
            endpoint=endpoint_hash
        )

    @staticmethod
    def check_rate_limit(
        user_id: int,
        endpoint: str,
        limit: int,
        window: int = 60
    ) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit

        Args:
            user_id: The user ID
            endpoint: The API endpoint
            limit: Maximum requests allowed in the window
            window: Time window in seconds (default: 60)

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        key = RateLimitCache.get_rate_limit_key(user_id, endpoint)

        try:
            # Try to increment the counter
            current = cache.incr(key)

            # If this is the first request in the window, set expiry
            if current == 1:
                cache.expire(key, window)

            # Calculate remaining
            remaining = max(0, limit - current)
            is_allowed = current <= limit

            return is_allowed, remaining

        except ValueError:
            # Key doesn't exist or can't be incremented
            cache.set(key, 1, window)
            return True, limit - 1
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # On error, allow the request
            return True, limit

    @staticmethod
    def reset_rate_limit(user_id: int, endpoint: str) -> bool:
        """Reset rate limit for a user on an endpoint"""
        key = RateLimitCache.get_rate_limit_key(user_id, endpoint)
        try:
            cache.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error resetting rate limit: {e}")
            return False


class NotificationCache:
    """Notification caching utilities"""

    @staticmethod
    def get_unread_count_key(user_id: int) -> str:
        """Get cache key for user's unread notification count"""
        return CACHE_KEYS['notification_count'].format(user_id=user_id)

    @staticmethod
    def cache_unread_count(user_id: int, count: int) -> bool:
        """Cache user's unread notification count"""
        key = NotificationCache.get_unread_count_key(user_id)
        try:
            cache.set(key, count, CACHE_TTL['notification_count'])
            return True
        except Exception as e:
            logger.error(f"Error caching notification count: {e}")
            return False

    @staticmethod
    def get_unread_count(user_id: int) -> Optional[int]:
        """Get cached unread notification count"""
        key = NotificationCache.get_unread_count_key(user_id)
        try:
            raw = cache.get(key)
            return int(raw) if raw is not None else None
        except Exception as e:
            logger.error(f"Error getting notification count: {e}")
            return None

    @staticmethod
    def invalidate_unread_count(user_id: int) -> bool:
        """Invalidate cached notification count"""
        key = NotificationCache.get_unread_count_key(user_id)
        try:
            cache.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error invalidating notification count: {e}")
            return False


class ActivityCache:
    """Recent activities caching"""

    @staticmethod
    def get_recent_activities_key(school_id: int) -> str:
        """Get cache key for school's recent activities"""
        return CACHE_KEYS['recent_activities'].format(school_id=school_id)

    @staticmethod
    def cache_activities(school_id: int, activities: list) -> bool:
        """Cache recent activities"""
        key = ActivityCache.get_recent_activities_key(school_id)
        try:
            cache.set(key, json.dumps(activities, default=str), CACHE_TTL['recent_activities'])
            return True
        except Exception as e:
            logger.error(f"Error caching activities: {e}")
            return False

    @staticmethod
    def get_activities(school_id: int) -> Optional[list]:
        """Get cached recent activities"""
        key = ActivityCache.get_recent_activities_key(school_id)
        try:
            raw = cache.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as e:
            logger.error(f"Error getting cached activities: {e}")
            return None

    @staticmethod
    def invalidate_activities(school_id: int) -> bool:
        """Invalidate cached activities"""
        key = ActivityCache.get_recent_activities_key(school_id)
        try:
            cache.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error invalidating activities: {e}")
            return False


def cached_view(timeout: int = 300, key_prefix: str = 'view', cache_vary_on_user: bool = False):
    """
    Decorator to cache view responses.

    IMPORTANT: This decorator caches the serialized JSON payload — NOT the
    DRF Response object (DRF Response objects are not reliably picklable).
    The wrapped function must return something JSON-serializable (list, dict,
    str) or a DRF Response whose .data is JSON-serializable.

    Args:
        timeout: Cache timeout in seconds
        key_prefix: Prefix for cache key
        cache_vary_on_user: If True, include user id in the key. Use this only
            for data that is user-specific but expensive to compute and safe
            to share within the same user (e.g. teacher dashboard).
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method != 'GET':
                return view_func(request, *args, **kwargs)

            # Always scope by school to guarantee tenant isolation.
            # If the user has no school_id (e.g. super_admin), fall back to a
            # user-scoped key so no cross-tenant leakage can occur.
            school_id = getattr(request.user, 'school_id', None) or getattr(request.user, 'school', None) or 0
            # Use the view name + resolved kwargs to build a stable path key
            view_name = getattr(wrapper, '__name__', view_func.__name__)
            path_key = hashlib.md5(
                f"{request.path}:{sorted(request.GET.items())}".encode()
            ).hexdigest()[:12]

            key_parts = [key_prefix, view_name, str(school_id), path_key]
            if cache_vary_on_user:
                key_parts.insert(3, str(request.user.id))

            cache_key = ':'.join(key_parts)

            try:
                raw = cache.get(cache_key)
                if raw is not None:
                    logger.debug(f"Cache hit for {cache_key}")
                    return json.loads(raw)
            except Exception as e:
                logger.debug(f"Cache get error for {cache_key}: {e}")

            response = view_func(request, *args, **kwargs)

            if response.status_code == 200:
                try:
                    cache.set(cache_key, json.dumps(response.data, default=str), timeout)
                except Exception as e:
                    logger.debug(f"Cache set error for {cache_key}: {e}")

            return response
        return wrapper
    return decorator


def cached_queryset(cache_key: str, queryset, ttl: int = 300):
    """
    Cache a Django QuerySet by forcing evaluation, storing its list repr.

    Never use this for user/school-scoped querysets without including the
    tenant/user id in ``cache_key``. The typical usage is:

        qs = cached_queryset(
            f"academics:classes:{school_id}",
            Class.objects.filter(school_id=school_id),
            CACHE_TTL['student_classes'],
        )

    Only safe for small, frequently-read, rarely-written reference data.
    """
    try:
        raw = cache.get(cache_key)
        if raw is not None:
            return json.loads(raw)
    except Exception as e:
        logger.debug(f"cached_queryset get failed: {e}")

    result = list(queryset)

    try:
        cache.set(cache_key, json.dumps(result, default=str), ttl)
    except Exception as e:
        logger.debug(f"cached_queryset set failed: {e}")

    return result


def invalidate_school_caches(school_id: int) -> None:
    """Central helper: invalidate every cache key scoped to a school.

    Call this from signal handlers / service methods whenever a school's
    reference data changes (settings, classes, subjects, fees, notices...).
    """
    keys = [
        CACHE_KEYS['school'].format(school_id=school_id),
        CACHE_KEYS['school_settings'].format(school_id=school_id),
        CACHE_KEYS['announcements'].format(school_id=school_id),
        CACHE_KEYS['news'].format(school_id=school_id),
        CACHE_KEYS['news_list'].format(school_id=school_id),
        CACHE_KEYS['notices'].format(school_id=school_id),
        CACHE_KEYS['class_performance'].format(school_id=school_id),
        CACHE_KEYS['overall_attendance'].format(school_id=school_id),
        CACHE_KEYS['student_classes'].format(school_id=school_id),
        CACHE_KEYS['billing_fees'].format(school_id=school_id),
        CACHE_KEYS['billing_payments_school'].format(school_id=school_id),
        CACHE_KEYS['academic_sessions'].format(school_id=school_id),
        CACHE_KEYS['grading_scales'].format(school_id=school_id),
        CACHE_KEYS['assessment_types'].format(school_id=school_id),
        CACHE_KEYS['notice_board'].format(school_id=school_id),
    ]
    keys.extend(DashboardCache.get_school_counts_cache_keys(school_id).values())
    keys.append(DashboardCache.get_stats_cache_key(school_id))
    keys.append(DashboardCache.get_earnings_cache_key(school_id))
    invalidate_keys(*keys)


def invalidate_cache_on_save(sender, instance, **kwargs):
    """
    Signal handler to invalidate cache when models are saved.

    Usage:
        from django.db.models.signals import post_save
        from core.cache import invalidate_cache_on_save
        post_save.connect(invalidate_cache_on_save, sender=MyModel)
    """
    try:
        if hasattr(instance, 'school_id') and instance.school_id:
            invalidate_school_caches(instance.school_id)
        elif hasattr(instance, 'school') and instance.school_id:
            invalidate_school_caches(instance.school_id)
    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")
