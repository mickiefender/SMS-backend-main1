from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.billing.views import InvoiceViewSet, PaymentViewSet, FeeTypeViewSet, StudentFeeViewSet, ClassFeeViewSet

router = DefaultRouter()
router.register(r'fee-types', FeeTypeViewSet, basename='fee-type')
router.register(r'student-fees', StudentFeeViewSet, basename='student-fee')
router.register(r'class-fees', ClassFeeViewSet, basename='class-fee')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
]
