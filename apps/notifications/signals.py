"""
Signal handlers that fire notifications when events occur in other apps.

This connects to post_save/post_delete signals from:
- apps.feed: FeedLesson, FeedComment, FeedLike, TeacherFollower
- apps.assignments: Assignment, AssignmentSubmission
- apps.attendance: Attendance models
- apps.billing: Fee models
"""
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Feed Signals ────────────────────────────────────────────────────────────

@receiver(post_save, sender='feed.FeedLesson')
def feed_lesson_saved(sender, instance, created, **kwargs):
    """When a new approved public lesson is created, notify followers."""
    if not created:
        return
    if instance.status != 'approved' or instance.visibility != 'public':
        return

    # Schedule async task to notify followers
    try:
        from apps.notifications.tasks import send_feed_notifications_for_new_lesson
        send_feed_notifications_for_new_lesson.delay(instance.id)
    except Exception as e:
        logger.error(f'Failed to schedule feed notification for lesson {instance.id}: {e}')


@receiver(post_save, sender='feed.FeedComment')
def feed_comment_saved(sender, instance, created, **kwargs):
    """When a comment is created, notify the lesson author or parent commenter."""
    if not created:
        return

    try:
        from apps.notifications.senders import notify_comment_on_lesson, notify_comment_reply

        # If it's a reply to another comment, notify the parent comment author
        if instance.parent and instance.parent.user_id != instance.user_id:
            notify_comment_reply(
                comment=instance,
                replier=instance.user,
                original_author=instance.parent.user,
            )
            return

        # Otherwise notify the lesson author
        if instance.lesson.teacher_id != instance.user_id:
            notify_comment_on_lesson(
                lesson=instance.lesson,
                commenter=instance.user,
                lesson_author=instance.lesson.teacher,
            )
    except Exception as e:
        logger.error(f'Failed to send comment notification: {e}')


@receiver(post_save, sender='feed.FeedLike')
def feed_like_saved(sender, instance, created, **kwargs):
    """When a lesson is liked, notify the teacher (if they aren't the liker)."""
    if not created:
        return

    try:
        if instance.user_id != instance.lesson.teacher_id:
            from apps.notifications.senders import notify_like_on_lesson
            notify_like_on_lesson(
                lesson=instance.lesson,
                liker=instance.user,
                lesson_teacher=instance.lesson.teacher,
            )
    except Exception as e:
        logger.error(f'Failed to send like notification: {e}')


@receiver(post_save, sender='feed.TeacherFollower')
def teacher_follower_saved(sender, instance, created, **kwargs):
    """When someone follows a teacher, notify the teacher."""
    if not created:
        return

    try:
        from apps.notifications.senders import notify_new_follower
        notify_new_follower(
            teacher=instance.teacher,
            follower=instance.user,
        )
    except Exception as e:
        logger.error(f'Failed to send follow notification: {e}')


# ─── Assignment Signals ──────────────────────────────────────────────────────

@receiver(post_save, sender='assignments.Assignment')
def assignment_saved(sender, instance, created, **kwargs):
    """When a new assignment is posted, notify students in the class."""
    if not created:
        return

    try:
        from apps.notifications.senders import notify_new_assignment
        notify_new_assignment(instance)
    except Exception as e:
        logger.error(f'Failed to send assignment notification: {e}')


@receiver(post_save, sender='assignments.AssignmentSubmission')
def assignment_graded(sender, instance, created, **kwargs):
    """When an assignment is graded (score changes), notify the student."""
    if not created and instance.score is not None:
        # Only notify when score was set (graded)
        try:
            from apps.notifications.senders import notify_assignment_graded
            notify_assignment_graded(instance)
        except Exception as e:
            logger.error(f'Failed to send grade notification: {e}')


# ─── Attendance Signals ──────────────────────────────────────────────────────

@receiver(post_save, sender='attendance.Attendance')
def attendance_marked(sender, instance, created, **kwargs):
    """When attendance is marked, notify the student."""
    if not created:
        return

    try:
        from apps.notifications.senders import notify_attendance_marked
        notify_attendance_marked(
            student=instance.student,
            date=instance.date,
            status=instance.status,
        )
    except Exception as e:
        logger.error(f'Failed to send attendance notification: {e}')


# ─── Billing/Fee Signals ─────────────────────────────────────────────────────

@receiver(post_save, sender='billing.Fee')
def fee_created(sender, instance, created, **kwargs):
    """When a new fee is created, send a notification."""
    if not created:
        return

    try:
        from apps.notifications.senders import notify_fee_reminder
        notify_fee_reminder(
            student=instance.student,
            fee=instance,
        )
    except Exception as e:
        logger.error(f'Failed to send fee notification: {e}')


# ─── School Announcements / Notices / Events ─────────────────────────────────

@receiver(post_save, sender='academics.Notice')
def notice_posted(sender, instance, created, **kwargs):
    """When a new school notice/announcement is posted, notify the school."""
    if not created:
        return

    try:
        from apps.notifications.senders import notify_notice_posted
        notify_notice_posted(instance)
    except Exception as e:
        logger.error(f'Failed to send notice notification: {e}')


@receiver(post_save, sender='academics.SchoolEvent')
def school_event_created(sender, instance, created, **kwargs):
    """When a new school event is created, notify the school."""
    if not created:
        return

    try:
        from apps.notifications.senders import notify_school_event
        notify_school_event(instance)
    except Exception as e:
        logger.error(f'Failed to send school event notification: {e}')


# ─── Exam / Grading Signals ──────────────────────────────────────────────────

@receiver(post_save, sender='academics.ExamResult')
def exam_result_saved(sender, instance, created, **kwargs):
    """When an exam result is recorded, notify the student."""
    if not created:
        return

    try:
        from apps.notifications.senders import notify_exam_result_posted
        notify_exam_result_posted(instance)
    except Exception as e:
        logger.error(f'Failed to send exam result notification: {e}')
