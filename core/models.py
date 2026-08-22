"""
Core Models - Student Notifications
"""
import logging

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class NotificationTypeChoices(models.TextChoices):
    ATTENDANCE = 'attendance', 'Attendance'
    GRADE = 'grade', 'Grade/Grading'
    ASSIGNMENT = 'assignment', 'Assignment'
    ANNOUNCEMENT = 'announcement', 'Announcement'
    NOTICE = 'notice', 'Notice'
    FEE = 'fee', 'Fees'
    MATERIAL = 'material', 'Material'
    MESSAGE = 'message', 'Message'
    GENERAL = 'general', 'General'


class StudentNotification(models.Model):
    """
    Persistent student notification model.
    Stores all notifications for students across different activities.
    """
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text='The student who receives this notification'
    )
    
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationTypeChoices.choices,
        default=NotificationTypeChoices.GENERAL,
        help_text='Type of notification'
    )
    
    title = models.CharField(
        max_length=200,
        help_text='Notification title'
    )
    
    message = models.TextField(
        help_text='Notification message body'
    )
    
    # Related object references (optional)
    related_object_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='ID of related object (attendance_id, assignment_id, etc.)'
    )
    
    related_object_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='Type of related object (e.g., Attendance, Assignment, Fee)'
    )
    
    # Metadata
    is_read = models.BooleanField(
        default=False,
        help_text='Whether the notification has been read'
    )
    
    is_pinned = models.BooleanField(
        default=False,
        help_text='Whether the notification is pinned'
    )
    
    priority = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Low'),
            ('normal', 'Normal'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        default='normal'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='When the notification was created'
    )
    
    read_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text='When the notification was marked as read'
    )
    
    class Meta:
        app_label = 'core'
        db_table = 'core_student_notification'
        verbose_name = 'Student Notification'
        verbose_name_plural = 'Student Notifications'
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['student', '-created_at']),
            models.Index(fields=['student', 'is_read']),
            models.Index(fields=['notification_type']),
        ]
    
    def __str__(self):
        return f"{self.student.name} - {self.title}"
    
    def mark_as_read(self):
        """Mark this notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
        return self


def create_student_notification(
    student,
    notification_type,
    title,
    message,
    related_object_id=None,
    related_object_type=None,
    priority='normal'
):
    """
    Helper function to create a student notification.
    """
    return StudentNotification.objects.create(
        student=student,
        notification_type=notification_type,
        title=title,
        message=message,
        related_object_id=str(related_object_id) if related_object_id else None,
        related_object_type=related_object_type,
        priority=priority
    )


class StaffActivityLog(models.Model):
    """
    Audit trail of actions performed by admin-staff users.

    Populated automatically by StaffActivityMiddleware for successful
    write requests (POST/PUT/PATCH/DELETE) made by admin-staff accounts,
    and available to other apps via log_staff_activity() for explicit
    events (approvals, task completions, ...).
    """

    ACTION_CHOICES = [
        ('task', 'Task'),
        ('approval', 'Approval'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='staff_activity_logs',
        help_text='The staff member who performed the action'
    )
    action_type = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        default='task',
        help_text='Kind of activity recorded'
    )
    title = models.CharField(
        max_length=255,
        help_text='Human-readable description of the action'
    )
    path = models.CharField(
        max_length=500,
        blank=True,
        help_text='API path that triggered the activity'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text='When the action happened'
    )

    class Meta:
        app_label = 'core'
        db_table = 'core_staff_activity_log'
        verbose_name = 'Staff Activity Log'
        verbose_name_plural = 'Staff Activity Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user} - {self.title}"


def log_staff_activity(user, action_type='task', title='', path=''):
    """
    Record an explicit staff activity. Safe to call from anywhere;
    failures never break the caller's request.
    """
    try:
        return StaffActivityLog.objects.create(
            user=user,
            action_type=action_type if action_type in ('task', 'approval') else 'task',
            title=title[:255],
            path=path[:500],
        )
    except Exception:
        logger = logging.getLogger(__name__)
        logger.debug("Failed to record staff activity", exc_info=True)
        return None
