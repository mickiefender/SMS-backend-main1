from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.platform.views import (
    ApiKeyViewSet, AuditLogViewSet, CampaignViewSet, CouponViewSet,
    FeatureFlagViewSet, ImpersonationView, InvoiceViewSet,
    ModerationReportViewSet, MonitoringSnapshotViewSet, PlatformOverviewView,
    PlatformRoleViewSet, RefundViewSet, SecurityEventViewSet,
    StorageQuotaViewSet, SupportTicketViewSet, SystemHealthView,
    SystemSettingViewSet, UserSessionViewSet, WebhookViewSet,
)

router = DefaultRouter()
router.register(r'roles', PlatformRoleViewSet, basename='platform-role')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
router.register(r'tickets', SupportTicketViewSet, basename='support-ticket')
router.register(r'feature-flags', FeatureFlagViewSet, basename='feature-flag')
router.register(r'settings', SystemSettingViewSet, basename='system-setting')
router.register(r'campaigns', CampaignViewSet, basename='campaign')
router.register(r'api-keys', ApiKeyViewSet, basename='api-key')
router.register(r'webhooks', WebhookViewSet, basename='webhook')
router.register(r'security-events', SecurityEventViewSet, basename='security-event')
router.register(r'sessions', UserSessionViewSet, basename='user-session')
router.register(r'moderation-reports', ModerationReportViewSet, basename='moderation-report')
router.register(r'coupons', CouponViewSet, basename='coupon')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'refunds', RefundViewSet, basename='refund')
router.register(r'storage-quotas', StorageQuotaViewSet, basename='storage-quota')
router.register(r'monitoring', MonitoringSnapshotViewSet, basename='monitoring-snapshot')

urlpatterns = [
    path('', include(router.urls)),
    path('overview/', PlatformOverviewView.as_view(), name='platform-overview'),
    path('health/', SystemHealthView.as_view(), name='platform-health'),
    path('impersonate/', ImpersonationView.as_view(), name='platform-impersonate'),
]
