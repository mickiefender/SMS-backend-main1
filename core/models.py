"""
Core Models - Student Notifications
"""
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
