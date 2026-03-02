import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class FeeStructure(models.Model):
    """Defines fee structures for different classes/terms."""

    TERM_CHOICES = [
        ('first', 'First Term'),
        ('second', 'Second Term'),
        ('third', 'Third Term'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='paystack_fee_structures'
    )
    class_level = models.ForeignKey(
        'academics.Class',
        on_delete=models.CASCADE,
        related_name='paystack_fee_structures',
        null=True,
        blank=True
    )
    academic_year = models.CharField(max_length=20)  # e.g., "2025/2026"
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    name = models.CharField(max_length=255)  # e.g., "Tuition Fee", "Lab Fee"
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_compulsory = models.BooleanField(default=True)
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-academic_year', 'term', 'name']
        unique_together = ['school', 'class_level', 'academic_year', 'term', 'name']

    def __str__(self):
        class_name = self.class_level.name if self.class_level else "All Classes"
        return f"{self.name} - {class_name} ({self.academic_year} {self.get_term_display()})"


class Invoice(models.Model):
    """Invoice generated for a student for specific fees."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('partially_paid', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='paystack_invoices'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='paystack_invoices',
        limit_choices_to={'role': 'student'}
    )
    academic_year = models.CharField(max_length=20)
    term = models.CharField(max_length=10, choices=FeeStructure.TERM_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.student.get_full_name()}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        self.balance = self.total_amount - self.amount_paid
        self.update_status()
        super().save(*args, **kwargs)

    def generate_invoice_number(self):
        """Generate a unique invoice number."""
        prefix = "INV"
        timestamp = timezone.now().strftime('%Y%m%d')
        random_part = uuid.uuid4().hex[:6].upper()
        return f"{prefix}-{timestamp}-{random_part}"

    def update_status(self):
        """Update invoice status based on payment."""
        if self.amount_paid >= self.total_amount and self.total_amount > 0:
            self.status = 'paid'
        elif self.amount_paid > 0:
            self.status = 'partially_paid'
        elif self.due_date and self.due_date < timezone.now().date() and self.status not in ['paid', 'cancelled']:
            self.status = 'overdue'


class InvoiceItem(models.Model):
    """Individual line items on an invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='items'
    )
    fee_structure = models.ForeignKey(
        FeeStructure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.description} - ₦{self.amount}"


class Payment(models.Model):
    """Records of payments made."""

    PAYMENT_METHOD_CHOICES = [
        ('paystack', 'Paystack'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
        ('cheque', 'Cheque'),
        ('pos', 'POS'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('abandoned', 'Abandoned'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='paystack_payments'
    )
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='paystack_payments'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='paystack_payments',
        limit_choices_to={'role': 'student'}
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='paystack')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Paystack-specific fields
    paystack_reference = models.CharField(max_length=255, unique=True, null=True, blank=True)
    paystack_access_code = models.CharField(max_length=255, null=True, blank=True)
    paystack_authorization_url = models.URLField(null=True, blank=True)
    paystack_transaction_id = models.CharField(max_length=255, null=True, blank=True)
    paystack_channel = models.CharField(max_length=50, null=True, blank=True)  # card, bank, ussd, etc.
    paystack_paid_at = models.DateTimeField(null=True, blank=True)
    paystack_fees = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # General fields
    transaction_reference = models.CharField(max_length=255, unique=True)
    receipt_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    paid_by = models.CharField(max_length=255, blank=True)  # Name of person who made payment
    paid_by_email = models.EmailField(blank=True)
    paid_by_phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.transaction_reference} - ₦{self.amount} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.transaction_reference:
            self.transaction_reference = self.generate_transaction_reference()
        super().save(*args, **kwargs)

    def generate_transaction_reference(self):
        """Generate a unique transaction reference."""
        prefix = "TXN"
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_part = uuid.uuid4().hex[:8].upper()
        return f"{prefix}-{timestamp}-{random_part}"


class PaystackWebhookLog(models.Model):
    """Log all Paystack webhook events for debugging and auditing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    reference = models.CharField(max_length=255, null=True, blank=True)
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Webhook: {self.event_type} - {self.reference} ({'Processed' if self.processed else 'Pending'})"


class PaymentReceipt(models.Model):
    """Generated receipts for successful payments."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.OneToOneField(
        Payment,
        on_delete=models.CASCADE,
        related_name='receipt'
    )
    receipt_number = models.CharField(max_length=50, unique=True)
    receipt_data = models.JSONField(default=dict)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Receipt {self.receipt_number}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self.generate_receipt_number()
        super().save(*args, **kwargs)

    def generate_receipt_number(self):
        prefix = "RCT"
        timestamp = timezone.now().strftime('%Y%m%d')
        random_part = uuid.uuid4().hex[:6].upper()
        return f"{prefix}-{timestamp}-{random_part}"
