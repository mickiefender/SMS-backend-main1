from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'fee-structures', views.FeeStructureViewSet, basename='fee-structure')
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')
router.register(r'payments', views.PaymentViewSet, basename='payment')
router.register(r'notifications', views.NotificationViewSet, basename='payment-notification')
router.register(r'bank-accounts', views.SchoolBankAccountViewSet, basename='bank-account')
router.register(r'withdrawals', views.WithdrawalViewSet, basename='withdrawal')

urlpatterns = [
    path('', include(router.urls)),
    path('webhook/paystack/', views.PaystackWebhookView.as_view(), name='paystack-webhook'),
    path('dashboard/', views.PaymentDashboardView.as_view(), name='payment-dashboard'),
    path('revenue/', views.SchoolRevenueView.as_view(), name='school-revenue'),
]
