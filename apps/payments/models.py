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


class Notification(models.Model):
    """In-app notifications for the dashboard notification bell."""

    NOTIFICATION_TYPE_CHOICES = [
        ('payment_received', 'Payment Received'),
        ('payment_confirmed', 'Payment Confirmed'),
        ('withdrawal_requested', 'Withdrawal Requested'),
        ('withdrawal_completed', 'Withdrawal Completed'),
        ('withdrawal_failed', 'Withdrawal Failed'),
        ('invoice_created', 'Invoice Created'),
        ('general', 'General'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='payment_notifications'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES,
        default='general'
    )
    is_read = models.BooleanField(default=False)
    related_payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['school', '-created_at']),
        ]

    def __str__(self):
        return f"Notification: {self.title} - {self.user.get_full_name()}"


class SchoolRevenue(models.Model):
    """Tracks total revenue collected for each school."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.OneToOneField(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='revenue'
    )
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    available_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Revenue: {self.school.name} - ₦{self.available_balance}"

    def add_revenue(self, amount):
        """Add revenue from a confirmed payment."""
        from decimal import Decimal
        amount = Decimal(str(amount))
        self.total_revenue += amount
        self.available_balance += amount
        self.save(update_fields=['total_revenue', 'available_balance', 'updated_at'])

    def deduct_for_withdrawal(self, amount):
        """Deduct balance for a withdrawal."""
        from decimal import Decimal
        amount = Decimal(str(amount))
        if amount > self.available_balance:
            raise ValueError("Insufficient balance for withdrawal")
        self.total_withdrawn += amount
        self.available_balance -= amount
        self.save(update_fields=['total_withdrawn', 'available_balance', 'updated_at'])


class SchoolBankAccount(models.Model):
    """Bank or MOMO account details for school withdrawals."""

    ACCOUNT_TYPE_CHOICES = [
        ('bank', 'Bank Account'),
        ('momo', 'Mobile Money'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='bank_accounts'
    )
    account_type = models.CharField(max_length=10, choices=ACCOUNT_TYPE_CHOICES)
    bank_name = models.CharField(max_length=255)
    bank_code = models.CharField(max_length=20)
    account_number = models.CharField(max_length=30)
    account_name = models.CharField(max_length=255)
    # Paystack transfer recipient code (created via Paystack API)
    recipient_code = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.school.name} - {self.bank_name} ({self.account_number})"


class WithdrawalRequest(models.Model):
    """Withdrawal requests from schools with OTP verification."""

    STATUS_CHOICES = [
        ('pending_otp', 'Pending OTP Verification'),
        ('otp_verified', 'OTP Verified'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    WITHDRAWAL_METHOD_CHOICES = [
        ('bank', 'Bank Transfer'),
        ('momo', 'Mobile Money'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='withdrawal_requests'
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='withdrawal_requests'
    )
    bank_account = models.ForeignKey(
        SchoolBankAccount,
        on_delete=models.SET_NULL,
        null=True,
        related_name='withdrawals'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    withdrawal_method = models.CharField(max_length=10, choices=WITHDRAWAL_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_otp')

    # OTP fields
    otp_code = models.CharField(max_length=6, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    otp_verified_at = models.DateTimeField(null=True, blank=True)

    # Paystack transfer fields
    paystack_transfer_code = models.CharField(max_length=255, blank=True)
    paystack_transfer_reference = models.CharField(max_length=255, blank=True)

    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Withdrawal: {self.school.name} - ₦{self.amount} ({self.status})"

    def generate_otp(self):
        """Generate a 6-digit OTP code."""
        import random
        self.otp_code = str(random.randint(100000, 999999))
        self.otp_created_at = timezone.now()
        self.save(update_fields=['otp_code', 'otp_created_at', 'updated_at'])
        return self.otp_code

    def verify_otp(self, code):
        """Verify the OTP code. Valid for 10 minutes."""
        from datetime import timedelta
        if not self.otp_code or not self.otp_created_at:
            return False
        if timezone.now() > self.otp_created_at + timedelta(minutes=10):
            return False
        if self.otp_code != code:
            return False
        self.otp_verified_at = timezone.now()
        self.status = 'otp_verified'
        self.save(update_fields=['otp_verified_at', 'status', 'updated_at'])
        return True
