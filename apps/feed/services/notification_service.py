"""
Notification service for the Learning Feed.
"""
from typing import Optional
from apps.feed import models


class NotificationService:
    @staticmethod
    def notify_new_lesson(lesson: models.FeedLesson):
        followers = models.TeacherFollower.objects.filter(teacher=lesson.teacher).select_related('user')
        notifications = [
            models.FeedNotification(
                user=follower.user,
                notification_type='new_lesson',
                title='New lesson from a teacher you follow',
                message=f'{lesson.teacher.get_full_name()} uploaded "{lesson.title}"',
                lesson=lesson,
                actor=lesson.teacher,
            )
            for follower in followers
        ]
        if notifications:
            models.FeedNotification.objects.bulk_create(notifications)

    @staticmethod
    def notify_comment_reply(comment: models.FeedComment):
        if not comment.parent:
            return
        parent_author = comment.parent.user
        if parent_author.id == comment.user_id:
            return
        models.FeedNotification.objects.create(
            user=parent_author,
            notification_type='comment_reply',
            title='Someone replied to your comment',
            message=f'{comment.user.get_full_name()} replied to your comment on "{comment.lesson.title}"',
            lesson=comment.lesson,
            comment=comment,
            actor=comment.user,
        )

    @staticmethod
    def notify_teacher_reply(comment: models.FeedComment):
        """Notify the lesson author when a teacher replies to a comment."""
        lesson_author = comment.lesson.teacher
        if lesson_author.id == comment.user_id:
            return
        models.FeedNotification.objects.create(
            user=lesson_author,
            notification_type='teacher_reply',
            title='Teacher replied to a comment',
            message=f'{comment.user.get_full_name()} replied on "{comment.lesson.title}"',
            lesson=comment.lesson,
            comment=comment,
            actor=comment.user,
        )

    @staticmethod
    def notify_new_follower(follower_relation: models.TeacherFollower):
        models.FeedNotification.objects.create(
            user=follower_relation.teacher,
            notification_type='follower',
            title='New follower',
            message=f'{follower_relation.user.get_full_name()} started following you',
            actor=follower_relation.user,
        )

    @staticmethod
    def notify_report_update(report: models.FeedReport):
        if not report.reporter:
            return
        models.FeedNotification.objects.create(
            user=report.reporter,
            notification_type='report_update',
            title='Report update',
            message=f'Your report status is now {report.status}',
            related_object_type='FeedReport',
            related_object_id=str(report.id),
        )

    @staticmethod
    def notify_lesson_approval(lesson: models.FeedLesson):
        models.FeedNotification.objects.create(
            user=lesson.teacher,
            notification_type='lesson_approved',
            title='Lesson approved',
            message=f'Your lesson "{lesson.title}" has been approved and is now public.',
            lesson=lesson,
        )

    @staticmethod
    def notify_lesson_suspension(lesson: models.FeedLesson, reason: Optional[str] = None):
        models.FeedNotification.objects.create(
            user=lesson.teacher,
            notification_type='lesson_suspended',
            title='Lesson suspended',
            message=f'Your lesson "{lesson.title}" has been suspended. {reason or ""}',
            lesson=lesson,
            priority='high',
        )
