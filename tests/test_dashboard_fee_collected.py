from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.schools.views import SchoolViewSet


class DashboardFeeCollectedTests(SimpleTestCase):
    @patch('apps.schools.views.DashboardCache.cache_stats')
    @patch('apps.schools.views.DashboardCache.get_stats', return_value=None)
    @patch('apps.billing.models.OnlinePayment.objects.filter')
    @patch('apps.billing.models.ManualPayment.objects.filter')
    @patch('apps.schools.views.User.objects.filter')
    def test_dashboard_sums_manual_and_successful_online_collections(
        self,
        user_filter,
        manual_payment_filter,
        online_payment_filter,
        _get_cached_stats,
        _cache_stats,
    ):
        user_filter.return_value.count.return_value = 0
        manual_payment_filter.return_value.aggregate.return_value = {
            'total': Decimal('125.50'),
        }
        online_payment_filter.return_value.aggregate.return_value = {
            'total': Decimal('74.50'),
        }

        request = APIRequestFactory().get('/api/schools/schools/dashboard_stats/')
        request.user = SimpleNamespace(
            school_id=17,
            school=None,
        )
        response = SchoolViewSet().dashboard_stats(request)

        self.assertEqual(response.data['data']['earnings'], 200.0)
        manual_payment_filter.assert_called_once_with(school_id=17)
        online_payment_filter.assert_called_once_with(
            school_id=17,
            status='success',
        )
