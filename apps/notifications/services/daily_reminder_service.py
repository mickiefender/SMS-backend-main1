"""
Personalised Daily Learning Reminder engine.

Builds a single, relevant, high-value reminder for each user once per day.
The engine prioritises urgency so users are never spammed:

STUDENTS (priority order):
  1. Assignments due today or tomorrow
  2. Upcoming exams
  3. Revision / study reminders (based on learning streak)
  4. Important school announcements
  5. General daily learning reminder (fallback)

TEACHERS (priority order):
  1. Pending grading tasks
  2. Attendance reminders (unmarked attendance)
  3. Upcoming classes / activities today
  4. Important school announcements
  5. General daily teaching reminder (fallback)

A reminder is only created when there is something relevant to say. The
task scheduler is responsible for respecting the user's preferred time and
the once-per-day guard (see tasks.send_daily_learning_reminders).
"""
import logging
from datetime import timedelta, datetime
from django.utils import timezone

from apps.notifications.services.notification_service import send_notification

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _start_of_day(dt=None):
    """Return today's midnight in the current timezone."""
    dt = dt or timezone.now()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_day(dt=None):
    """Return tomorrow's midnight (exclusive end of today)."""
    return _start_of_day(dt) + timedelta(days=1)


def _safe(queryset):
    """Return a list for a queryset, tolerating ImportError/table issues."""
    try:
        return list(queryset)
    except Exception as e:  # noqa: BLE001
        logger.debug('daily_reminder query skipped: %s', e)
        return []


# ---------------------------------------------------------------------------
# Student reminder items
# ---------------------------------------------------------------------------

def _student_assignments_due(student):
    """Assignments for the student's active classes due today or tomorrow."""
    try:
        from apps.assignments.models import Assignment
        from apps.academics.models import StudentClass
    except ImportError:
        return []

    classes = StudentClass.objects.filter(
        student=student, is_active=True
    ).values_list('class_obj_id', flat=True)

    now = timezone.now()
    tomorrow_end = _end_of_day(now) + timedelta(days=1)

    qs = Assignment.objects.filter(
        class_obj_id__in=list(classes),
        due_date__gte=now,
        due_date__lte=tomorrow_end,
    ).select_related('subject')[:5]

    items = []
    for a in _safe(qs):
        days = (a.due_date.date() - now.date()).days
        when = 'today' if days <= 0 else 'tomorrow'
        subj = a.subject.name if a.subject else 'your subject'
        items.append({
            'priority': 1,
            'kind': 'assignment',
            'title': f'Assignment due {when}',
            'message': (
                f'"{a.title}" ({subj}) is due {when} at '
                f'{a.due_date.strftime("%H:%M")}.'
            ),
            'target_screen': 'assignment_view',
            'target_id': str(a.id),
        })
    return items


def _student_upcoming_exams(student):
    """Exams for the student's active classes within the next 7 days."""
    try:
        from apps.academics.models import Exam, StudentClass
    except ImportError:
        return []

    classes = StudentClass.objects.filter(
        student=student, is_active=True
    ).values_list('class_obj_id', flat=True)

    today = timezone.now().date()
    window_end = today + timedelta(days=7)

    qs = Exam.objects.filter(
        class_obj_id__in=list(classes),
        exam_date__gte=today,
        exam_date__lte=window_end,
    ).select_related('subject')[:5]

    items = []
    for e in _safe(qs):
        days = (e.exam_date - today).days
        when = 'today' if days == 0 else (
            'tomorrow' if days == 1 else f'in {days} days'
        )
        subj = e.subject.name if e.subject else 'a subject'
        items.append({
            'priority': 1,
            'kind': 'exam',
            'title': 'Upcoming exam',
            'message': (
                f'{subj} exam "{e.title}" is {when} '
                f'({e.exam_date.strftime("%b %d")}) at '
                f'{e.exam_time.strftime("%H:%M") if e.exam_time else "TBA"}.'
            ),
            'target_screen': 'exam_view',
            'target_id': str(e.id),
        })
    return items


def _student_revision_reminder(student):
    """Study/revision nudge if the student has an active learning streak
    but hasn't engaged recently (no watch today)."""
    try:
        from apps.feed.models import WatchHistory, LearningProfile
    except ImportError:
        return []

    today_start = _start_of_day()
    watched_today = WatchHistory.objects.filter(
        user=student, last_watched_at__gte=today_start
    ).exists()
    if watched_today:
        return []

    profile = LearningProfile.objects.filter(user=student).first()
    streak = profile.learning_streak_days if profile else 0

    if streak > 0:
        message = (
            f'You are on a {streak}-day learning streak! Keep it going with '
            'a quick lesson from your personalised feed.'
        )
    else:
        message = (
            'A quick revision session today will keep your learning on track. '
            'Pick a lesson from your feed.'
        )

    return [{
        'priority': 2,
        'kind': 'revision',
        'title': 'Time to learn',
        'message': message,
        'target_screen': 'feed',
        'target_id': '',
    }]


def _student_announcements(student):
    """Recent school-wide announcements (last 5 unread)."""
    try:
        from apps.academics.models import Notice
        from apps.notifications.models import Notification
    except ImportError:
        return []

    if not student.school_id:
        return []

    announcements = Notice.objects.filter(
        school_id=student.school_id, is_active=True
    ).order_by('-created_at')[:3]

    # Only show announcements the student hasn't already seen in-app.
    seen = set(Notification.objects.filter(
        recipient=student, category='school_announcement'
    ).values_list('target_id', flat=True))

    items = []
    for notice in _safe(announcements):
        if str(notice.id) in seen:
            continue
        items.append({
            'priority': 3,
            'kind': 'announcement',
            'title': 'School announcement',
            'message': notice.title,
            'target_screen': 'announcement_view',
            'target_id': str(notice.id),
        })
    return items


# ---------------------------------------------------------------------------
# Teacher reminder items
# ---------------------------------------------------------------------------

def _teacher_pending_grading(teacher):
    """Submissions awaiting grading for the teacher's assignments."""
    try:
        from apps.assignments.models import AssignmentSubmission
    except ImportError:
        return []

    qs = AssignmentSubmission.objects.filter(
        assignment__teacher=teacher,
        status__in=['submitted'],
        score__isnull=True,
    ).select_related('assignment', 'student')[:5]

    items = []
    for s in _safe(qs):
        items.append({
            'priority': 1,
            'kind': 'grading',
            'title': 'Pending grading',
            'message': (
                f'{s.student.get_full_name()} submitted "{s.assignment.title}". '
                'Ready to grade.'
            ),
            'target_screen': 'assignment_view',
            'target_id': str(s.assignment_id),
        })
    return items


def _teacher_attendance_reminder(teacher):
    """Classes the teacher should take attendance for today (not recorded)."""
    try:
        from apps.academics.models import ClassTeacher, Timetable
        from apps.attendance.models import Attendance
    except ImportError:
        return []

    today = timezone.now().date()
    day_name = today.strftime('%A').lower()

    # Classes the teacher is responsible for as form tutor.
    managed = ClassTeacher.objects.filter(
        teacher=teacher, is_form_tutor=True
    ).select_related('class_obj')

    items = []
    for ct in _safe(managed):
        cls = ct.class_obj
        marked_today = Attendance.objects.filter(
            class_obj=cls, date=today
        ).exists()
        if marked_today:
            continue
        items.append({
            'priority': 1,
            'kind': 'attendance',
            'title': 'Attendance reminder',
            'message': (
                f'Attendance for {cls.name} has not been marked today. '
                'Please record it.'
            ),
            'target_screen': 'attendance_view',
            'target_id': str(cls.id),
        })
    return items


def _teacher_upcoming_classes(teacher):
    """Today's classes from the timetable for this teacher."""
    try:
        from apps.academics.models import Timetable
    except ImportError:
        return []

    today = timezone.now().date()
    day_name = today.strftime('%A').lower()

    qs = Timetable.objects.filter(
        teacher=teacher, day=day_name,
    ).select_related('class_obj', 'subject').order_by('start_time')[:5]

    items = []
    for t in _safe(qs):
        items.append({
            'priority': 2,
            'kind': 'class',
            'title': 'Upcoming class today',
            'message': (
                f'{t.subject.name if t.subject else "Class"} for '
                f'{t.class_obj.name} at {t.start_time.strftime("%H:%M")}.'
            ),
            'target_screen': 'timetable_view',
            'target_id': str(t.id),
        })
    return items


def _teacher_announcements(teacher):
    """Recent school-wide announcements for the teacher's school."""
    try:
        from apps.academics.models import Notice
        from apps.notifications.models import Notification
    except ImportError:
        return []

    if not teacher.school_id:
        return []

    announcements = Notice.objects.filter(
        school_id=teacher.school_id, is_active=True
    ).order_by('-created_at')[:3]

    seen = set(Notification.objects.filter(
        recipient=teacher, category='school_announcement'
    ).values_list('target_id', flat=True))

    items = []
    for notice in _safe(announcements):
        if str(notice.id) in seen:
            continue
        items.append({
            'priority': 3,
            'kind': 'announcement',
            'title': 'School announcement',
            'message': notice.title,
            'target_screen': 'announcement_view',
            'target_id': str(notice.id),
        })
    return items


def _teacher_general_reminder(teacher):
    """Fallback general reminder when nothing is urgent."""
    return [{
        'priority': 4,
        'kind': 'general',
        'title': 'Daily teaching reminder',
        'message': (
            'Review your pending tasks and prepare for today\'s classes to '
            'keep things running smoothly.'
        ),
        'target_screen': 'home',
        'target_id': '',
    }]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_reminder_items(user):
    """
    Return an ordered list of reminder items for a user.

    Items are returned lowest-priority-number first (1 = most urgent).
    Empty list means nothing relevant — the caller should skip sending.
    """
    if getattr(user, 'role', '') == 'teacher':
        items = (
            _teacher_pending_grading(user)
            + _teacher_attendance_reminder(user)
            + _teacher_upcoming_classes(user)
            + _teacher_announcements(user)
        )
        if not items:
            items = _teacher_general_reminder(user)
    else:
        # Default to student behaviour.
        items = (
            _student_assignments_due(user)
            + _student_upcoming_exams(user)
            + _student_revision_reminder(user)
            + _student_announcements(user)
        )
        if not items:
            items = _student_general_reminder(user)

    # Sort by priority number ascending (1 = first).
    items.sort(key=lambda x: x['priority'])
    return items


def _student_general_reminder(student):
    """Fallback general learning reminder for students."""
    return [{
        'priority': 4,
        'kind': 'general',
        'title': 'Daily learning reminder',
        'message': (
            'A few minutes of learning today goes a long way. Check your '
            'feed for something new!'
        ),
        'target_screen': 'feed',
        'target_id': '',
    }]


def compose_reminder_notification(user):
    """
    Build a single Notification dict for a user's daily reminder.

    Returns a dict suitable for send_notification(...), or None if the user
    has no relevant items / is disabled. The scheduler calls this once per
    day per user.
    """
    try:
        from apps.notifications.models import NotificationPreference
        prefs = NotificationPreference.objects.filter(user=user).first()
    except Exception:  # noqa: BLE001
        prefs = None

    # Master toggle + category preference.
    if prefs is not None:
        if not prefs.daily_reminder_enabled:
            return None
        if not prefs.is_category_enabled('daily_reminder'):
            return None
        if prefs.has_received_daily_reminder_today():
            return None

    items = build_reminder_items(user)
    if not items:
        return None

    # Compose title + body from the top items (cap at 3 lines / 2 items).
    top = items[0]
    extra = items[1] if len(items) > 1 else None

    title = top['title']
    message = top['message']
    if extra:
        message = f"{message}\n\nAlso: {extra['message']}"

    return {
        'recipient': user,
        'notification_type': 'daily_learning_reminder',
        'category': 'daily_reminder',
        'title': title,
        'message': message[:500],
        'target_screen': top['target_screen'],
        'target_id': top['target_id'],
        'priority': 'normal',
    }


def send_daily_reminder(user):
    """
    Send a single daily learning reminder to a user.

    Returns the created Notification or None. Updates
    NotificationPreference.last_daily_reminder_at to prevent spamming.
    """
    payload = compose_reminder_notification(user)
    if not payload:
        return None

    notification = send_notification(**payload)
    if notification:
        try:
            from apps.notifications.models import NotificationPreference
            prefs, _ = NotificationPreference.objects.get_or_create(user=user)
            prefs.last_daily_reminder_at = timezone.now()
            prefs.save(update_fields=['last_daily_reminder_at'])
        except Exception as e:  # noqa: BLE001
            logger.warning('Failed to stamp daily reminder for user %s: %s', user.id, e)

    return notification
