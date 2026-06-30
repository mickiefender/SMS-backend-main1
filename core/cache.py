"""
Redis Cache Service for School Management System

Provides caching utilities for:
- Dashboard data caching
- Query result caching
- Session management
- Rate limiting data
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
}

# Cache TTL values (in seconds)
CACHE_TTL = {
    'dashboard_stats': 300,        # 5 minutes
    'counts': 600,                  # 10 minutes
    'user_session': 3600,           # 1 hour
    'api_rate_limit': 60,           # 1 minute
    'notification_count': 30,      # 30 seconds
    'recent_activities': 120,      # 2 minutes
}


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
            cache.set(key, data, ttl)
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
            return cache.get(key)
        except Exception as e:
            logger.error(f"Error getting cached dashboard stats: {e}")
            return None
    
    @staticmethod
    def invalidate_stats(school_id: int) -> bool:
        """Invalidate all dashboard caches for a school"""
        keys = [
            DashboardCache.get_stats_cache_key(school_id),
            DashboardCache.get_earnings_cache_key(school_id),
        ]
        keys.extend(DashboardCache.get_school_counts_cache_keys(school_id).values())
        
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
                keys['students']: counts.get('students', 0),
                keys['teachers']: counts.get('teachers', 0),
                keys['classes']: counts.get('classes', 0),
                keys['subjects']: counts.get('subjects', 0),
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
            return cache.get(key)
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
            cache.set(key, activities, CACHE_TTL['recent_activities'])
            return True
        except Exception as e:
            logger.error(f"Error caching activities: {e}")
            return False
    
    @staticmethod
    def get_activities(school_id: int) -> Optional[list]:
        """Get cached recent activities"""
        key = ActivityCache.get_recent_activities_key(school_id)
        try:
            return cache.get(key)
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


def cached_view(timeout: int = 300, key_prefix: str = 'view'):
    """
    Decorator to cache view responses
    
    Args:
        timeout: Cache timeout in seconds
        key_prefix: Prefix for cache key
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Skip cache for authenticated users on personalized endpoints
            if hasattr(request, 'user') and request.user.is_authenticated:
                # Don't cache user-specific data by default
                return view_func(request, *args, **kwargs)
            
            # Generate cache key from request path and query params
            cache_key = f"{key_prefix}:{request.path}:{hash(frozenset(request.GET.items()))}"
            
            try:
                cached_response = cache.get(cache_key)
                if cached_response is not None:
                    logger.debug(f"Cache hit for {cache_key}")
                    return cached_response
            except Exception as e:
                logger.error(f"Cache get error: {e}")
            
            # Execute view and cache response
            response = view_func(request, *args, **kwargs)
            
            # Only cache successful GET responses
            if request.method == 'GET' and response.status_code == 200:
                try:
                    cache.set(cache_key, response, timeout)
                except Exception as e:
                    logger.error(f"Cache set error: {e}")
            
            return response
        return wrapper
    return decorator


def invalidate_cache_on_save(sender, instance, **kwargs):
    """
    Signal handler to invalidate cache when models are saved
    
    Usage:
        from django.db.models.signals import post_save
        from core.cache import invalidate_cache_on_save
        post_save.connect(invalidate_cache_on_save, sender=MyModel)
    """
    try:
        if hasattr(instance, 'school_id'):
            school_id = instance.school_id
            DashboardCache.invalidate_stats(school_id)
            ActivityCache.invalidate_activities(school_id)
    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")

