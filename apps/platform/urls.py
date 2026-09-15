from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.platform.views import (
    ApiKeyViewSet, AuditLogViewSet, CampaignViewSet, CouponViewSet,
    FeatureFlagViewSet, ImpersonationView, InvoiceViewSet,
    ModerationReportViewSet, MonitoringSnapshotViewSet, PlatformOverviewView,
    PlatformRoleViewSet, RefundViewSet, SecurityEventViewSet,
    StorageQuotaViewSet, SupportTicketViewSet, SystemHealthView,
    PublicTrustedSchoolsView,
    PublicFaqsView, FaqView,
    PublicBlogPostsView, BlogPostView,
    PlatformStaffView,
    ContactInquiryView,
    TrustedSchoolLogoUploadView,
    TrustedSchoolLogoDeleteView,
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
    path('public/trusted-schools/', PublicTrustedSchoolsView.as_view(), name='public-trusted-schools'),
    path('public/faqs/', PublicFaqsView.as_view(), name='public-faqs'),
    path('public/blog/', PublicBlogPostsView.as_view(), name='public-blog-posts'),
    path('faqs/', FaqView.as_view(), name='faqs'),
    path('faqs/<int:faq_id>/', FaqView.as_view(), name='faq-detail'),
    path('blog/', BlogPostView.as_view(), name='blog-posts'),
    path('blog/<int:post_id>/', BlogPostView.as_view(), name='blog-post-detail'),
    path('staff/', PlatformStaffView.as_view(), name='platform-staff'),
    path('staff/<int:staff_id>/', PlatformStaffView.as_view(), name='platform-staff-detail'),
    path('contact-inquiries/', ContactInquiryView.as_view(), name='contact-inquiries'),
    path('contact-inquiries/<int:inquiry_id>/', ContactInquiryView.as_view(), name='contact-inquiry-detail'),
    path('trusted-schools/upload/', TrustedSchoolLogoUploadView.as_view(), name='trusted-school-logo-upload'),
    path('trusted-schools/<int:partner_id>/', TrustedSchoolLogoDeleteView.as_view(), name='trusted-school-logo-delete'),
    path('', include(router.urls)),
    path('overview/', PlatformOverviewView.as_view(), name='platform-overview'),
    path('health/', SystemHealthView.as_view(), name='platform-health'),
    path('impersonate/', ImpersonationView.as_view(), name='platform-impersonate'),
]
