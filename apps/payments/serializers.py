from rest_framework import serializers
from .models import (
    FeeStructure, Invoice, InvoiceItem,
    Payment, PaymentReceipt, PaystackWebhookLog
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

    class Meta:
        model = Payment
        fields = [
            'id', 'invoice', 'school', 'student', 'amount',
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
