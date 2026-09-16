from django.db import models
from django.utils import timezone


class Plan(models.Model):
    PLAN_CHOICES = (
        ('starter', 'Starter'),
        ('standard', 'Standard'),
        ('premium', 'Premium'),
    )
    
    name = models.CharField(max_length=50, choices=PLAN_CHOICES, unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    max_students = models.IntegerField()
    max_teachers = models.IntegerField()
    max_classes = models.IntegerField()
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['price']
    
    def __str__(self):
        return self.get_name_display()


class School(models.Model):
    """
    A tenant. ``status`` is the school_status and is the single source of
    truth for whether the school may use the platform:

        pending_compliance -> account exists but compliance is outstanding
        active             -> fully approved and usable
        rejected           -> the Super Admin rejected the application
        suspended          -> was active, now suspended
        inactive           -> legacy value (unused by the compliance flow)

    Compliance is layered on top via the ``compliance_profile`` relation
    (apps.compliance). This model never stores requirement rows itself —
    only the denormalised ``compliance_status`` summary used for fast
    listing/filtering in the Super Admin console.
    """

    STATUS_CHOICES = (
        ('pending_compliance', 'Pending Compliance'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('rejected', 'Rejected'),
        ('inactive', 'Inactive'),
    )

    #: School statuses that may use the normal Alara modules.
    APPROVED_STATUSES = ('active',)
    #: School statuses that must be routed to the compliance page first.
    COMPLIANCE_FIRST_STATUSES = ('pending_compliance',)
    #: School statuses denied access entirely (compliance/rejected screen).
    BLOCKED_STATUSES = ('rejected',)

    SCHOOL_TYPE_CHOICES = (
        ('kindergarten', 'Kindergarten / Early Years'),
        ('primary', 'Primary School'),
        ('secondary', 'Secondary School'),
        ('combined', 'Combined (Primary & Secondary)'),
        ('tertiary', 'Tertiary / College'),
        ('vocational', 'Vocational / Technical'),
        ('other', 'Other'),
    )

    COMPLIANCE_STATUS_CHOICES = (
        ('not_started', 'Not Started'),
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('requires_resubmission', 'Requires Resubmission'),
    )

    APPROVAL_METHOD_CHOICES = (
        ('fully_compliant', 'Fully Compliant'),
        ('approved_with_overrides', 'Approved With Compliance Overrides'),
    )
    
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    logo = models.ImageField(upload_to='schools/logos/', null=True, blank=True)
    logo_url = models.URLField(max_length=500, blank=True, null=True, help_text="Supabase URL for school logo")
    website = models.URLField(blank=True)
    primary_color = models.CharField(
        max_length=7, 
        default='#0a0a0a',
        help_text='Primary brand color (hex format #RRGGBB)'
    )
    secondary_color = models.CharField(
        max_length=7, 
        default='#008484', 
        help_text='Secondary brand color (hex format #RRGGBB)'
    )
    sidebar_color = models.CharField(
        max_length=7, 
        default='#209090', 
        help_text='Sidebar accent color (hex format #RRGGBB)'
    )
    
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending_compliance',
        help_text='School status — also the compliance gate for module access.')
    # Institution type drives which compliance requirements apply.
    school_type = models.CharField(
        max_length=30, choices=SCHOOL_TYPE_CHOICES, default='combined')

    # ── Compliance summary (detail lives in apps.compliance) ──────────────
    compliance_status = models.CharField(
        max_length=30, choices=COMPLIANCE_STATUS_CHOICES, default='not_started')
    approval_method = models.CharField(
        max_length=30, choices=APPROVAL_METHOD_CHOICES, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='schools_approved')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='schools_rejected')
    rejection_reason = models.TextField(blank=True, default='')
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspended_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='schools_suspended')
    suspension_reason = models.TextField(blank=True, default='')
    
    subscription_start = models.DateField(auto_now_add=True)
    subscription_end = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return self.name
    
    def get_logo_url(self):
        """Get the logo URL, preferring Supabase URL over local storage"""
        if self.logo_url:
            return self.logo_url
        if self.logo:
            return self.logo.url
        return None

    # ── Compliance / approval helpers ─────────────────────────────────────
    @property
    def is_approved(self):
        """True when the school is fully active and may use every module."""
        return self.status in self.APPROVED_STATUSES

    @property
    def requires_compliance(self):
        """True when the school admin must complete compliance first."""
        return self.status in self.COMPLIANCE_FIRST_STATUSES

    @property
    def is_rejected(self):
        return self.status == 'rejected'

    @property
    def is_suspended(self):
        return self.status == 'suspended'

    @property
    def has_overrides(self):
        """True when the school was approved with bypassed requirements."""
        return self.approval_method == 'approved_with_overrides'

    def compliance_badge(self):
        """Badge shown in the Super Admin console (brief §29)."""
        if self.status == 'pending_compliance':
            return 'Pending Compliance'
        if self.status == 'rejected':
            return 'Rejected'
        if self.status == 'suspended':
            return 'Suspended'
        if self.status != 'active':
            return self.get_status_display()
        if self.has_overrides:
            return 'Approved With Compliance Overrides'
        return 'Fully Verified'

    def approval_method_label(self):
        if self.approval_method == 'fully_compliant':
            return 'Fully Compliant'
        if self.approval_method == 'approved_with_overrides':
            return 'Approved With Bypassed Requirements'
        return None


class Subscription(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('cancelled', 'Cancelled'),
    )
    
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField()
    auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.school.name} - {self.plan.name}"

class Announcement(models.Model):
    PRIORITY_CHOICES = (
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
        ('critical', 'Critical'),
    )
    
    AUDIENCE_CHOICES = (
        ('all', 'All'),
        ('students', 'Students'),
        ('teachers', 'Teachers'),
        ('parents', 'Parents'),
        ('staff', 'Staff'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='+')
    title = models.CharField(max_length=255)
    content = models.TextField()
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='all')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', '-created_at']),
            models.Index(fields=['priority']),
        ]
    
    def __str__(self):
        return f"{self.school.name} - {self.title}"
