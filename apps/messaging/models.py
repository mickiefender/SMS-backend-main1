from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from apps.schools.models import School
from apps.academics.models import Class

User = get_user_model()


class Message(models.Model):
    """Messages sent between users"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=255)
    content = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Message from {self.sender} to {self.recipient}"


class Announcement(models.Model):
    """School announcements sent to multiple recipients"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='announcements')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_announcements')
    title = models.CharField(max_length=255)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Recipients
    send_to_teachers = models.BooleanField(default=False)
    send_to_students = models.BooleanField(default=False)
    send_to_all = models.BooleanField(default=True)

    # Optional: individually targeted recipients (students AND/OR teachers).
    # When non-empty these users always receive the announcement, on top of
    # whatever the audience flags above select.
    recipients = models.ManyToManyField(
        User, blank=True, related_name='announcements_received'
    )

    # Optional: specific classes or grades
    classes = models.ManyToManyField(Class, blank=True, related_name='announcements')

    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')

    published_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_date', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.school.name}"


class AnnouncementRead(models.Model):
    """Track which users have read announcements"""
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name='read_by')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcement_reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['announcement', 'user']

    def __str__(self):
        return f"{self.user} read {self.announcement.title}"


class Notice(models.Model):
    """Important notices from school admin"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='notices')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_notices')
    title = models.CharField(max_length=255)
    content = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    # Recipients
    send_to_teachers = models.BooleanField(default=False)
    send_to_students = models.BooleanField(default=False)
    send_to_all = models.BooleanField(default=True)

    # Optional: individually targeted recipients (students AND/OR teachers).
    # When non-empty these users always receive the notice, on top of
    # whatever the audience flags above select.
    recipients = models.ManyToManyField(
        User, blank=True, related_name='notices_received'
    )

    is_pinned = models.BooleanField(default=False)
    expiry_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.school.name}"


class PersonalNotice(models.Model):
    """Personal notices/announcements sent to individual students."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='personal_notices')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personal_notices_received')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='personal_notices_created')
    title = models.CharField(max_length=255)
    content = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Personal Notice: {self.title} to {self.student.get_full_name()} - {self.school.name}"


class SMSConfiguration(models.Model):
    """The sender identity and switch for one school."""

    STATUS_CHOICES = (
        ("pending", "Pending approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("disabled", "Disabled"),
    )
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="sms_configuration")
    sender_id = models.CharField(max_length=11, blank=True)
    sender_id_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    rejection_reason = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.school.name} SMS ({self.sender_id or 'not configured'})"


class SMSBalance(models.Model):
    """A separately lockable credit balance for each tenant."""

    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="sms_balance")
    credits = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.school.name}: {self.credits} SMS credits"


class SMSTemplate(models.Model):
    CATEGORY_CHOICES = (
        ("attendance", "Attendance"),
        ("fees", "Fees"),
        ("results", "Exam results"),
        ("announcement", "Announcement"),
        ("meeting", "Meeting"),
        ("emergency", "Emergency"),
        ("custom", "Custom"),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="sms_templates")
    name = models.CharField(max_length=120)
    message = models.TextField()
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="custom")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_sms_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_sms_template_name"),
        ]


class SMSJob(models.Model):
    STATUS_CHOICES = (
        ("queued", "Queued"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("partially_failed", "Partially failed"),
        ("failed", "Failed"),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="sms_jobs")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="sms_jobs_requested",
    )
    idempotency_key = models.CharField(max_length=128, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    recipient_count = models.PositiveIntegerField(default=0)
    credits_reserved = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "idempotency_key"],
                name="unique_sms_job_idempotency",
            ),
        ]


class SMSMessage(models.Model):
    STATUS_CHOICES = (
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="sms_messages")
    job = models.ForeignKey(SMSJob, on_delete=models.CASCADE, null=True, blank=True, related_name="messages")
    sender_id = models.CharField(max_length=11)
    recipient = models.CharField(max_length=30)
    message = models.TextField()
    category = models.CharField(max_length=30, blank=True, default="custom")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    provider_message_id = models.CharField(max_length=255, blank=True)
    provider_response = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    message_parts = models.PositiveIntegerField(default=1)
    credits_used = models.PositiveIntegerField(default=1)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="sms_messages_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["school", "status"]),
            models.Index(fields=["provider_message_id"]),
        ]


class SMSCreditLedger(models.Model):
    """Auditable balance changes, including reservations and refunds."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="sms_credit_ledger")
    amount = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=40)
    job = models.ForeignKey(SMSJob, on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_entries")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
