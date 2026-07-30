"""Core URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from .notifications_api import StudentNotificationViewSet

# Create router for notifications
router = DefaultRouter()
router.register(r'notifications', StudentNotificationViewSet, basename='notifications')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('apps.users.urls')),
    path('api/schools/', include('apps.schools.urls')),
    path('api/academics/', include('apps.academics.urls')),
    path('api/attendance/', include('apps.attendance.urls')),
    path('api/assignments/', include('apps.assignments.urls')),
    path('api/billing/', include('apps.billing.urls')),
    path('api/payments/', include('apps.payments.urls')),
    path('api/students/', include('apps.students.urls')),
    path('api/messaging/', include('apps.messaging.urls')),
    path('api/feed/', include('apps.feed.urls')),
    # Student notifications API
    path('api/', include(router.urls)),
    # Centralized notifications API
    path('api/notifications/', include('apps.notifications.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
