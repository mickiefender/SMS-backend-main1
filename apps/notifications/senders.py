"""
High-level notification sender functions for every event type.

Each function is a thin wrapper around send_notification() that fills in
the correct category, notification_type, title, message, and deep-link metadata.
Import these in your Django apps or signals to fire notifications.
"""
from typing import Optional
from apps.notifications.services.notification_service import send_notification, send_notification_to_class


# ─── Feed ────────────────────────────────────────────────────────────────────

def notify_new_lesson(lesson, follower):
    """Notify a follower that a teacher published a new lesson."""
    return send_notification(
        recipient=follower,
        notification_type='new_lesson_from_followed_teacher',
        category='feed',
        title=f'New Lesson: {lesson.title}',
        message=f'{lesson.teacher.get_full_name()} published "{lesson.title}"',
        target_screen='lesson_detail',
        target_id=str(lesson.id),
        image_url=lesson.thumbnail_url or '',
    )


def notify_comment_on_lesson(lesson, commenter, lesson_author):
    """Notify a lesson author that someone commented."""
    return send_notification(
        recipient=lesson_author,
        notification_type='comment_on_lesson',
        category='comment',
        title=f'New Comment on "{lesson.title}"',
        message=f'{commenter.get_full_name()} commented: {commenter.body[:120]}',
        target_screen='lesson_detail',
        target_id=str(lesson.id),
    )


def notify_comment_reply(comment, replier, original_author):
    """Notify a user that someone replied to their comment."""
    return send_notification(
        recipient=original_author,
        notification_type='comment_reply',
        category='comment',
        title='New Reply to Your Comment',
        message=f'{replier.get_full_name()} replied: {replier.body[:120]}',
        target_screen='lesson_detail',
        target_id=str(comment.lesson_id),
    )


def notify_like_on_lesson(lesson, liker, lesson_teacher):
    """Notify a teacher that someone liked their lesson."""
    return send_notification(
        recipient=lesson_teacher,
        notification_type='lesson_liked',
        category='like',
        title=f'Someone Liked "{lesson.title}"',
        message=f'{liker.get_full_name()} liked your lesson "{lesson.title}"',
        target_screen='lesson_detail',
        target_id=str(lesson.id),
    )


def notify_new_follower(teacher, follower):
    """Notify a teacher that someone followed them."""
    return send_notification(
        recipient=teacher,
        notification_type='new_follower',
        category='feed',
        title='New Follower!',
        message=f'{follower.get_full_name()} started following you',
        target_screen='teacher_profile',
        target_id=str(teacher.id),
    )


# ─── School Announcements ────────────────────────────────────────────────────

def notify_school_announcement(announcement, school):
    """School-wide announcement."""
    from apps.notifications.services.notification_service import send_notification_to_school
    return send_notification_to_school(
        school=school,
        notification_type='school_announcement',
        category='school_announcement',
        title=announcement.title,
        message=announcement.content[:200],
        target_screen='announcement_view',
        target_id=str(announcement.id),
        priority=announcement.priority if hasattr(announcement, 'priority') else 'normal',
    )


# ─── Assignments ─────────────────────────────────────────────────────────────

def notify_new_assignment(assignment):
    """New assignment posted to a class."""
    return send_notification_to_class(
        class_obj=assignment.class_obj,
        notification_type='new_assignment',
        category='assignment',
        title=f'New Assignment: {assignment.title}',
        message=f'{assignment.teacher.get_full_name()} posted "{assignment.title}" due {assignment.due_date.strftime("%b %d")}',
        target_screen='assignment_view',
        target_id=str(assignment.id),
    )


def notify_assignment_graded(submission):
    """Notify a student that their assignment was graded."""
    return send_notification(
        recipient=submission.student,
        notification_type='assignment_graded',
        category='assignment',
        title=f'Assignment Graded: {submission.assignment.title}',
        message=f'Your assignment scored {submission.score:.0f}/100. Feedback: {submission.feedback[:100] if submission.feedback else "Check your results."}',
        target_screen='assignment_view',
        target_id=str(submission.assignment_id),
        priority='high',
    )


# ─── Grades ──────────────────────────────────────────────────────────────────

def notify_grade_posted(student, subject_name, grade, term):
    """Notify a student that a grade was posted."""
    return send_notification(
        recipient=student,
        notification_type='grade_posted',
        category='grade',
        title=f'Grade Posted: {subject_name}',
        message=f'Your grade for {subject_name} ({term}) has been posted: {grade}',
        target_screen='grade_view',
        target_id=str(student.id),
        priority='high',
    )


# ─── Attendance ──────────────────────────────────────────────────────────────

def notify_attendance_marked(student, date, status):
    """Notify a student that their attendance was marked."""
    status_label = {'present': 'Present', 'absent': 'Absent', 'late': 'Late', 'excused': 'Excused'}
    label = status_label.get(status, status)
    return send_notification(
        recipient=student,
        notification_type='attendance_marked',
        category='attendance',
        title=f'Attendance: {label}',
        message=f'Your attendance for {date.strftime("%b %d, %Y")} has been marked: {label}',
        target_screen='attendance_view',
        priority='low',
    )


# ─── Fees ────────────────────────────────────────────────────────────────────

def notify_fee_reminder(student, fee):
    """Remind a student/parent about an upcoming or overdue fee."""
    return send_notification(
        recipient=student,
        notification_type='fee_reminder',
        category='fee_reminder',
        title=f'Fee Reminder: {fee.name}',
        message=f'{fee.name} fee of GHS {fee.amount:.2f} is due {fee.due_date.strftime("%b %d, %Y")}',
        target_screen='fee_view',
        target_id=str(fee.id),
        priority='high',
    )


def notify_fee_payment_confirmed(student, fee, amount_paid):
    """Confirm that a fee payment was received."""
    return send_notification(
        recipient=student,
        notification_type='fee_payment_confirmed',
        category='fee_reminder',
        title=f'Payment Received: {fee.name}',
        message=f'Payment of GHS {amount_paid:.2f} for {fee.name} has been confirmed.',
        target_screen='fee_view',
        target_id=str(fee.id),
    )


# ─── Upload Status ───────────────────────────────────────────────────────────

def notify_upload_status(teacher, lesson, status):
    """Notify a teacher about their video upload status."""
    status_messages = {
        'processing': 'Your video is being processed. It will be available shortly.',
        'approved': 'Your lesson has been approved and is now live!',
        'rejected': 'Your lesson was not approved. Please check the feedback.',
        'failed': 'Video processing failed. Please try uploading again.',
    }
    message = status_messages.get(status, f'Upload status updated: {status}')
    return send_notification(
        recipient=teacher,
        notification_type=f'upload_{status}',
        category='upload_status',
        title=f'Lesson {status.title()}: {lesson.title}',
        message=message,
        target_screen='lesson_detail',
        target_id=str(lesson.id),
        priority='high' if status in ('rejected', 'failed') else 'normal',
    )


# ─── Messages ────────────────────────────────────────────────────────────────

def notify_new_message(recipient, sender, preview):
    """Notify a user that they received a new message."""
    return send_notification(
        recipient=recipient,
        notification_type='new_message',
        category='message',
        title=f'Message from {sender.get_full_name()}',
        message=preview[:150],
        target_screen='chat',
        target_id=str(sender.id),
    )


# ─── App Updates ─────────────────────────────────────────────────────────────

def notify_app_update(users, version, changelog_preview):
    """Notify a list of users about an app update."""
    from apps.notifications.services.notification_service import send_notification
    created = []
    for user in users:
        n = send_notification(
            recipient=user,
            notification_type='app_update',
            category='app_update',
            title=f'Alara v{version} Available!',
            message=changelog_preview[:200],
            target_screen='app_update',
            target_id=version,
            priority='low',
            skip_preference_check=True,
        )
        if n:
            created.append(n)
    return created
