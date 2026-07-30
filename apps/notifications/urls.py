"""
URL patterns for the notifications app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.notifications import views

router = DefaultRouter()
router.register(r'notifications', views.NotificationViewSet, basename='notification')
router.register(r'devices', views.DeviceViewSet, basename='device')

urlpatterns = [
    path('preferences/', views.NotificationPreferenceView.as_view(), name='notification-preferences'),
    path('send/', views.SendNotificationView.as_view(), name='notification-send'),
    path('', include(router.urls)),
]
