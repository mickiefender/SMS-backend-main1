"""Attendance email notification tasks using existing email infrastructure"""
from celery import shared_task
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.conf import settings
import os

from apps.attendance.models import Attendance
from apps.schools.models import School

# Import Resend conditionally
try:
    import resend
    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    resend = None

IS_DEVELOPMENT = os.environ.get("DEBUG", "False") == "True" or os.environ.get("ENVIRONMENT") == "development"
RESEND_DOMAIN = os.environ.get("RESEND_DOMAIN", "localhost")


def send_via_django(subject, html_message, recipient_emails, email_type="attendance"):
    """Fallback console email backend for development"""
    try:
        plain_message = strip_tags(html_message)
        sender = f"School Management <attendance@{RESEND_DOMAIN}>"
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=sender,
            to=recipient_emails,
        )
        email.attach_alternative(html_message, "text/html")
        console_backend = ConsoleEmailBackend()
        console_backend.send_messages([email])
        print(f"\n{'='*80}")
        print(f"[ATTENDANCE EMAIL] Sent to {len(recipient_emails)} students ({email_type})")
        print(f"Subject: {subject}")
        print(f"{'='*80}\n")
        return f"Sent {email_type} to {len(recipient_emails)} via console"
    except Exception as e:
        print(f"[ATTENDANCE] Console error: {e}")
        return f"Console error: {str(e)}"


@shared_task
def send_attendance_marked_email(attendance_ids):
    """
    Send attendance confirmation emails to students for marked attendances.
    attendance_ids: list of Attendance PKs
    """
    try:
        attendances = Attendance.objects.select_related(
            'student', 'class_obj__school', 'subject', 'teacher'
        ).filter(id__in=attendance_ids)
        
        if not attendances.exists():
            return "No attendances found"
        
        school = attendances.first().class_obj.school
        results = []
        
        for attendance in attendances:
            student = attendance.student
            if not student.email:
                results.append(f"No email for {student.get_full_name()}")
                continue
            
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            context = {
                'subject': f"Attendance Marked - {attendance.status.upper()}",
                'school_name': school.name,
                'logo_url': school.get_logo_url() if hasattr(school, 'get_logo_url') else '',
                'student_name': student.get_full_name(),
                'status': attendance.get_status_display(),
                'status_lower': attendance.status,
                'class_name': attendance.class_obj.name,
                'subject_name': attendance.subject.name,
                'date': attendance.date.strftime('%B %d, %Y'),
                'teacher_name': attendance.teacher.get_full_name() if attendance.teacher else 'Admin',
                'remark': getattr(attendance, 'remark', ''),
                'frontend_url': frontend_url,
                'attendance_link': f"{frontend_url}/dashboard/student/attendance",
                'sender_name': attendance.teacher.get_full_name() if attendance.teacher else 'School Admin',
            }
            
            html_message = render_to_string('emails/attendance_marked.html', context)
            subject = f"Attendance Update: {attendance.status.title()} - {attendance.class_obj.name} - {attendance.subject.name}"
            recipient_emails = [student.email]
            
            # Try Resend first (prod)
            if RESEND_AVAILABLE and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
                try:
                    resend.Emails.send({
                        "from": f"Attendance <attendance@{RESEND_DOMAIN}>",
                        "to": recipient_emails,
                        "subject": subject,
                        "html": html_message,
                    })
                    results.append(f"Sent to {student.email} via Resend")
                except Exception as e:
                    print(f"[ATTENDANCE] Resend failed: {e}")
                    results.append(send_via_django(subject, html_message, recipient_emails))
            else:
                # Dev: console backend
                results.append(send_via_django(subject, html_message, recipient_emails))
        
        return f"Processed {len(attendance_ids)} attendances: {results}"
    
    except Exception as e:
        print(f"[ATTENDANCE TASK] Error: {e}")
        return f"Error: {str(e)}"

