from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.attendance.views import AttendanceViewSet

router = DefaultRouter()
router.register(r'', AttendanceViewSet, basename='attendance')

urlpatterns = [
    path('', include(router.urls)),
]
