from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.billing.views import (
    InvoiceViewSet, 
    PaymentViewSet, 
    FeeViewSet, 
    StudentFeeAssignmentViewSet, 
    ClassFeeAssignmentViewSet, 
    SchoolFeeAssignmentViewSet
)

router = DefaultRouter()
router.register(r'fees', FeeViewSet, basename='fee')
router.register(r'school-fee-assignments', SchoolFeeAssignmentViewSet, basename='school-fee-assignment')
router.register(r'class-fee-assignments', ClassFeeAssignmentViewSet, basename='class-fee-assignment')
router.register(r'student-fee-assignments', StudentFeeAssignmentViewSet, basename='student-fee-assignment')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
]
