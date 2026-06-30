"""Celery tasks for payment notifications and OTP emails using Resend."""
import os
import logging

from celery import shared_task
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()

# Import Resend
try:
    import resend
    resend.api_key = os.environ.get("RESEND_API_KEY", "")
except ImportError:
    resend = None

IS_DEVELOPMENT = os.environ.get("DEBUG", "False") == "True" or os.environ.get("ENVIRONMENT") == "development"
RESEND_DOMAIN = os.environ.get("RESEND_DOMAIN", "localhost")


def _send_email(subject, html_message, recipient_emails, email_type="email"):
    """Send email via Resend (production) or console backend (development)."""
    if not recipient_emails:
        return f"No recipients for {email_type}"

    if resend and os.environ.get("RESEND_API_KEY") and not IS_DEVELOPMENT:
        try:
            email_response = resend.Emails.send({
                "from": f"payments@{RESEND_DOMAIN}",
                "to": recipient_emails,
                "subject": subject,
                "html": html_message,
                "reply_to": os.environ.get("REPLY_TO_EMAIL", "noreply@schoolmanagement.edu"),
            })
            return f"Successfully sent {email_type} to {len(recipient_emails)} recipients via Resend"
        except Exception as e:
            logger.error(f"Resend error, falling back to Django backend: {e}")

    # Fallback: Django console backend
    try:
        from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
        from django.core.mail import EmailMultiAlternatives

        console_backend = ConsoleEmailBackend()
        plain_message = strip_tags(html_message)
        sender = "School Management <noreply@schoolmanagement.edu>"

        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=sender,
            to=recipient_emails,
        )
        email.attach_alternative(html_message, "text/html")
        console_backend.send_messages([email])

        logger.info(f"[Payment Email] Sent {email_type} to {len(recipient_emails)} recipients via console backend")
        return f"Successfully sent {email_type} to {len(recipient_emails)} recipients via console backend"
    except Exception as e:
        logger.error(f"Console email backend error: {e}")
        return f"Error sending {email_type}: {str(e)}"


@shared_task
def send_payment_confirmed_email(payment_id):
    """Send payment confirmation email to school admin(s) when a payment is confirmed."""
    try:
        from .models import Payment

        payment = Payment.objects.select_related(
            'student', 'school', 'invoice'
        ).get(id=payment_id)

        # Get school admin emails
        school_admins = User.objects.filter(
            school=payment.school,
            role__in=['school_admin', 'finance_officer'],
            is_active=True
        )
        admin_emails = [admin.email for admin in school_admins if admin.email]

        if not admin_emails:
            return f"No admin emails found for school {payment.school.name}"

        # Build context for each admin
        for admin in school_admins:
            if not admin.email:
                continue

            context = {
                'recipient_name': admin.get_full_name() or 'Admin',
                'school_name': payment.school.name,
                'student_name': payment.student.get_full_name(),
                'invoice_number': payment.invoice.invoice_number,
                'transaction_reference': payment.transaction_reference,
                'payment_method': payment.get_payment_method_display(),
                'amount': str(payment.amount),
                'balance': str(payment.invoice.balance),
                'payment_date': payment.created_at.strftime('%B %d, %Y at %I:%M %p'),
            }

            html_message = render_to_string('emails/payment_confirmed_email.html', context)

            _send_email(
                subject=f"Payment Confirmed: ₦{payment.amount} from {payment.student.get_full_name()}",
                html_message=html_message,
                recipient_emails=[admin.email],
                email_type="payment_confirmation"
            )

        return f"Payment confirmation emails sent for payment {payment_id}"

    except Exception as e:
        logger.error(f"Error sending payment confirmation email: {e}")
        return f"Error: {str(e)}"


@shared_task
def send_withdrawal_otp_email(withdrawal_id):
    """Send OTP email to school's email address for withdrawal verification."""
    try:
        from .models import WithdrawalRequest

        withdrawal = WithdrawalRequest.objects.select_related(
            'school', 'requested_by', 'bank_account'
        ).get(id=withdrawal_id)

        # Send OTP to the school's email address
        school_email = withdrawal.school.email
        if not school_email:
            return f"No email found for school {withdrawal.school.name}"

        method_display = 'Bank Transfer' if withdrawal.withdrawal_method == 'bank' else 'Mobile Money'

        context = {
            'recipient_name': withdrawal.requested_by.get_full_name() or 'Admin',
            'school_name': withdrawal.school.name,
            'otp_code': withdrawal.otp_code,
            'amount': str(withdrawal.amount),
            'withdrawal_method': method_display,
            'account_name': withdrawal.bank_account.account_name if withdrawal.bank_account else 'N/A',
            'bank_name': withdrawal.bank_account.bank_name if withdrawal.bank_account else 'N/A',
            'account_number': withdrawal.bank_account.account_number if withdrawal.bank_account else 'N/A',
            'requested_by': withdrawal.requested_by.get_full_name(),
        }

        html_message = render_to_string('emails/withdrawal_otp_email.html', context)

        result = _send_email(
            subject=f"Withdrawal Verification OTP - {withdrawal.school.name}",
            html_message=html_message,
            recipient_emails=[school_email],
            email_type="withdrawal_otp"
        )

        return result

    except Exception as e:
        logger.error(f"Error sending withdrawal OTP email: {e}")
        return f"Error: {str(e)}"
