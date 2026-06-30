"""
Custom Redis-based Throttling for DRF

Provides role-based rate limiting using Redis for:
- Per-user rate limiting
- Per-role rate limiting
- API endpoint specific rate limiting
"""
import logging
from rest_framework.throttling import SimpleRateThrottle
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class RedisRateThrottle(SimpleRateThrottle):
    """
    Base throttle class using Redis for rate limiting
    """
    scope = None
    rate = None
    
    def get_cache_key(self, request, view):
        """Generate cache key for rate limiting"""
        if not request.user or not request.user.is_authenticated:
            # Use IP address for anonymous users
            ident = self.get_ident(request)
        else:
            # Use user ID for authenticated users
            ident = request.user.pk
        
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }
    
    def allow_request(self, request, view):
        """Check if request is allowed based on rate limit"""
        # Get the rate for this throttle
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        
        # Get the cache key
        self.key = self.get_cache_key(request, view)
        
        if self.key is None:
            return True
        
        try:
            # Try to get the current count from cache
            self.history = cache.get(self.key, [])
        except Exception as e:
            logger.error(f"Rate limit cache error: {e}")
            # On cache error, allow the request
            return True
        
        # Get current timestamp
        self.now = self.timer()
        
        # Trim history to within the duration window
        self.history = [timestamp for timestamp in self.history if timestamp > self.now - self.duration]
        
        # Check if we're within the limit
        if len(self.history) >= self.num_requests:
            return self.wait()
        
        return True
    
    def wait(self):
        """Calculate time to wait before next request"""
        if self.history:
            remaining_duration = self.duration - (self.now - self.history[0])
            available_requests = self.num_requests - len(self.history) + 1
            if available_requests <= 0:
                wait_time = remaining_duration / (self.num_requests + 1)
                return max(0, wait_time)
        return None


class UserRoleRateThrottle(RedisRateThrottle):
    """
    Rate throttle based on user role
    """
    role_scope_map = {
        'super_admin': 'school_admins',
        'school_admin': 'school_admins',
        'teacher': 'teachers',
        'student': 'students',
    }
    
    def get_rate(self):
        """Get rate based on user role"""
        # Use getattr to safely access request
        request = getattr(self, 'request', None)
        
        if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
            return settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}).get('anon', '100/minute')
        
        user_role = getattr(request.user, 'role', 'user')
        scope = self.role_scope_map.get(user_role, 'user')
        
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        return rates.get(scope, rates.get('user', '200/minute'))


class AnonRateThrottle(RedisRateThrottle):
    """
    Rate throttle for anonymous users
    """
    scope = 'anon'
    
    def get_rate(self):
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        return rates.get('anon', '100/minute')
    
    def get_cache_key(self, request, view):
        """Use IP address for anonymous users"""
        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class UserRateThrottle(RedisRateThrottle):
    """
    Rate throttle for authenticated users
    """
    scope = 'user'
    
    def get_rate(self):
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        return rates.get('user', '200/minute')
    
    def get_cache_key(self, request, view):
        """Use user ID for authenticated users"""
        if not request.user or not request.user.is_authenticated:
            return None
        
        ident = request.user.pk
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class BurstRateThrottle(RedisRateThrottle):
    """
    Burst rate throttle for short-term high traffic
    """
    scope = 'burst'
    
    def get_rate(self):
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        return rates.get('burst', '20/minute')


class SustainedRateThrottle(RedisRateThrottle):
    """
    Sustained rate throttle for long-term usage
    """
    scope = 'sustained'
    
    def get_rate(self):
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        return rates.get('sustained', '1000/day')


class APIEndpointRateThrottle(RedisRateThrottle):
    """
    Rate throttle specific to API endpoints
    """
    endpoint_scope_map = {
        '/api/users/': 'user',
        '/api/billing/': 'billing',
        '/api/attendance/': 'attendance',
        '/api/grades/': 'grades',
        '/api/assignments/': 'assignments',
    }
    
    def get_rate(self, request=None):
        """Get rate based on endpoint"""
        if request is None:
            return '100/minute'
        
        path = request.path
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        
        # Find matching endpoint scope
        for endpoint, scope in self.endpoint_scope_map.items():
            if path.startswith(endpoint):
                return rates.get(scope, '100/minute')
        
        return rates.get('user', '200/minute')
    
    def allow_request(self, request, view):
        """Check rate limit for specific endpoint"""
        self.request = request
        self.rate = self.get_rate(request)
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.key = self.get_cache_key(request, view)
        
        if self.key is None:
            return True
        
        try:
            self.history = cache.get(self.key, [])
        except Exception as e:
            logger.error(f"Rate limit cache error: {e}")
            return True
        
        self.now = self.timer()
        self.history = [timestamp for timestamp in self.history if timestamp > self.now - self.duration]
        
        if len(self.history) >= self.num_requests:
            return self.wait()
        
        return True


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

