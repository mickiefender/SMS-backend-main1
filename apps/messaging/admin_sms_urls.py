from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminSMSSenderRequestViewSet, AdminSMSBalanceView, AdminSMSDashboardView

router = DefaultRouter()
router.register(r"sender-requests", AdminSMSSenderRequestViewSet, basename="admin-sms-sender-request")

urlpatterns = [
    path("", include(router.urls)),
    path("balance/", AdminSMSBalanceView.as_view(), name="admin-sms-balance"),
    path("dashboard/", AdminSMSDashboardView.as_view(), name="admin-sms-dashboard"),
]
