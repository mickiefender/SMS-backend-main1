from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MessageViewSet, AnnouncementViewSet, NoticeViewSet,
    SMSConfigurationView, SMSTemplateViewSet, SMSMessageViewSet,
    SMSBalanceView, SMSSendView, SMSDashboardView, SMSWebhookView,
    AdminSMSSenderRequestViewSet, AdminSMSBalanceView, AdminSMSSendView,
    AdminSMSDashboardView,
)

router = DefaultRouter()
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'announcements', AnnouncementViewSet, basename='announcement')
router.register(r'notices', NoticeViewSet, basename='notice')
router.register(r'sms/templates', SMSTemplateViewSet, basename='sms-template')
router.register(r'sms/messages', SMSMessageViewSet, basename='sms-message')
admin_router = DefaultRouter()
admin_router.register(r'sender-requests', AdminSMSSenderRequestViewSet, basename='sms-sender-request')

urlpatterns = [
    path('', include(router.urls)),
    path('sms/settings/', SMSConfigurationView.as_view(), name='sms-settings'),
    path('sms/balance/', SMSBalanceView.as_view(), name='sms-balance'),
    path('sms/send/', SMSSendView.as_view(), name='sms-send'),
    path('sms/dashboard/', SMSDashboardView.as_view(), name='sms-dashboard'),
    path('sms/webhooks/arkesel/', SMSWebhookView.as_view(), name='sms-arkesel-webhook'),
    path('admin/sms/', include(admin_router.urls)),
    path('admin/sms/balance/', AdminSMSBalanceView.as_view(), name='admin-sms-balance'),
    path('admin/sms/send/', AdminSMSSendView.as_view(), name='admin-sms-send'),
    path('admin/sms/dashboard/', AdminSMSDashboardView.as_view(), name='admin-sms-dashboard'),
]
