from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class PlatformRole(models.Model):
    """Configurable internal platform role with JSON permission codes."""
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    permissions = models.JSONField(default=list)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Tables created manually via backend/sql/superadmin_platform.sql.
        db_table = 'platform_role'

    def __str__(self):
        return self.display_name


class PlatformUserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='platform_roles')
    role = models.ForeignKey(PlatformRole, on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='platform_roles_assigned')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'platform_user_role'
        unique_together = ['user', 'role']

    def __str__(self):
        return f"{self.user} → {self.role}"


class AuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    actor_name = models.CharField(max_length=150, blank=True, default='')
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True, default='')
    target_id = models.CharField(max_length=100, blank=True, default='')
    target_label = models.CharField(max_length=255, blank=True, default='')
    changes = models.JSONField(default=dict)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.actor_name} · {self.action} · {self.target_label}"


def write_audit_log(request, actor, action, target_type='', target_id='', target_label='', changes=None):
    """Convenience helper used by every sensitive super-admin action."""
    return AuditLog.objects.create(
        actor=actor,
        actor_name=(actor.get_full_name() or actor.username) if actor else '',
        action=action,
        target_type=str(target_type),
        target_id=str(target_id),
        target_label=str(target_label),
        changes=changes or {},
        ip_address=request.META.get('REMOTE_ADDR', '') if request else '',
        user_agent=request.META.get('HTTP_USER_AGENT', '') if request else '',
    )


class ImpersonationSession(models.Model):
    super_admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='impersonations_started')
    target_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='impersonated_as')
    reason = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'impersonation_session'


class SupportTicket(models.Model):
    KIND_CHOICES = (
        ('bug', 'Bug Report'), ('feature_request', 'Feature Request'),
        ('question', 'Question'), ('feedback', 'Feedback'),
    )
    STATUS_CHOICES = (
        ('open', 'Open'), ('in_progress', 'In Progress'), ('waiting', 'Waiting'),
        ('resolved', 'Resolved'), ('closed', 'Closed'),
    )
    PRIORITY_CHOICES = (
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent'),
    )

    reference = models.CharField(max_length=20, unique=True, blank=True)
    requester = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tickets_requested')
    requester_name = models.CharField(max_length=150, blank=True, default='')
    school = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    kind = models.CharField(max_length=30, choices=KIND_CHOICES, default='bug')
    subject = models.CharField(max_length=255)
    body = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_assigned')
    internal_notes = models.TextField(blank=True, default='')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'support_ticket'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.reference:
            from django.utils import timezone
            year = timezone.now().year
            last = SupportTicket.objects.filter(reference__startswith=f'TCK-{year}').order_by('-id').first()
            seq = (int(last.reference[-6:]) + 1) if last else 1
            self.reference = f'TCK-{year}-{seq:06d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} · {self.subject}"


class SupportTicketComment(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='ticket_comments')
    author_name = models.CharField(max_length=150, blank=True, default='')
    body = models.TextField()
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'support_ticket_comment'
        ordering = ['created_at']


class FeatureFlag(models.Model):
    SCOPE_CHOICES = (('global', 'Global'), ('school', 'School'), ('plan', 'Plan'))

    key = models.CharField(max_length=100)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default='')
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default='global')
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, null=True, blank=True, related_name='feature_flags')
    plan_name = models.CharField(max_length=50, null=True, blank=True)
    enabled = models.BooleanField(default=True)
    rollout_percent = models.IntegerField(default=100)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='flags_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feature_flag'
        unique_together = ['key', 'scope', 'school', 'plan_name']
        ordering = ['key', 'scope']


class SystemSetting(models.Model):
    CATEGORY_CHOICES = (
        ('general', 'General'), ('branding', 'Branding'), ('email', 'Email'),
        ('sms', 'SMS'), ('push', 'Push'), ('payments', 'Payments'),
        ('storage', 'Storage'), ('ai', 'AI'), ('security', 'Security'),
    )

    key = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='general')
    value = models.JSONField(default=dict)
    is_secret = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True, default='')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='settings_updated')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_setting'

    def __str__(self):
        return self.key


class NotificationCampaign(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'), ('scheduled', 'Scheduled'), ('sending', 'Sending'),
        ('sent', 'Sent'), ('failed', 'Failed'),
    )
    AUDIENCE_CHOICES = (
        ('all', 'All Users'), ('school', 'Specific Schools'), ('role', 'Specific Roles'),
        ('users', 'Specific Users'), ('plan', 'Subscription Plan'),
    )

    name = models.CharField(max_length=200)
    channels = models.JSONField(default=list)  # ["push","email","sms"]
    audience_type = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='all')
    audience_filter = models.JSONField(default=dict)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default='')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.IntegerField(default=0)
    delivered_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='campaigns_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_campaign'
        ordering = ['-created_at']


class ApiKey(models.Model):
    name = models.CharField(max_length=150)
    prefix = models.CharField(max_length=12)
    hashed_key = models.CharField(max_length=255)
    scopes = models.JSONField(default=list)
    rate_limit_per_min = models.IntegerField(default=60)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='api_keys_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_key'


class Webhook(models.Model):
    name = models.CharField(max_length=150)
    url = models.URLField()
    events = models.JSONField(default=list)
    secret = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    last_status = models.IntegerField(null=True, blank=True)
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'webhook'


class ApiUsageLog(models.Model):
    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, null=True, blank=True, related_name='usage')
    method = models.CharField(max_length=10, blank=True, default='')
    path = models.TextField(blank=True, default='')
    status_code = models.IntegerField(default=0)
    duration_ms = models.IntegerField(default=0)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_usage_log'
        ordering = ['-created_at']


class SecurityEvent(models.Model):
    SEVERITY_CHOICES = (('info', 'Info'), ('warning', 'Warning'), ('critical', 'Critical'))

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='security_events')
    event_type = models.CharField(max_length=50)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')
    details = models.JSONField(default=dict)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'security_event'
        ordering = ['-created_at']


class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='platform_sessions')
    session_key = models.CharField(max_length=128, unique=True)
    device = models.CharField(max_length=255, blank=True, default='')
    browser = models.CharField(max_length=100, blank=True, default='')
    os = models.CharField(max_length=100, blank=True, default='')
    ip_address = models.CharField(max_length=64, blank=True, default='')
    location = models.CharField(max_length=150, blank=True, default='')
    is_active = models.BooleanField(default=True)
    last_activity = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_session'


class AccountLockout(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lockouts')
    locked_at = models.DateTimeField(auto_now_add=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True, default='')
    failed_attempts = models.IntegerField(default=0)
    released_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lockouts_released')
    released_at = models.DateTimeField(null=True, blank=True)
    is_locked = models.BooleanField(default=True)

    class Meta:
        db_table = 'account_lockout'


class StorageQuota(models.Model):
    school = models.OneToOneField('schools.School', on_delete=models.CASCADE, related_name='storage_quota')
    quota_mb = models.BigIntegerField(default=5120)
    used_mb = models.BigIntegerField(default=0)
    videos_mb = models.BigIntegerField(default=0)
    images_mb = models.BigIntegerField(default=0)
    documents_mb = models.BigIntegerField(default=0)
    backups_mb = models.BigIntegerField(default=0)
    computed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Table was created manually via backend/sql/superadmin_platform.sql.
        db_table = 'storage_quota'


class ModerationReport(models.Model):
    REASON_CHOICES = (
        ('inappropriate', 'Inappropriate'), ('copyright', 'Copyright'),
        ('spam', 'Spam'), ('violence', 'Violence'), ('other', 'Other'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'), ('reviewing', 'Reviewing'),
        ('actioned', 'Actioned'), ('dismissed', 'Dismissed'),
    )

    reporter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reports_filed')
    content_type = models.CharField(max_length=50)  # video | image | document | post | comment
    content_id = models.BigIntegerField(default=0)
    content_url = models.TextField(blank=True, default='')
    content_preview = models.TextField(blank=True, default='')
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='content_reported')
    school = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True, related_name='moderation_reports')
    reason = models.CharField(max_length=50, choices=REASON_CHOICES, default='inappropriate')
    details = models.TextField(blank=True, default='')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    action_taken = models.CharField(max_length=50, blank=True, default='')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'moderation_report'
        ordering = ['-created_at']


class Coupon(models.Model):
    DISCOUNT_CHOICES = (('percent', 'Percent'), ('fixed', 'Fixed Amount'))

    code = models.CharField(max_length=40, unique=True)
    description = models.CharField(max_length=255, blank=True, default='')
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_CHOICES, default='percent')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_redemptions = models.IntegerField(default=0)  # 0 = unlimited
    redemption_count = models.IntegerField(default=0)
    applies_to_plan = models.CharField(max_length=50, null=True, blank=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coupon'


class Invoice(models.Model):
    STATUS_CHOICES = (('open', 'Open'), ('paid', 'Paid'), ('void', 'Void'), ('refunded', 'Refunded'))

    number = models.CharField(max_length=30, unique=True, blank=True)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, related_name='platform_invoices')
    subscription_id = models.BigIntegerField(null=True, blank=True)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default='GHS')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    line_items = models.JSONField(default=list)
    pdf_url = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoice'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.number:
            from django.utils import timezone
            year = timezone.now().year
            last = Invoice.objects.filter(number__startswith=f'INV-{year}').order_by('-id').first()
            seq = (int(last.number[-6:]) + 1) if last else 1
            self.number = f'INV-{year}-{seq:06d}'
        super().save(*args, **kwargs)


class Refund(models.Model):
    STATUS_CHOICES = (('pending', 'Pending'), ('processed', 'Processed'), ('rejected', 'Rejected'))

    transaction_ref = models.CharField(max_length=100, blank=True, default='')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='refunds')
    school = models.ForeignKey('schools.School', on_delete=models.SET_NULL, null=True, blank=True, related_name='refunds')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default='GHS')
    reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='refunds_processed')
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'refund'
        ordering = ['-created_at']


class MonitoringSnapshot(models.Model):
    STATUS_CHOICES = (('healthy', 'Healthy'), ('degraded', 'Degraded'), ('down', 'Down'))

    component = models.CharField(max_length=50)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='healthy')
    latency_ms = models.IntegerField(default=0)
    error_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    details = models.JSONField(default=dict)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'monitoring_snapshot'
        ordering = ['-recorded_at']
