"""
Django signals for the Learning Feed.
"""
from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver

from apps.feed import models
from apps.feed.services.feed_service import FeedService
from apps.feed.services.notification_service import NotificationService


@receiver(post_save, sender=models.FeedLesson)
def lesson_saved(sender, instance, created, **kwargs):
    # New approved public lessons notify followers
    if created and instance.status == 'approved' and instance.visibility == 'public':
        NotificationService.notify_new_lesson(instance)
    # Invalidate caches when important fields change
    FeedService.invalidate_feed_caches(instance)


@receiver(post_delete, sender=models.FeedLesson)
def lesson_deleted(sender, instance, **kwargs):
    FeedService.invalidate_feed_caches(instance)


@receiver(m2m_changed, sender=models.FeedLesson.tags.through)
def lesson_tags_changed(sender, instance, action, **kwargs):
    if action in ('post_add', 'post_remove', 'post_clear'):
        # Save to trigger search_vector refresh via DB trigger
        instance.save(update_fields=['updated_at'])


@receiver(post_save, sender=models.FeedComment)
def comment_saved(sender, instance, created, **kwargs):
    if created:
        if instance.parent and instance.parent.user_id != instance.user_id:
            NotificationService.notify_comment_reply(instance)
        # Teacher replies to comments on their own lessons
        if instance.lesson.teacher_id == instance.user_id and instance.parent:
            NotificationService.notify_teacher_reply(instance)
