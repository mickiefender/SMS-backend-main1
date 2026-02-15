"""Email notification tasks for Celery using Resend with localhost fallback"""
from celery import shared_task
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
from django.core.mail import send_mass_mail
import os
from apps.academics.models import Class, Enrollment
from .models import Notice, Announcement

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
            'priority': notice.get_priority_display(),
            'created_by': notice.created_by.get_full_name() if notice.created_by else 'School Admin',
            'school_name': notice.school.name,
        }
        
        html_message = render_to_string('emails/notice_email.html', context)
        
        # Use Resend if API key exists and not localhost, otherwise use Django backend
        if resend and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
            try:
                email_response = resend.Emails.send({
                    "from": f"notices@{RESEND_DOMAIN}",
                    "to": recipient_emails,
                    "subject": f"Notice: {notice.title}",
                    "html": html_message,
                    "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
                })
                return f"Successfully sent notice {notice_id} to {len(recipient_emails)} recipients via Resend"
            except Exception as e:
                print(f"[v0] Resend error, falling back to Django backend: {e}")
                # Fallback to Django backend
                return send_via_django(notice.title, html_message, recipient_emails)
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
    try:
        announcement = Announcement.objects.get(id=announcement_id)
        recipients = get_announcement_recipients(announcement)
        
        if not recipients:
            return f"No recipients for announcement {announcement_id}"
        
        recipient_emails = [user.email for user in recipients if user.email]
        
        if not recipient_emails:
            return f"No valid email addresses for announcement {announcement_id}"
        
        context = {
            'announcement_title': announcement.title,
            'announcement_content': announcement.content,
            'created_by': announcement.created_by.get_full_name() if announcement.created_by else 'School Admin',
            'school_name': announcement.school.name,
        }
        
        html_message = render_to_string('emails/announcement_email.html', context)
        
        # Use Resend if API key exists and not localhost, otherwise use Django backend
        if resend and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
            try:
                email_response = resend.Emails.send({
                    "from": f"announcements@{RESEND_DOMAIN}",
                    "to": recipient_emails,
                    "subject": f"Announcement: {announcement.title}",
                    "html": html_message,
                    "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
                })
                return f"Successfully sent announcement {announcement_id} to {len(recipient_emails)} recipients via Resend"
            except Exception as e:
                print(f"[v0] Resend error, falling back to Django backend: {e}")
                # Fallback to Django backend
                return send_via_django(announcement.title, html_message, recipient_emails)
        else:
            # Development/localhost: use Django console/file backend
            return send_via_django(announcement.title, html_message, recipient_emails, is_announcement=True)
    
    except Announcement.DoesNotExist:
        return f"Announcement {announcement_id} not found"
    except Exception as e:
        print(f"[v0] Error sending announcement emails: {e}")
        return f"Error sending announcement emails: {str(e)}"


def send_via_django(subject, html_message, recipient_emails, is_notice=False, is_announcement=False):
    """
    Console email backend for development/localhost testing.
    Prints emails to stdout/Celery worker console instead of sending via SMTP.
    """
    try:
        from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
        from django.core.mail import EmailMultiAlternatives
        
        # Use console backend directly to print emails
        console_backend = ConsoleEmailBackend()
        plain_message = strip_tags(html_message)
        sender = "School Management <noreply@schoolmanagement.edu>"
        
        # Create email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=sender,
            to=recipient_emails,
        )
        email.attach_alternative(html_message, "text/html")
        
        # Send via console backend (prints to stdout)
        result = console_backend.send_messages([email])
        
        email_type = "notice" if is_notice else "announcement" if is_announcement else "email"
        print(f"\n{'='*80}")
        print(f"[v0] EMAIL SENT TO {len(recipient_emails)} RECIPIENTS")
        print(f"{'='*80}")
        print(f"Subject: {subject}")
        print(f"Recipients: {', '.join(recipient_emails)}")
        print(f"Email Type: {email_type}")
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
        # Send to all users in school
        recipients = set(User.objects.filter(school=school, is_active=True))
    else:
        # Send to teachers
        if notice.send_to_teachers:
            teachers = User.objects.filter(
                school=school, 
                role='teacher',
                is_active=True
            )
            recipients.update(teachers)
        
        # Send to students
        if notice.send_to_students:
            students = User.objects.filter(
                school=school,
                role='student',
                is_active=True
            )
            recipients.update(students)
    
    return list(recipients)


def get_announcement_recipients(announcement):
    """Get list of users who should receive the announcement"""
    recipients = set()
    school = announcement.school
    
    if announcement.send_to_all:
        # Send to all users in school
        recipients = set(User.objects.filter(school=school, is_active=True))
    else:
        # Send to teachers
        if announcement.send_to_teachers:
            teachers = User.objects.filter(
                school=school,
                role='teacher',
                is_active=True
            )
            recipients.update(teachers)
        
        # Send to students in specific classes
        if announcement.send_to_students:
            if announcement.classes.exists():
                # Send to students in specified classes
                classes = announcement.classes.all()
                students = User.objects.filter(
                    school=school,
                    role='student',
                    is_active=True,
                    student_profile__enrollment__class__in=classes
                ).distinct()
            else:
                # Send to all students in school
                students = User.objects.filter(
                    school=school,
                    role='student',
                    is_active=True
                )
            recipients.update(students)
    
    return list(recipients)
