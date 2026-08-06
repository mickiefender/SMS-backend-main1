"""Email notification tasks for Celery using Resend with localhost fallback"""
from celery import shared_task
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
from django.core.mail import send_mass_mail, EmailMultiAlternatives
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
import os
from django.conf import settings
from core.notifications import notification_service

from apps.schools.models import School
from apps.academics.models import Class, StudentClass
from apps.assignments.models import Assignment
from apps.messaging.models import Notice, Announcement, PersonalNotice

User = get_user_model()

# Import Resend
try:
    import resend
    resend.api_key = os.environ.get("RESEND_API_KEY", "")
except ImportError:
    resend = None

# Check if we're in development/localhost
IS_DEVELOPMENT = os.environ.get("DEBUG", "False") == "True" or os.environ.get("ENVIRONMENT") == "development"
RESEND_DOMAIN = os.environ.get("RESEND_DOMAIN", "localhost")


@shared_task
def send_notice_email(notice_id):
    """Send notice emails to recipients asynchronously via Resend or fallback"""
    try:
        notice = Notice.objects.get(id=notice_id)
        recipients = get_notice_recipients(notice)
        
        if not recipients:
            return f"No recipients for notice {notice_id}"
        
        recipient_emails = [user.email for user in recipients if user.email]
        
        if not recipient_emails:
            return f"No valid email addresses for notice {notice_id}"
        
        context = {
            'notice_title': notice.title,
            'notice_content': notice.content,
            'notice_priority': notice.priority,
            'created_by': notice.created_by.get_full_name() if notice.created_by else 'School Admin',
            'school_name': notice.school.name,
            'logo_url': notice.school.get_logo_url(),
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:3000'),
        }
        
        html_message = render_to_string('emails/notice_email.html', context)
        
        # Use Resend if API key exists and not localhost, otherwise use Django backend
        if resend and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
            try:
                email_response = resend.Emails.send({
                    "from": f"School Management <notices@{RESEND_DOMAIN}>",
                    "to": recipient_emails,
                    "subject": f"Notice: {notice.title}",
                    "html": html_message,
                    "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
                })
                return f"Successfully sent notice {notice_id} to {len(recipient_emails)} recipients via Resend"
            except Exception as e:
                print(f"[v0] Resend error, falling back to Django backend: {e}")
                # Fallback to Django backend
                return send_via_django(notice.title, html_message, recipient_emails, is_notice=True)
        else:
            # Development/localhost: use Django console/file backend
            return send_via_django(notice.title, html_message, recipient_emails, is_notice=True)
    
    except Notice.DoesNotExist:
        return f"Notice {notice_id} not found"
    except Exception as e:
        print(f"[v0] Error sending notice emails: {e}")
        return f"Error sending notice emails: {str(e)}"


@shared_task
def send_announcement_email(announcement_id):
    """Send announcement emails to recipients asynchronously via Resend or fallback"""
    import logging
    logger = logging.getLogger(__name__)
    try:
        announcement = Announcement.objects.get(id=announcement_id)
        recipients = get_announcement_recipients(announcement)
        
        recipient_emails = [user.email for user in recipients if user.email]
        logger.info(f"[ANNOUNCEMENT {announcement_id}] Found {len(recipients)} recipients, {len(recipient_emails)} with emails: {recipient_emails[:5]}{'...' if len(recipient_emails)>5 else ''}")
        
        if not recipients:
            logger.warning(f"[ANNOUNCEMENT {announcement_id}] No recipients found")
            return f"No recipients for announcement {announcement_id}"
        
        if not recipient_emails:
            logger.warning(f"[ANNOUNCEMENT {announcement_id}] No valid emails found")
            return f"No valid email addresses for announcement {announcement_id}"
        
        recipient_emails = [user.email for user in recipients if user.email]
        
        if not recipient_emails:
            return f"No valid email addresses for announcement {announcement_id}"
        
        context = {
            'title': announcement.title,
            'content': announcement.content,
            'created_by': announcement.created_by.get_full_name() if announcement.created_by else 'School Admin',
            'school_name': announcement.school.name,
            'logo_url': announcement.school.get_logo_url(),
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:3000'),
            'priority': announcement.priority,
        }
        
        html_message = render_to_string('emails/announcement.html', context)
        
        # Use Resend if API key exists and not localhost, otherwise use Django backend
        if resend and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
            try:
                email_response = resend.Emails.send({
                    "from": f"School Management <announcements@{RESEND_DOMAIN}>",
                    "to": recipient_emails,
                    "subject": f"Announcement: {announcement.title}",
                    "html": html_message,
                    "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
                })
                return f"Successfully sent announcement {announcement_id} to {len(recipient_emails)} recipients via Resend"
            except Exception as e:
                print(f"[v0] Resend error, falling back to Django backend: {e}")
                return send_via_django(announcement.title, html_message, recipient_emails, is_announcement=True)
        else:
            return send_via_django(announcement.title, html_message, recipient_emails, is_announcement=True)
    
    except Announcement.DoesNotExist:
        return f"Announcement {announcement_id} not found"
    except Exception as e:
        print(f"[v0] Error sending announcement emails: {e}")
        return f"Error sending announcement emails: {str(e)}"


@shared_task
def send_assignment_email(assignment_id):
    """Send new assignment notification to all students in the class via Resend or fallback."""
    try:
        assignment = Assignment.objects.select_related(
            'class_obj__school', 
            'subject', 
            'teacher'
        ).get(id=assignment_id)
        
        # Get all students in the class via StudentClass
        student_classes = StudentClass.objects.filter(
            class_obj=assignment.class_obj,
            is_active=True
        ).select_related('student')
        
        recipients = [sc.student for sc in student_classes if sc.student.is_active]
        recipient_emails = [student.email for student in recipients if student.email]
        
        if not recipient_emails:
            return f"No active student emails found for assignment {assignment_id}"
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        school = assignment.class_obj.school
        context = {
            'title': assignment.title,
            'description': assignment.description or 'No description provided.',
            'due_date': assignment.due_date,
            'class_name': assignment.class_obj.name,
            'subject_name': assignment.subject.name,
            'teacher_name': assignment.teacher.get_full_name(),
            'school_name': school.name,
            'logo_url': school.get_logo_url() if hasattr(school, 'get_logo_url') else '',
            'frontend_url': frontend_url,
            'assignment_link': f"{frontend_url}/dashboard/student/assignments",
        }
        
        html_message = render_to_string('emails/assignment.html', context)
        subject = f"New Assignment: {assignment.title} - Due {assignment.due_date.strftime('%Y-%m-%d %H:%M')}"
        
        # Use same Resend/console logic
        if resend and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
            try:
                email_response = resend.Emails.send({
                    "from": f"School Management <assignments@{RESEND_DOMAIN}>",
                    "to": recipient_emails,
                    "subject": subject,
                    "html": html_message,
                    "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
                })
                return f"Assignment email sent to {len(recipient_emails)} students via Resend"
            except Exception as e:
                print(f"[Assignment] Resend error, fallback: {e}")
                return send_via_django(subject, html_message, recipient_emails, is_assignment=True)
        else:
            return send_via_django(subject, html_message, recipient_emails, is_assignment=True)
    
    except Assignment.DoesNotExist:
        return f"Assignment {assignment_id} not found"
    except Exception as e:
        print(f"[Assignment Email] Error: {e}")
        return f"Error sending assignment email: {str(e)}"


@shared_task
def send_assignment_submission_email(submission_id):
    """Send an email to a student when their assignment has been marked
    as submitted (typically by a teacher)."""
    try:
        from apps.assignments.models import AssignmentSubmission

        submission = AssignmentSubmission.objects.select_related(
            'assignment__class_obj__school',
            'assignment__subject',
            'assignment__teacher',
            'student',
        ).get(id=submission_id)

        student = submission.student
        if not student.email:
            return f"No email for student {student.id} on submission {submission_id}"

        assignment = submission.assignment
        school = assignment.class_obj.school
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')

        context = {
            'title': assignment.title,
            'description': assignment.description or 'No description provided.',
            'due_date': assignment.due_date,
            'class_name': assignment.class_obj.name,
            'subject_name': assignment.subject.name,
            'teacher_name': assignment.teacher.get_full_name() if assignment.teacher_id else 'Your teacher',
            'student_name': student.get_full_name() or student.username,
            'school_name': school.name,
            'logo_url': school.get_logo_url() if hasattr(school, 'get_logo_url') else '',
            'frontend_url': frontend_url,
            'assignment_link': f"{frontend_url}/dashboard/student/assignments",
        }

        html_message = render_to_string('emails/assignment_submitted.html', context)
        subject = f'Assignment Submitted: {assignment.title}'
        recipient_emails = [student.email]

        if resend and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
            try:
                resend.Emails.send({
                    "from": f"School Management <assignments@{RESEND_DOMAIN}>",
                    "to": recipient_emails,
                    "subject": subject,
                    "html": html_message,
                    "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
                })
                return f"Submission email sent to {student.email} via Resend"
            except Exception as e:
                print(f"[Submission] Resend error, fallback: {e}")
                return send_via_django(subject, html_message, recipient_emails, is_assignment=True)
        else:
            return send_via_django(subject, html_message, recipient_emails, is_assignment=True)

    except AssignmentSubmission.DoesNotExist:
        return f"AssignmentSubmission {submission_id} not found"
    except Exception as e:
        print(f"[Submission Email] Error: {e}")
        return f"Error sending submission email: {str(e)}"


@shared_task
def send_realtime_notification(notification_type, user_id, title, message, data=None):
    """
    Send real-time notification via Redis pub/sub
    """
    try:
        success = notification_service.send_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data or {}
        )
        return f"Notification sent: {success}"
    except Exception as e:
        return f"Error sending notification: {str(e)}"


@shared_task
def broadcast_school_notification(school_id, notification_type, title, message, data=None):
    """
    Broadcast notification to all users in a school
    """
    try:
        success = notification_service.send_school_notification(
            school_id=school_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data or {}
        )
        return f"School notification broadcast: {success}"
    except Exception as e:
        return f"Error broadcasting notification: {str(e)}"


def send_via_django(subject, html_message, recipient_emails, is_notice=False, is_announcement=False, is_assignment=False, is_personal_notice=False):
    """
    Console email backend for development/localhost testing.
    """
    try:
        plain_message = strip_tags(html_message)
        sender = "School Management <noreply@schoolmanagement.edu>"
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=sender,
            to=recipient_emails,
        )
        email.attach_alternative(html_message, "text/html")
        
        console_backend = ConsoleEmailBackend()
        result = console_backend.send_messages([email])
        
        email_type = "personal_notice" if is_personal_notice else "notice" if is_notice else "announcement" if is_announcement else "assignment" if is_assignment else "email"
        print(f"\n{'='*80}")
        print(f"[v0] EMAIL SENT TO {len(recipient_emails)} RECIPIENTS ({email_type.upper()})")
        print(f"{'='*80}")
        print(f"Subject: {subject}")
        print(f"Recipients: {', '.join(recipient_emails[:3])}{'...' if len(recipient_emails) > 3 else ''}")
        print(f"{'='*80}\n")
        
        return f"Successfully sent {email_type} to {len(recipient_emails)} recipients via console backend"
    except Exception as e:
        print(f"[v0] Console email backend error: {e}")
        import traceback
        traceback.print_exc()
        return f"Error sending via console backend: {str(e)}"


def get_notice_recipients(notice):
    """Get list of users who should receive the notice"""
    recipients = set()
    school = notice.school
    
    if notice.send_to_all:
        recipients = set(User.objects.filter(school=school, is_active=True))
    else:
        if notice.send_to_teachers:
            teachers = User.objects.filter(school=school, role='teacher', is_active=True)
            recipients.update(teachers)
        
        if notice.send_to_students:
            students = User.objects.filter(school=school, role='student', is_active=True)
            recipients.update(students)
    
    return list(recipients)


def get_announcement_recipients(announcement):
    """Get list of users who should receive the announcement"""
    recipients = set()
    school = announcement.school
    
    if announcement.send_to_all:
        recipients = set(User.objects.filter(school=school, is_active=True))
    else:
        # Send to teachers
        if announcement.send_to_teachers:
            teachers = User.objects.filter(school=school, role='teacher', is_active=True)
            recipients.update(teachers)
        
        # Send to students
        if announcement.send_to_students:
            if announcement.classes.exists():
                # Send to students in specified classes
                classes_qs = announcement.classes.all()
                student_classes = StudentClass.objects.filter(
                    class_obj__in=classes_qs,
                    is_active=True
                ).select_related('student')
                students = [sc.student for sc in student_classes if sc.student.is_active]
                recipients.update(students)
            else:
                # Send to all students in school
                students = User.objects.filter(school=school, role='student', is_active=True)
                recipients.update(students)
    
    return list(recipients)


@shared_task
def send_personal_notice_email(personal_notice_id):
    """Send personal notice email to individual student via Resend or fallback"""
    try:
        personal_notice = PersonalNotice.objects.get(id=personal_notice_id)
        student = personal_notice.student
        
        if not student.email:
            return f"No email for student {personal_notice.student.id}"
        
        context = {
            'title': personal_notice.title,
            'content': personal_notice.content,
            'student_name': student.get_full_name(),
            'created_by': personal_notice.created_by.get_full_name() if personal_notice.created_by else 'School Admin',
            'school_name': personal_notice.school.name,
            'logo_url': personal_notice.school.get_logo_url(),
            'priority': 'personal',
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:3000'),
            'created_at': personal_notice.sent_at,
        }
        
        html_message = render_to_string('emails/announcement.html', context)
        subject = f"Personal Notice: {personal_notice.title}"
        recipient_emails = [student.email]
        
        # Use Resend if available and not development, fallback to Django console
        if resend and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
            try:
                email_response = resend.Emails.send({
                    "from": f"School Management <personal@{RESEND_DOMAIN}>",
                    "to": recipient_emails,
                    "subject": subject,
                    "html": html_message,
                    "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
                })
                print(f"[PERSONAL NOTICE] Sent to {student.email} via Resend")
                # Send realtime notification
                notification_service.send_notification(
                    user_id=student.id,
                    notification_type='personal_notice',
                    title=personal_notice.title,
                    message=personal_notice.content[:100] + '...',
                    data={'notice_id': personal_notice.id}
                )
                return f"Personal notice sent to {student.email}"
            except Exception as e:
                print(f"[PERSONAL] Resend error, fallback: {e}")
                return send_via_django(subject, html_message, recipient_emails, is_personal_notice=True)
        else:
            result = send_via_django(subject, html_message, recipient_emails, is_personal_notice=True)
            # Send realtime notification anyway
            notification_service.send_notification(
                user_id=student.id,
                notification_type='personal_notice',
                title=personal_notice.title,
                message=personal_notice.content[:100] + '...',
                data={'notice_id': personal_notice.id}
            )
            return result
    
    except PersonalNotice.DoesNotExist:
        return f"PersonalNotice {personal_notice_id} not found"
    except Exception as e:
        print(f"[PERSONAL NOTICE] Error: {e}")
        return f"Error sending personal notice: {str(e)}"
