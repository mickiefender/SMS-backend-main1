from django.contrib import admin
from .models import (
    FeeStructure, Invoice, InvoiceItem,
    Payment, PaymentReceipt, PaystackWebhookLog,
    Notification, SchoolRevenue, SchoolBankAccount, WithdrawalRequest
)


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ['name', 'school', 'class_level', 'academic_year', 'term', 'amount', 'is_active']
    list_filter = ['academic_year', 'term', 'is_active', 'is_compulsory']
    search_fields = ['name', 'description']


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ['fee_structure', 'description', 'amount']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'student', 'school', 'academic_year', 'term',
                    'total_amount', 'amount_paid', 'balance', 'status']
    list_filter = ['status', 'academic_year', 'term']
    search_fields = ['invoice_number', 'student__first_name', 'student__last_name']
    inlines = [InvoiceItemInline]
    readonly_fields = ['invoice_number', 'total_amount', 'amount_paid', 'balance']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['transaction_reference', 'student', 'amount', 'payment_method',
                    'status', 'paystack_reference', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['transaction_reference', 'paystack_reference',
                     'student__first_name', 'student__last_name']
    readonly_fields = [
        'transaction_reference', 'paystack_reference', 'paystack_access_code',
        'paystack_authorization_url', 'paystack_transaction_id',
        'paystack_channel', 'paystack_paid_at', 'paystack_fees'
    ]


@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'payment', 'generated_at']
    search_fields = ['receipt_number']
    readonly_fields = ['receipt_number', 'receipt_data', 'generated_at']


@admin.register(PaystackWebhookLog)
class PaystackWebhookLogAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'reference', 'processed', 'ip_address', 'created_at']
    list_filter = ['event_type', 'processed', 'created_at']
    search_fields = ['reference', 'event_type']
    readonly_fields = ['event_type', 'payload', 'reference', 'processed',
                       'processing_error', 'ip_address', 'created_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'school', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at']


@admin.register(SchoolRevenue)
class SchoolRevenueAdmin(admin.ModelAdmin):
    list_display = ['school', 'total_revenue', 'total_withdrawn', 'available_balance', 'updated_at']
    search_fields = ['school__name']
    readonly_fields = ['updated_at']


@admin.register(SchoolBankAccount)
class SchoolBankAccountAdmin(admin.ModelAdmin):
    list_display = ['school', 'account_type', 'bank_name', 'account_number',
                    'account_name', 'is_default', 'is_verified', 'created_at']
    list_filter = ['account_type', 'is_default', 'is_verified']
    search_fields = ['school__name', 'bank_name', 'account_number', 'account_name']
    readonly_fields = ['recipient_code', 'created_at', 'updated_at']


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ['school', 'requested_by', 'amount', 'withdrawal_method',
                    'status', 'created_at', 'completed_at']
    list_filter = ['status', 'withdrawal_method', 'created_at']
    search_fields = ['school__name', 'requested_by__first_name', 'requested_by__last_name']
    readonly_fields = [
        'otp_code', 'otp_created_at', 'otp_verified_at',
        'paystack_transfer_code', 'paystack_transfer_reference',
        'created_at', 'updated_at'
    ]
