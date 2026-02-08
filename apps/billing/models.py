from django.db import models
from apps.schools.models import School, Plan
from apps.academics.models import Class


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

class FeeType(models.Model):
    """Define types of fees (School Fees, PTA, Transport, etc.)"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='fee_types')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['school', 'name']
        ordering = ['name']
        indexes = [
            models.Index(fields=['school', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.school.name} - {self.name}"


class StudentFee(models.Model):
    """Individual fees assigned to students"""
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='student_fees', limit_choices_to={'role': 'student'})
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name='student_fees')
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='student_individual_fees')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'fee_type']
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.student.get_full_name()} - {self.fee_type.name}"


class ClassFee(models.Model):
    """Fees assigned to entire classes"""
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='class_fees')
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name='class_fees')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['class_obj', 'fee_type']
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.class_obj} - {self.fee_type}"


class Fee(models.Model):
    """Predefined fees"""
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='predefined_fees')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['school', 'name']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.school.name} - {self.name}"
