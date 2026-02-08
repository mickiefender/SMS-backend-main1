from django.db import models
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

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='announcements')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_announcements')
    title = models.CharField(max_length=255)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Recipients
    send_to_teachers = models.BooleanField(default=False)
    send_to_students = models.BooleanField(default=False)
    send_to_all = models.BooleanField(default=True)
    
    # Optional: specific classes or grades
    classes = models.ManyToManyField(Class, blank=True, related_name='announcements')
    
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
    
    is_pinned = models.BooleanField(default=False)
    expiry_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.school.name}"
