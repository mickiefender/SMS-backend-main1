"""
Centralized notification service — creates, stores, deduplicates, and delivers
notifications across the entire platform.

Every event type in the system goes through this service:
- Feed events (new lesson, comment, like, follow)
- School announcements
- Assignments (new, reminder, graded)
- Attendance
- Fees
- Messages
- Live classes
- Upload status
- Daily reminders
- App updates
"""
import hashlib
import logging
from typing import List, Optional, Dict, Any
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.notifications.models import Notification, NotificationPreference, Device
from apps.notifications.services.fcm_service import (
    send_to_user,
    send_to_multiple_users,
    send_to_topic,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ─── Category Constants ──────────────────────────────────────────────────────

CATEGORY_FEED = 'feed'
CATEGORY_SCHOOL_ANNOUNCEMENT = 'school_announcement'
CATEGORY_ASSIGNMENT = 'assignment'
CATEGORY_ASSIGNMENT_REMINDER = 'assignment_reminder'
CATEGORY_GRADE = 'grade'
CATEGORY_ATTENDANCE = 'attendance'
CATEGORY_FEE_REMINDER = 'fee_reminder'
CATEGORY_MESSAGE = 'message'
CATEGORY_LIVE_CLASS = 'live_class'
CATEGORY_UPLOAD_STATUS = 'upload_status'
CATEGORY_COMMENT = 'comment'
CATEGORY_LIKE = 'like'
CATEGORY_DAILY_REMINDER = 'daily_reminder'
CATEGORY_APP_UPDATE = 'app_update'


# ─── Core Functions ──────────────────────────────────────────────────────────

def _make_dedup_hash(recipient_id, category, notification_type, target_id):
    raw = f'{recipient_id}:{category}:{notification_type}:{target_id or ""}'
    return hashlib.sha256(raw.encode()).hexdigest()


def send_notification(
    recipient,
    notification_type: str,
    category: str,
    title: str,
    message: str,
    target_screen: str = '',
    target_id: str = '',
    image_url: str = '',
    priority: str = 'normal',
    extra_data: Optional[Dict] = None,
    skip_push: bool = False,
    skip_preference_check: bool = False,
) -> Optional[Notification]:
    """
    Create a notification, store it in the database, and deliver it via FCM push.

    - Deduplicates: identical notification (same recipient + category + type + target)
      sent within the last 5 minutes is skipped.
    - Respects the user's NotificationPreference settings (unless
      skip_preference_check=True).
    - Skips push delivery if the user has push disabled globally or for
      the given category.
    - Anonymous / guest users are silently skipped.
    """
    # Resolve user object if recipient is an integer
    if isinstance(recipient, int):
        try:
            recipient = User.objects.get(id=recipient)
        except User.DoesNotExist:
            logger.warning(f'User {recipient} not found — skipping notification')
            return None

    # Guests get no personalized push
    if getattr(recipient, 'is_anonymous', False) or not recipient.is_authenticated:
        logger.debug('Skipping notification for anonymous user')
        return None

    dedup_hash = _make_dedup_hash(
        recipient.id, category, notification_type, target_id
    )

    # Deduplicate within 5-minute window
    recent = Notification.objects.filter(
        dedup_hash=dedup_hash,
        created_at__gte=timezone.now() - timezone.timedelta(minutes=5),
    ).exists()
    if recent:
        logger.debug(f'Dedup hit — skipping notification {dedup_hash}')
        return None

    # Check user preferences
    if not skip_preference_check:
        try:
            prefs = NotificationPreference.objects.get(user=recipient)
            if not prefs.push_enabled:
                skip_push = True
            if not prefs.is_category_enabled(category):
                logger.debug(f'Category {category} disabled for user {recipient.id}')
                return None
        except NotificationPreference.DoesNotExist:
            pass  # Default: everything enabled

    # Persist notification
    with transaction.atomic():
        notification = Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            category=category,
            title=title,
            message=message,
            target_screen=target_screen,
            target_id=str(target_id) if target_id else '',
            image_url=image_url,
            priority=priority,
            dedup_hash=dedup_hash,
        )

    # Deliver push
    if not skip_push:
        try:
            sent = send_to_user(notification, recipient, extra_data)
            if sent:
                logger.info(f'Push sent to {sent} device(s) for user {recipient.id}')
        except Exception as e:
            logger.error(f'Push delivery failed for user {recipient.id}: {e}')

    return notification


def send_notification_to_class(
    class_obj,
    notification_type: str,
    category: str,
    title: str,
    message: str,
    target_screen: str = '',
    target_id: str = '',
    priority: str = 'normal',
) -> List[Notification]:
    """Send a notification to all students in a specific class."""
    from apps.academics.models import StudentClass

    student_ids = StudentClass.objects.filter(
        class_obj=class_obj, is_active=True
    ).values_list('student_id', flat=True)

    students = User.objects.filter(id__in=student_ids, role='student', is_active=True)
    created = []
    for student in students:
        n = send_notification(
            recipient=student,
            notification_type=notification_type,
            category=category,
            title=title,
            message=message,
            target_screen=target_screen,
            target_id=target_id,
            priority=priority,
        )
        if n:
            created.append(n)
    return created


def send_notification_to_school(
    school,
    notification_type: str,
    category: str,
    title: str,
    message: str,
    target_screen: str = '',
    target_id: str = '',
    priority: str = 'normal',
    target_roles: Optional[List[str]] = None,
) -> List[Notification]:
    """Send a notification to all users in a school, optionally filtered by role."""
    qs = User.objects.filter(school=school, is_active=True)
    if target_roles:
        qs = qs.filter(role__in=target_roles)

    created = []
    for user in qs:
        n = send_notification(
            recipient=user,
            notification_type=notification_type,
            category=category,
            title=title,
            message=message,
            target_screen=target_screen,
            target_id=target_id,
            priority=priority,
        )
        if n:
            created.append(n)
    return created


def send_notification_to_role(
    role: str,
    notification_type: str,
    category: str,
    title: str,
    message: str,
    target_screen: str = '',
    target_id: str = '',
    priority: str = 'normal',
) -> List[Notification]:
    """Send a notification to all users with a specific role across the platform."""
    users = User.objects.filter(role=role, is_active=True)
    created = []
    for user in users:
        n = send_notification(
            recipient=user,
            notification_type=notification_type,
            category=category,
            title=title,
            message=message,
            target_screen=target_screen,
            target_id=target_id,
            priority=priority,
        )
        if n:
            created.append(n)
    return created


# ─── Read / Update helpers ───────────────────────────────────────────────────

def mark_as_read(notification_id, user) -> bool:
    """Mark a single notification as read."""
    try:
        notification = Notification.objects.get(id=notification_id, recipient=user)
        notification.mark_as_read()
        return True
    except Notification.DoesNotExist:
        return False


def mark_all_as_read(user) -> int:
    """Mark all unread notifications as read for a user. Returns count updated."""
    count = Notification.objects.filter(
        recipient=user, is_read=False
    ).update(is_read=True, read_at=timezone.now())
    return count


def get_unread_count(user) -> int:
    """Quick unread count for a user."""
    return Notification.objects.filter(recipient=user, is_read=False).count()


def get_notifications_for_user(user, limit=50, offset=0, is_read=None, category=None):
    """Paginated notification list for a user with optional filters."""
    qs = Notification.objects.filter(recipient=user)
    if is_read is not None:
        qs = qs.filter(is_read=is_read)
    if category:
        qs = qs.filter(category=category)
    return qs.order_by('-created_at')[offset:offset + limit]


# ─── Device / Preference helpers ─────────────────────────────────────────────

def register_device(user, fcm_token, platform='android', device_name=''):
    """Register or update an FCM device token for a user."""
    device, created = Device.objects.update_or_create(
        fcm_token=fcm_token,
        defaults={
            'user': user,
            'platform': platform,
            'device_name': device_name,
            'is_active': True,
        },
    )
    Device.objects.filter(user=user, fcm_token=fcm_token).update(is_active=True)
    return device, created


def unregister_device(fcm_token) -> bool:
    """Deactivate a device by its FCM token."""
    updated = Device.objects.filter(fcm_token=fcm_token).update(is_active=False)
    return updated > 0


def get_or_create_preferences(user):
    """Get or create notification preferences for a user."""
    prefs, created = NotificationPreference.objects.get_or_create(user=user)
    return prefs, created
