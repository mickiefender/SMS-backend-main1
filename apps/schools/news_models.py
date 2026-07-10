from django.db import models
from apps.schools.models import School


class News(models.Model):
    """School news items with optional banner support."""

    AUDIENCE_CHOICES = (
        ('all', 'All'),
        ('students', 'Students'),
        ('teachers', 'Teachers'),
        ('parents', 'Parents'),
        ('staff', 'Staff'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='news_items',
    )
    title = models.CharField(max_length=500)
    excerpt = models.TextField(default='', blank=True)
    content = models.TextField(default='', blank=True)
    category = models.CharField(max_length=100, default='Announcements')
    audience = models.CharField(
        max_length=50, choices=AUDIENCE_CHOICES, default='all'
    )
    banner_image_url = models.TextField(null=True, blank=True)

    is_published = models.BooleanField(default=True)
    is_banner = models.BooleanField(
        default=False,
        help_text='Show this news item in the rotating banner/carousel on dashboards',
    )

    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='news_created',
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'news'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'is_published', 'created_at']),
            models.Index(fields=['school', 'is_banner', 'created_at']),
            models.Index(fields=['audience']),
            models.Index(fields=['category']),
        ]
        verbose_name = 'News'
        verbose_name_plural = 'News'

    def __str__(self):
        return f'{self.school.name} — {self.title}'

    def save(self, *args, **kwargs):
        """Auto-set published_at when publishing for the first time."""
        if self.pk:
            orig = News.objects.filter(pk=self.pk).first()
            if orig and not orig.is_published and self.is_published:
                from django.utils import timezone
                self.published_at = timezone.now()
        elif self.is_published:
            from django.utils import timezone
            self.published_at = self.published_at or timezone.now()
        super().save(*args, **kwargs)
