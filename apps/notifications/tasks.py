"""
Celery tasks for the notifications app.

Handles async notification delivery, scheduled reminders, and maintenance.
"""
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.notifications.models import Notification, Device, NotificationPreference
from apps.notifications.services import fcm_service

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_bulk_notification(self, notification_id, user_ids):
    """
    Send a stored notification to a list of user IDs.
    Used for bulk operations like class-wide or school-wide notifications.
    """
    try:
        notification = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        logger.error(f'Notification {notification_id} not found')
        return 0

    sent_count = fcm_service.send_to_multiple_users(notification, user_ids)
    logger.info(f'Bulk notification {notification_id}: sent to {sent_count} of {len(user_ids)} users')
    return sent_count


@shared_task
def send_scheduled_reminders():
    """
    Check for upcoming due dates and send reminder notifications.
    Runs via Celery Beat (e.g. every hour).
    """
    now = timezone.now()
    reminder_window = now + timedelta(days=3)

    # Remind about assignments due in 3 days
    from apps.assignments.models import Assignment
    upcoming = Assignment.objects.filter(
        due_date__gte=now,
        due_date__lte=reminder_window,
    ).select_related('class_obj')

    for assignment in upcoming:
        students = User.objects.filter(
            role='student',
            studentprofile__in=assignment.class_obj.studentclass_set.all()
        )
        for student in students:
            from apps.notifications.services.notification_service import send_notification
            send_notification(
                recipient=student,
                notification_type='assignment_reminder',
                category='assignment_reminder',
                title=f'Assignment Due: {assignment.title}',
                message=f'Your assignment "{assignment.title}" is due {assignment.due_date.strftime("%b %d")}',
                target_screen='assignment_view',
                target_id=str(assignment.id),
                priority='high',
            )

    # Remind about fee payments due in 7 days
    from apps.billing.models import Fee
    fee_reminder_window = now + timedelta(days=7)
    upcoming_fees = Fee.objects.filter(
        due_date__gte=now,
        due_date__lte=fee_reminder_window,
        is_paid=False,
    ).select_related('student')

    for fee in upcoming_fees:
        from apps.notifications.services.notification_service import send_notification
        send_notification(
            recipient=fee.student,
            notification_type='fee_reminder',
            category='fee_reminder',
            title=f'Fee Reminder: {fee.name}',
            message=f'Your {fee.name} fee of GHS {fee.amount:.2f} is due {fee.due_date.strftime("%b %d")}',
            target_screen='fee_view',
            target_id=str(fee.id),
            priority='high',
        )

    logger.info(f'Scheduled reminders sent: {upcoming.count()} assignments, {upcoming_fees.count()} fees')
    return upcoming.count() + upcoming_fees.count()


@shared_task
def clean_invalid_devices():
    """
    Deactivate FCM tokens that haven't been seen in 90 days.
    Runs via Celery Beat (e.g. daily).
    """
    cutoff = timezone.now() - timedelta(days=90)
    count, _ = Device.objects.filter(
        is_active=True,
        last_seen_at__lt=cutoff,
    ).update(is_active=False)
    logger.info(f'Cleaned {count} stale devices')
    return count


@shared_task
def send_daily_learning_reminders():
    """
    Send personalised daily learning reminders to students and teachers.

    This task is scheduled via Celery Beat (e.g. every hour). It:
      * respects each user's preferred reminder time (daily_reminder_time,
        default 16:00 UTC) — only fires when the current hour matches;
      * honours the master toggle + daily_reminder category preference;
      * never sends more than once per day per user
        (last_daily_reminder_at guard);
      * composes a single, prioritised, personalised notification via
        daily_reminder_service.
    """
    from apps.notifications.services import daily_reminder_service

    now = timezone.now()
    current_hour = now.hour

    # Reasonable window: we send in the hour that matches the user's
    # preferred time. Users with no explicit time default to 16:00 UTC.
    default_hour = 16

    candidates = User.objects.filter(is_active=True).filter(
        role__in=['student', 'teacher']
    )

    sent_count = 0
    for user in candidates:
        try:
            prefs = NotificationPreference.objects.filter(user=user).first()
        except NotificationPreference.DoesNotExist:
            prefs = None

        # Master toggle.
        if prefs is not None and not prefs.daily_reminder_enabled:
            continue
        # Category preference.
        if prefs is not None and not prefs.is_category_enabled('daily_reminder'):
            continue
        # Once per day.
        if prefs is not None and prefs.has_received_daily_reminder_today():
            continue

        preferred_hour = default_hour
        if prefs is not None and prefs.daily_reminder_time is not None:
            preferred_hour = prefs.daily_reminder_time.hour

        if preferred_hour != current_hour:
            continue

        try:
            n = daily_reminder_service.send_daily_reminder(user)
            if n:
                sent_count += 1
        except Exception as e:
            logger.warning('Daily reminder failed for user %s: %s', user.id, e)

    logger.info(f'Sent {sent_count} daily learning reminders')
    return sent_count


@shared_task
def send_feed_notifications_for_new_lesson(lesson_id):
    """
    Notify followers when a teacher publishes a new lesson.
    Triggered by signal.
    """
    from apps.feed.models import FeedLesson, TeacherFollower
    from apps.notifications.services.notification_service import send_notification

    try:
        lesson = FeedLesson.objects.get(id=lesson_id)
    except FeedLesson.DoesNotExist:
        return

    followers = TeacherFollower.objects.filter(
        teacher=lesson.teacher
    ).select_related('user')

    sent_count = 0
    for follow in followers:
        n = send_notification(
            recipient=follow.user,
            notification_type='new_lesson_from_followed_teacher',
            category='feed',
            title=f'New Lesson: {lesson.title}',
            message=f'{lesson.teacher.get_full_name()} published "{lesson.title}" in {lesson.subject.name if lesson.subject else ""}',
            target_screen='lesson_detail',
            target_id=str(lesson.id),
            image_url=lesson.thumbnail_url or '',
            priority='normal',
        )
        if n:
            sent_count += 1

    logger.info(f'Feed notifications for lesson {lesson_id}: sent to {sent_count} followers')
    return sent_count
