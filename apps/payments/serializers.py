from rest_framework import serializers
from .models import (
    FeeStructure, Invoice, InvoiceItem,
    Payment, PaymentReceipt, PaystackWebhookLog,
    Notification, SchoolRevenue, SchoolBankAccount, WithdrawalRequest
)


class FeeStructureSerializer(serializers.ModelSerializer):
    term_display = serializers.CharField(source='get_term_display', read_only=True)
    class_level_name = serializers.CharField(source='class_level.name', read_only=True)

    class Meta:
        model = FeeStructure
        fields = [
            'id', 'school', 'class_level', 'class_level_name',
            'academic_year', 'term', 'term_display', 'name',
            'description', 'amount', 'is_compulsory', 'due_date',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['id', 'fee_structure', 'description', 'amount']
        read_only_fields = ['id']


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    term_display = serializers.CharField(source='get_term_display', read_only=True)
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'school', 'student', 'student_name',
            'academic_year', 'term', 'term_display', 'status', 'status_display',
            'total_amount', 'amount_paid', 'balance', 'due_date',
            'notes', 'items', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'invoice_number', 'total_amount', 'amount_paid',
            'balance', 'created_at', 'updated_at'
        ]

    def get_student_name(self, obj):
        return obj.student.get_full_name()


class InvoiceCreateSerializer(serializers.Serializer):
    """Serializer for creating invoices with fee items."""
    student_id = serializers.UUIDField()
    academic_year = serializers.CharField(max_length=20)
    term = serializers.ChoiceField(choices=FeeStructure.TERM_CHOICES)
    fee_structure_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False
    )
    due_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class InitializePaymentSerializer(serializers.Serializer):
    """Serializer for initializing a Paystack payment."""
    invoice_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    email = serializers.EmailField()
    callback_url = serializers.URLField(required=False)
    metadata = serializers.DictField(required=False)


class PaymentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    student_name = serializers.SerializerMethodField()
    invoice_number = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'invoice', 'school', 'student', 'student_name',
            'invoice_number', 'amount',
            'payment_method', 'payment_method_display', 'status', 'status_display',
            'paystack_reference', 'paystack_authorization_url',
            'paystack_channel', 'paystack_paid_at', 'paystack_fees',
            'transaction_reference', 'receipt_number',
            'paid_by', 'paid_by_email', 'paid_by_phone',
            'notes', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'paystack_reference', 'paystack_authorization_url',
            'paystack_channel', 'paystack_paid_at', 'paystack_fees',
            'transaction_reference', 'receipt_number',
            'created_at', 'updated_at'
        ]

    def get_student_name(self, obj):
        return obj.student.get_full_name() if obj.student else ''

    def get_invoice_number(self, obj):
        return obj.invoice.invoice_number if obj.invoice else ''


class PaymentReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentReceipt
        fields = ['id', 'payment', 'receipt_number', 'receipt_data', 'generated_at']
        read_only_fields = ['id', 'receipt_number', 'generated_at']


class VerifyPaymentSerializer(serializers.Serializer):
    """Serializer for verifying a payment."""
    reference = serializers.CharField(max_length=255)


class RecordOfflinePaymentSerializer(serializers.Serializer):
    """Serializer for recording offline/manual payments."""
    invoice_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = serializers.ChoiceField(
        choices=[
            ('bank_transfer', 'Bank Transfer'),
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
            ('pos', 'POS'),
            ('other', 'Other'),
        ]
    )
    paid_by = serializers.CharField(max_length=255, required=False)
    paid_by_phone = serializers.CharField(max_length=20, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    transaction_date = serializers.DateTimeField(required=False)


# ==================== NEW SERIALIZERS ====================


class NotificationSerializer(serializers.ModelSerializer):
    notification_type_display = serializers.CharField(
        source='get_notification_type_display', read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            'id', 'school', 'user', 'title', 'message',
            'notification_type', 'notification_type_display',
            'is_read', 'related_payment', 'metadata', 'created_at'
        ]
        read_only_fields = [
            'id', 'school', 'user', 'title', 'message',
            'notification_type', 'related_payment', 'metadata', 'created_at'
        ]


class SchoolRevenueSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = SchoolRevenue
        fields = [
            'id', 'school', 'school_name', 'total_revenue',
            'total_withdrawn', 'available_balance', 'updated_at'
        ]
        read_only_fields = fields


class SchoolBankAccountSerializer(serializers.ModelSerializer):
    account_type_display = serializers.CharField(
        source='get_account_type_display', read_only=True
    )

    class Meta:
        model = SchoolBankAccount
        fields = [
            'id', 'school', 'account_type', 'account_type_display',
            'bank_name', 'bank_code', 'account_number', 'account_name',
            'recipient_code', 'is_default', 'is_verified',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'recipient_code', 'is_verified', 'created_at', 'updated_at'
        ]


class SchoolBankAccountCreateSerializer(serializers.Serializer):
    """Serializer for adding a bank/MOMO account."""
    account_type = serializers.ChoiceField(choices=SchoolBankAccount.ACCOUNT_TYPE_CHOICES)
    bank_code = serializers.CharField(max_length=20)
    account_number = serializers.CharField(max_length=30)
    is_default = serializers.BooleanField(required=False, default=False)


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    withdrawal_method_display = serializers.CharField(
        source='get_withdrawal_method_display', read_only=True
    )
    requested_by_name = serializers.SerializerMethodField()
    bank_account_details = SchoolBankAccountSerializer(source='bank_account', read_only=True)

    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'school', 'requested_by', 'requested_by_name',
            'bank_account', 'bank_account_details', 'amount',
            'withdrawal_method', 'withdrawal_method_display',
            'status', 'status_display',
            'paystack_transfer_code', 'paystack_transfer_reference',
            'notes', 'completed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'school', 'requested_by', 'status',
            'paystack_transfer_code', 'paystack_transfer_reference',
            'completed_at', 'created_at', 'updated_at'
        ]

    def get_requested_by_name(self, obj):
        return obj.requested_by.get_full_name() if obj.requested_by else ''


class InitiateWithdrawalSerializer(serializers.Serializer):
    """Serializer for initiating a withdrawal request."""
    bank_account_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    withdrawal_method = serializers.ChoiceField(
        choices=WithdrawalRequest.WITHDRAWAL_METHOD_CHOICES
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class VerifyWithdrawalOTPSerializer(serializers.Serializer):
    """Serializer for verifying withdrawal OTP."""
    withdrawal_id = serializers.UUIDField()
    otp_code = serializers.CharField(max_length=6, min_length=6)


class StudentPaymentHistorySerializer(serializers.ModelSerializer):
    """Simplified payment serializer for student payment history."""
    payment_method_display = serializers.CharField(
        source='get_payment_method_display', read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    invoice_total = serializers.DecimalField(
        source='invoice.total_amount', max_digits=12, decimal_places=2, read_only=True
    )
    invoice_balance = serializers.DecimalField(
        source='invoice.balance', max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            'id', 'invoice_number', 'invoice_total', 'invoice_balance',
            'amount', 'payment_method', 'payment_method_display',
            'status', 'status_display', 'transaction_reference',
            'paystack_channel', 'created_at'
        ]
        read_only_fields = fields
