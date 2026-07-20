"""
Moderation service: reports, suspensions, approvals, and hidden lessons.
"""
from django.utils import timezone
from apps.feed import models
from apps.feed.services.notification_service import NotificationService


class ModerationService:
    @staticmethod
    def create_report(reporter, target_type, target_id, reason, description=''):
        report = models.FeedReport(
            reporter=reporter,
            target_type=target_type,
            reason=reason,
            description=description,
        )
        if target_type == 'lesson':
            report.lesson_id = target_id
        elif target_type == 'comment':
            report.comment_id = target_id
        elif target_type == 'teacher':
            report.teacher_id = target_id
        report.save()
        return report

    @staticmethod
    def approve_lesson(lesson: models.FeedLesson, moderator):
        lesson.status = 'approved'
        lesson.verification_status = 'verified'
        if lesson.visibility == 'public' and not lesson.published_at:
            lesson.published_at = timezone.now()
        lesson.save(update_fields=['status', 'verification_status', 'published_at', 'updated_at'])
        NotificationService.notify_lesson_approval(lesson)
        return lesson

    @staticmethod
    def suspend_lesson(lesson: models.FeedLesson, moderator, reason=''):
        lesson.status = 'suspended'
        lesson.visibility = 'suspended'
        lesson.save(update_fields=['status', 'visibility', 'updated_at'])
        NotificationService.notify_lesson_suspension(lesson, reason=reason)
        return lesson

    @staticmethod
    def hide_lesson(lesson: models.FeedLesson):
        lesson.visibility = 'hidden'
        lesson.save(update_fields=['visibility', 'updated_at'])
        return lesson

    @staticmethod
    def resolve_report(report: models.FeedReport, moderator, resolution=''):
        report.status = 'resolved'
        report.resolution = resolution
        report.resolved_by = moderator
        report.resolved_at = timezone.now()
        report.save(update_fields=['status', 'resolution', 'resolved_by', 'resolved_at', 'updated_at'])
        NotificationService.notify_report_update(report)
        return report

    @staticmethod
    def dismiss_report(report: models.FeedReport, moderator, resolution=''):
        report.status = 'dismissed'
        report.resolution = resolution
        report.resolved_by = moderator
        report.resolved_at = timezone.now()
        report.save(update_fields=['status', 'resolution', 'resolved_by', 'resolved_at', 'updated_at'])
        NotificationService.notify_report_update(report)
        return report

    @staticmethod
    def suspend_teacher(teacher_id: int, moderator, reason=''):
        from apps.users.models import User
        user = User.objects.get(pk=teacher_id)
        user.is_active_user = False
        user.save(update_fields=['is_active_user', 'updated_at'])
        # Suspend all public lessons by the teacher
        models.FeedLesson.objects.filter(teacher=user).update(
            status='suspended', visibility='suspended'
        )
        return user

    @staticmethod
    def soft_delete_comment(comment: models.FeedComment):
        comment.is_deleted = True
        comment.body = '[deleted]'
        comment.save(update_fields=['is_deleted', 'body', 'updated_at'])
        return comment
