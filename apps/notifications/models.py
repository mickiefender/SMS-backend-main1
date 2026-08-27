"""
Notification models — centralized notification system covering all event types.

- Notification: stored in-app notification with dedup and deep-link metadata
- Device: FCM token registry per user (supports multiple devices)
- NotificationPreference: per-user toggle for categories
- NotificationType: lookup table of available notification types
"""
import uuid
import hashlib
from django.db import models
from django.conf import settings
from django.utils import timezone


User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Notification Type lookup
# ---------------------------------------------------------------------------

class NotificationType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_enabled_by_default = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications_type'
        ordering = ['sort_order', 'name']
        verbose_name = 'Notification Type'
        verbose_name_plural = 'Notification Types'

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Device  (FCM token registry)
# ---------------------------------------------------------------------------

class Device(models.Model):
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='devices'
    )
    fcm_token = models.CharField(max_length=500, unique=True, db_index=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='android')
    device_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications_device'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['fcm_token']),
        ]
        verbose_name = 'Device'
        verbose_name_plural = 'Devices'

    def __str__(self):
        return f'{self.platform} device for user {self.user_id}'


# ---------------------------------------------------------------------------
# Notification Preference
# ---------------------------------------------------------------------------

class NotificationPreference(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='notification_preferences'
    )
    # Nested JSON: {'categories': {'feed': True, 'assignment': False, ...}}
    preferences = models.JSONField(default=dict, blank=True)
    push_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    # ── Daily Learning Reminder ──────────────────────────────────
    # Master toggle for the personalised daily learning reminder.
    daily_reminder_enabled = models.BooleanField(default=True)
    # Preferred local time for the daily reminder (null → default 16:00 UTC).
    daily_reminder_time = models.TimeField(null=True, blank=True)
    # Tracks when the last daily reminder was sent so we never spam (once/day).
    last_daily_reminder_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications_preference'
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'

    def __str__(self):
        return f'Preferences for user {self.user_id}'

    def is_category_enabled(self, category: str) -> bool:
        """Check if a notification category is enabled for this user."""
        cat_prefs = self.preferences.get('categories', {})
        return cat_prefs.get(category, True) is not False

    def is_daily_reminder_enabled(self) -> bool:
        """True when the user wants daily reminders (master toggle + category)."""
        return (
            self.daily_reminder_enabled
            and self.is_category_enabled('daily_reminder')
        )

    def has_received_daily_reminder_today(self) -> bool:
        """True if a daily reminder was already sent to this user today."""
        if not self.last_daily_reminder_at:
            return False
        from django.utils import timezone
        now = timezone.now()
        return (
            self.last_daily_reminder_at.year == now.year
            and self.last_daily_reminder_at.month == now.month
            and self.last_daily_reminder_at.day == now.day
        )


# ---------------------------------------------------------------------------
# Notification  (stored in-app notification record)
# ---------------------------------------------------------------------------

class Notification(models.Model):
    CATEGORY_CHOICES = [
        ('feed', 'Feed'),
        ('school_announcement', 'School Announcement'),
        ('assignment', 'Assignment'),
        ('assignment_reminder', 'Assignment Reminder'),
        ('grade', 'Grade'),
        ('attendance', 'Attendance'),
        ('fee_reminder', 'Fee Reminder'),
        ('message', 'Message'),
        ('live_class', 'Live Class'),
        ('upload_status', 'Upload Status'),
        ('comment', 'Comment'),
        ('like', 'Like'),
        ('daily_reminder', 'Daily Reminder'),
        ('app_update', 'App Update'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notifications'
    )
    notification_type = models.CharField(max_length=50, db_index=True)
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default='feed', db_index=True
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    image_url = models.URLField(max_length=1000, blank=True)
    # Deep-link metadata
    target_screen = models.CharField(max_length=255, blank=True,
        help_text='e.g. lesson_detail, assignment_view, fee_view')
    target_id = models.CharField(max_length=50, blank=True,
        help_text='ID of the related resource')
    priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default='normal'
    )
    is_read = models.BooleanField(default=False, db_index=True)
    is_pinned = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    # SHA-256 hash for deduplication (recipient + category + type + target_id)
    dedup_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications_notification'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['category']),
            models.Index(fields=['dedup_hash']),
        ]
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f'{self.title} -> {self.recipient_id}'

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    @staticmethod
    def make_dedup_hash(recipient_id, category, notification_type, target_id):
        raw = f'{recipient_id}:{category}:{notification_type}:{target_id or ""}'
        return hashlib.sha256(raw.encode()).hexdigest()
