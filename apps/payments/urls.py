from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'fee-structures', views.FeeStructureViewSet, basename='fee-structure')
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')
router.register(r'payments', views.PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
    path('webhook/paystack/', views.PaystackWebhookView.as_view(), name='paystack-webhook'),
    path('dashboard/', views.PaymentDashboardView.as_view(), name='payment-dashboard'),
]
