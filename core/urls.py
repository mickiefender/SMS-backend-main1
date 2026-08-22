"""Core URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .notifications_api import StudentNotificationViewSet
from .staff_activity_api import StaffActivityWeeklyView

# Create router for notifications
router = DefaultRouter()
router.register(r'notifications', StudentNotificationViewSet, basename='notifications')

urlpatterns = [
    path('admin/', admin.site.urls),
    # JWT token refresh — lets the mobile client silently renew an expired
    # access token using the stored refresh token (SimpleJWT standard view).
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
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
    # Centralized notifications API — must come BEFORE the legacy
    # /api/notifications/ router below, otherwise requests like
    # POST /api/notifications/devices/ are captured by the old
    # StudentNotificationViewSet as {pk}="devices" and rejected with 405.
    path('api/notifications/', include('apps.notifications.urls')),
    # Legacy student notifications API
    path('api/', include(router.urls)),
    # Admin-staff dashboard: real recorded activity (weekly chart + recent actions)
    path('api/core/staff-activity/weekly/', StaffActivityWeeklyView.as_view(), name='staff_activity_weekly'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
