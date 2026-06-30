from django.db import models
from apps.schools.models import School, Plan
from apps.academics.models import Class
from django.contrib.auth import get_user_model


# ==================== CORE BILLING MODELS ====================

class Invoice(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='invoices')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    invoice_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    issued_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-issued_date']
    
    def __str__(self):
        return f"{self.invoice_number} - {self.school.name}"


class Payment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=50)
    transaction_id = models.CharField(max_length=100, unique=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.amount}"


# ==================== FEE MANAGEMENT SYSTEM ====================

class Fee(models.Model):
    """Predefined fees"""
    FEE_TYPE_CHOICES = (
        ('academic', 'Academic'),
        ('administrative', 'Administrative'),
        ('other', 'Other'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='billing_fees')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    fee_type = models.CharField(max_length=20, choices=FEE_TYPE_CHOICES)
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['school', 'name']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.school.name} - {self.name}"


class SchoolFeeAssignment(models.Model):
    """Fees assigned to the entire school"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='school_fee_assignments')
    fee = models.ForeignKey(Fee, on_delete=models.CASCADE, related_name='school_assignments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['school', 'fee']
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.school} - {self.fee}"


class ClassFeeAssignment(models.Model):
    """Fees assigned to entire classes"""
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='class_fee_assignments')
    fee = models.ForeignKey(Fee, on_delete=models.CASCADE, related_name='class_assignments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['class_obj', 'fee']
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.class_obj} - {self.fee}"


class StudentFeeAssignment(models.Model):
    """Individual fees assigned to students"""
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='student_fee_assignments', limit_choices_to={'role': 'student'})
    fee = models.ForeignKey(Fee, on_delete=models.CASCADE, related_name='student_assignments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Track amount paid
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
    ], default='pending', editable=False)  # Auto-calculated
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'fee']
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.student.get_full_name()} - {self.fee.name}"
    
    def save(self, *args, **kwargs):
        # Ensure amount_paid is not None
        if self.amount_paid is None:
            self.amount_paid = 0
        
        # Auto-calculate status based on amount_paid
        if self.amount_paid >= self.amount:
            self.amount_paid = self.amount
            self.paid = True
            self.status = 'paid'
        elif self.amount_paid > 0:
            self.paid = False
            self.status = 'partial'
        else:
            self.paid = False
            self.status = 'pending'
        super().save(*args, **kwargs)
    
    @property
    def balance(self):
        """Calculate remaining balance"""
        paid = self.amount_paid if self.amount_paid is not None else 0
        return max(0, self.amount - paid)


# ==================== PAYMENT TRACKING FOR MANUAL PAYMENTS ====================

class ManualPayment(models.Model):
    """Track manual/fee payments made by students"""
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money'),
        ('check', 'Check'),
        ('card', 'Card'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='manual_payments')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='manual_payments', limit_choices_to={'role': 'student'})
    fee_assignment = models.ForeignKey(StudentFeeAssignment, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    receipt_number = models.CharField(max_length=100, unique=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, limit_choices_to={'role__in': ['school_admin', 'finance_officer', 'admin']})
    payment_date = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['student', 'payment_date']),
            models.Index(fields=['receipt_number']),
        ]
    
    def __str__(self):
        return f"Payment: {self.student.get_full_name()} - {self.amount} - {self.receipt_number}"
    
    def save(self, *args, **kwargs):
        if not self.receipt_number:
            # Generate receipt number: RCP-{SCHOOL_CODE}-{YYYYMMDD}-{RANDOM}
            import random
            from datetime import datetime
            school_code = self.school.name[:3].upper() if self.school else "SCH"
            date_str = datetime.now().strftime("%Y%m%d")
            random_num = random.randint(1000, 9999)
            self.receipt_number = f"RCP-{school_code}-{date_str}-{random_num}"
        super().save(*args, **kwargs)


class OnlinePayment(models.Model):
    """Track online payments made via Paystack"""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='online_payments')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='online_payments', limit_choices_to={'role': 'student'})
    fee_assignment = models.ForeignKey(StudentFeeAssignment, on_delete=models.CASCADE, related_name='online_payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='paystack')
    transaction_id = models.CharField(max_length=100, unique=True)
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    receipt_number = models.CharField(max_length=100, unique=True)
    notes = models.TextField(blank=True)
    channel = models.CharField(max_length=50, blank=True)  # card, bank, ussd, mobile_money
    currency = models.CharField(max_length=10, default='GHS')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'created_at']),
            models.Index(fields=['reference']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"OnlinePayment: {self.student.get_full_name()} - {self.amount} - {self.reference}"
    
    def save(self, *args, **kwargs):
        if not self.receipt_number:
            # Generate receipt number: OLP-{SCHOOL_CODE}-{YYYYMMDD}-{RANDOM}
            import random
            from datetime import datetime
            school_code = self.school.name[:3].upper() if self.school else "SCH"
            date_str = datetime.now().strftime("%Y%m%d")
            random_num = random.randint(1000, 9999)
            self.receipt_number = f"OLP-{school_code}-{date_str}-{random_num}"
        super().save(*args, **kwargs)


# ==================== EXPENSE TRACKING ====================

User = get_user_model()

class SchoolExpense(models.Model):
    """Track school expenses (outflows)"""
    EXPENSE_CATEGORY_CHOICES = (
        ('utilities', 'Utilities'),
        ('salaries', 'Salaries & Wages'),
        ('supplies', 'Supplies & Materials'),
        ('maintenance', 'Maintenance & Repairs'),
        ('transport', 'Transportation'),
        ('marketing', 'Marketing & Advertising'),
        ('events', 'Events & Activities'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='school_expenses')
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORY_CHOICES, default='other')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateField()
    description = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, limit_choices_to={'role__in': ['school_admin', 'finance_officer', 'admin']})
    expense_number = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-expense_date']
        indexes = [
            models.Index(fields=['school', 'expense_date']),
            models.Index(fields=['expense_number']),
        ]
    
    def __str__(self):
        return f"Expense: {self.category} - {self.amount} - {self.expense_number}"
    
    def save(self, *args, **kwargs):
        if not self.expense_number:
            # Generate expense number: EXP-{SCHOOL_CODE}-{YYYYMMDD}-{RANDOM}
            import random
            from datetime import datetime
            school_code = self.school.name[:3].upper() if self.school else "SCH"
            date_str = self.expense_date.strftime("%Y%m%d") if self.expense_date else datetime.now().strftime("%Y%m%d")
            random_num = random.randint(1000, 9999)
            self.expense_number = f"EXP-{school_code}-{date_str}-{random_num}"
        super().save(*args, **kwargs)
