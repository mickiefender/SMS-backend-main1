from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from core.cache import (
    CACHE_TTL,
    _generation_key,
    cached_api_response,
    invalidate_cache_namespaces,
)


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'cache-policy-tests',
    },
})
class CachePolicyTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_ttls_follow_data_volatility(self):
        self.assertGreaterEqual(CACHE_TTL['dashboard_stats'], 30)
        self.assertLessEqual(CACHE_TTL['dashboard_stats'], 60)
        self.assertGreaterEqual(CACHE_TTL['attendance'], 30)
        self.assertLessEqual(CACHE_TTL['attendance'], 60)
        self.assertEqual(CACHE_TTL['notifications'], 30)
        self.assertEqual(CACHE_TTL['students'], 300)
        self.assertEqual(CACHE_TTL['teachers'], 300)
        self.assertEqual(CACHE_TTL['class_subject_pages'], 300)
        self.assertGreaterEqual(CACHE_TTL['courses'], 600)
        self.assertLessEqual(CACHE_TTL['courses'], 900)
        self.assertGreaterEqual(CACHE_TTL['timetables'], 600)
        self.assertLessEqual(CACHE_TTL['timetables'], 900)
        self.assertGreaterEqual(CACHE_TTL['school_settings'], 1800)

    def test_tenant_invalidation_preserves_other_tenant_generation(self):
        invalidate_cache_namespaces('students', school_id=101)

        self.assertEqual(cache.get(_generation_key('students', 101)), 1)
        self.assertEqual(cache.get(_generation_key('students')), 1)
        self.assertIsNone(cache.get(_generation_key('students', 202)))

    def test_user_invalidation_does_not_bump_tenant_or_global_generation(self):
        invalidate_cache_namespaces('notifications', user_id=55)

        self.assertEqual(cache.get(_generation_key('notifications', user_id=55)), 1)
        self.assertIsNone(cache.get(_generation_key('notifications')))
        self.assertIsNone(cache.get(_generation_key('notifications', 101)))

    def test_cached_api_responses_are_isolated_by_tenant(self):
        calls = []
        factory = APIRequestFactory()

        @cached_api_response('students', CACHE_TTL['students'])
        def student_list(request):
            calls.append(request.user.school_id)
            return Response({'school_id': request.user.school_id})

        def request_for_school(school_id):
            request = Request(factory.get('/api/students/?page=1'))
            request.user = SimpleNamespace(
                pk=7,
                role='school_admin',
                school_id=school_id,
                is_authenticated=True,
            )
            return request

        with patch('core.cache.cache.lock', create=True) as lock:
            lock.return_value.acquire.return_value = True
            first = student_list(request_for_school(101))
            self.assertEqual(first.data['school_id'], 101)
            self.assertEqual(
                student_list(request_for_school(101)).data['school_id'], 101
            )
            second = student_list(request_for_school(202))
            invalidate_cache_namespaces('students', school_id=101)
            refreshed_first = student_list(request_for_school(101))
            cached_second = student_list(request_for_school(202))

        self.assertEqual(second.data['school_id'], 202)
        self.assertEqual(refreshed_first.data['school_id'], 101)
        self.assertEqual(cached_second.data['school_id'], 202)
        self.assertEqual(calls, [101, 202, 101])
