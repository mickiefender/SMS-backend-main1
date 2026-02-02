from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.billing.views import InvoiceViewSet, PaymentViewSet, FeeViewSet, AssignFeeView

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'fees', FeeViewSet, basename='fee')

urlpatterns = [
    path('', include(router.urls)),
    path('assign-fee/', AssignFeeView.as_view(), name='assign-fee'),
]
