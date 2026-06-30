"""Academic document email notification tasks."""
import os
from celery import shared_task
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.conf import settings

from apps.academics.models import Document, StudentClass

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


def send_via_django(subject, html_message, recipient_emails, email_type="document_shared"):
    """Fallback console email backend for development."""
    try:
        plain_message = strip_tags(html_message)
        sender = f"School Management <documents@{RESEND_DOMAIN}>"
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=sender,
            to=recipient_emails,
        )
        email.attach_alternative(html_message, "text/html")
        console_backend = ConsoleEmailBackend()
        console_backend.send_messages([email])
        return f"Sent {email_type} to {len(recipient_emails)} via console"
    except Exception as e:
        return f"Console error: {str(e)}"


@shared_task
def send_document_shared_email(document_id, class_ids):
    """
    Send document shared notification to all active students in the selected classes.
    """
    try:
        document = Document.objects.select_related(
            "school", "uploaded_by", "related_subject", "related_class"
        ).get(id=document_id)

        student_classes = StudentClass.objects.select_related("student", "class_obj").filter(
            class_obj_id__in=class_ids,
            is_active=True
        )

        recipients = {}
        for sc in student_classes:
            student = sc.student
            if student and student.is_active and student.email:
                recipients[student.email] = student

        if not recipients:
            return f"No active student emails found for document {document_id}"

        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        context = {
            "school_name": document.school.name,
            "logo_url": document.school.get_logo_url() if hasattr(document.school, "get_logo_url") else "",
            "document_title": document.title,
            "document_description": document.description or "A new learning document has been shared with your class.",
            "document_type": getattr(document, "document_type", "Material"),
            "subject_name": document.related_subject.name if document.related_subject else "General",
            "class_name": document.related_class.name if document.related_class else "Your Class",
            "uploaded_by": document.uploaded_by.get_full_name() if document.uploaded_by else "Teacher",
            "frontend_url": frontend_url,
            "documents_link": f"{frontend_url}/dashboard/student/documents",
        }

        html_message = render_to_string("emails/document_shared.html", context)
        subject = f"New Class Document Shared: {document.title}"

        recipient_emails = list(recipients.keys())

        if RESEND_AVAILABLE and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
            try:
                resend.Emails.send({
                    "from": f"School Management <documents@{RESEND_DOMAIN}>",
                    "to": recipient_emails,
                    "subject": subject,
                    "html": html_message,
                    "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
                })
                return f"Sent document shared email to {len(recipient_emails)} students via Resend"
            except Exception:
                return send_via_django(subject, html_message, recipient_emails)

        return send_via_django(subject, html_message, recipient_emails)

    except Document.DoesNotExist:
        return f"Document {document_id} not found"
    except Exception as e:
        return f"Error sending document shared email: {str(e)}"
