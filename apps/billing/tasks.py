"""Celery tasks for billing notifications (fee payments)."""
import os
import logging
from celery import shared_task
from celery.schedules import crontab
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Sum, Count, Avg
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

        logger.info(f"[Billing Email] Sent {email_type} to {len(recipient_emails)} recipients via console backend")
        return f"Successfully sent {email_type} to {len(recipient_emails)} recipients via console backend"
    except Exception as e:
        logger.error(f"Console email backend error: {e}")
        return f"Error sending {email_type}: {str(e)}"


def strip_tags(html):
    """Strip HTML tags from string"""
    import re
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html)


@shared_task
def send_fee_payment_email(payment_id):
    """Send fee payment confirmation email to student when a manual payment is recorded."""
    try:
        from apps.billing.models import ManualPayment

        payment = ManualPayment.objects.select_related(
            'student', 'school', 'fee_assignment', 'fee_assignment__fee', 'recorded_by'
        ).get(id=payment_id)

        # Get student email
        student_email = payment.student.email
        if not student_email:
            return f"No email found for student {payment.student.get_full_name()}"

        # Calculate balance after payment
        fee_assignment = payment.fee_assignment
        new_balance = float(fee_assignment.amount) - float(fee_assignment.amount_paid)
        
        # Format payment method for display
        payment_method_display = payment.get_payment_method_display()

        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        context = {
            'recipient_name': payment.student.get_full_name() or 'Student',
            'school_name': payment.school.name,
            'student_name': payment.student.get_full_name(),
            'fee_name': fee_assignment.fee.name,
            'amount_paid': str(payment.amount),
            'total_amount': str(fee_assignment.amount),
            'amount_paid_total': str(fee_assignment.amount_paid),
            'balance': str(max(0, new_balance)),
            'receipt_number': payment.receipt_number,
            'payment_method': payment_method_display,
            'payment_date': payment.payment_date.strftime('%B %d, %Y at %I:%M %p'),
            'recorded_by': payment.recorded_by.get_full_name() if payment.recorded_by else 'School Admin',
            'notes': payment.notes or '',
            'is_paid': fee_assignment.status == 'paid',
            'logo_url': payment.school.get_logo_url() if hasattr(payment.school, 'get_logo_url') else '',
            'frontend_url': frontend_url,
            'fee_link': f"{frontend_url}/dashboard/student/fees",
            'email_heading': 'Manual Fee Update Confirmation',
            'email_intro': 'A manual fee payment update has been recorded on your student account. Please review the details below for your records.',
        }

        html_message = render_to_string('emails/fee_payment_confirmation.html', context)

        _send_email(
            subject=f"Payment Received - {payment.school.name} - {fee_assignment.fee.name}",
            html_message=html_message,
            recipient_emails=[student_email],
            email_type="fee_payment_confirmation"
        )

        return f"Fee payment confirmation email sent for payment {payment_id}"

    except Exception as e:
        logger.error(f"Error sending fee payment confirmation email: {e}")
        return f"Error: {str(e)}"


@shared_task
def send_online_payment_email(payment_id):
    """
    Send fee payment confirmation email to BOTH student AND school admin 
    when an online payment is made via Paystack.
    """
    try:
        from apps.billing.models import OnlinePayment
        from django.contrib.auth import get_user_model
        User = get_user_model()

        payment = OnlinePayment.objects.select_related(
            'student', 'school', 'fee_assignment', 'fee_assignment__fee'
        ).get(id=payment_id)

        # Get student email
        student_email = payment.student.email
        if not student_email:
            return f"No email found for student {payment.student.get_full_name()}"

        # Calculate balance after payment (if fee_assignment exists)
        fee_assignment = payment.fee_assignment
        new_balance = 0
        fee_name = "School Fee"
        total_amount = payment.amount
        amount_paid_total = payment.amount
        is_paid = True
        
        if fee_assignment:
            new_balance = float(fee_assignment.amount) - float(fee_assignment.amount_paid)
            fee_name = fee_assignment.fee.name
            total_amount = fee_assignment.amount
            amount_paid_total = fee_assignment.amount_paid
            is_paid = fee_assignment.status == 'paid'

        # Prepare context for student email
        student_context = {
            'recipient_name': payment.student.get_full_name() or 'Student',
            'school_name': payment.school.name,
            'student_name': payment.student.get_full_name(),
            'fee_name': fee_name,
            'amount_paid': str(payment.amount),
            'total_amount': str(total_amount),
            'amount_paid_total': str(amount_paid_total),
            'balance': str(max(0, new_balance)),
            'receipt_number': payment.receipt_number,
            'payment_method': 'Paystack (' + (payment.channel or 'Online') + ')',
            'payment_date': payment.paid_at.strftime('%B %d, %Y at %I:%M %p') if payment.paid_at else 'N/A',
            'recorded_by': 'Online Payment',
            'notes': payment.notes or '',
            'is_paid': is_paid,
            'reference': payment.reference,
        }

        student_html_message = render_to_string('emails/fee_payment_confirmation.html', student_context)

        # Send email to student
        _send_email(
            subject=f"Payment Received - {payment.school.name} - {fee_name}",
            html_message=student_html_message,
            recipient_emails=[student_email],
            email_type="online_payment_student"
        )

        # Get school admin emails
        school_admin_emails = list(User.objects.filter(
            school=payment.school,
            role='school_admin',
            email__isnull=False
        ).values_list('email', flat=True))

        if school_admin_emails:
            # Prepare context for school admin
            admin_context = {
                'recipient_name': 'School Admin',
                'school_name': payment.school.name,
                'student_name': payment.student.get_full_name(),
                'fee_name': fee_name,
                'amount_paid': str(payment.amount),
                'total_amount': str(total_amount),
                'amount_paid_total': str(amount_paid_total),
                'balance': str(max(0, new_balance)),
                'receipt_number': payment.receipt_number,
                'payment_method': 'Paystack (' + (payment.channel or 'Online') + ')',
                'payment_date': payment.paid_at.strftime('%B %d, %Y at %I:%M %p') if payment.paid_at else 'N/A',
                'recorded_by': 'Online Payment',
                'notes': payment.notes or '',
                'is_paid': is_paid,
                'reference': payment.reference,
            }

            admin_html_message = render_to_string('emails/fee_payment_confirmation.html', admin_context)

            # Send email to school admins
            _send_email(
                subject=f"New Online Payment - {payment.student.get_full_name()} - {payment.school.name} - {fee_name}",
                html_message=admin_html_message,
                recipient_emails=school_admin_emails,
                email_type="online_payment_admin"
            )
            
            return f"Online payment confirmation emails sent to student and {len(school_admin_emails)} school admin(s) for payment {payment_id}"
        
        return f"Online payment confirmation email sent to student for payment {payment_id}"

    except Exception as e:
        logger.error(f"Error sending online payment confirmation email: {e}")
        return f"Error: {str(e)}"


@shared_task
def send_bulk_fee_assignment_email(fee_assignment_ids):
    """Send bulk fee assignment notification to students (for school/class bulk assigns)."""
    try:
        from apps.billing.models import StudentFeeAssignment
        
        assignments = StudentFeeAssignment.objects.filter(
            id__in=fee_assignment_ids
        ).select_related('student', 'school', 'fee')
        
        if not assignments.exists():
            return f"No fee assignments found for IDs {fee_assignment_ids}"
        
        # Group by school/fee for bulk send per school
        from collections import defaultdict
        school_emails = defaultdict(list)
        
        for assignment in assignments:
            if assignment.student.email:
                key = f"{assignment.school.id}_{assignment.fee.id}"
                school_emails[key].append(assignment.student.email)
        
        results = []
        for key, emails in school_emails.items():
            school_id, fee_id = key.split('_')
            sample_assignment = assignments.filter(school_id=school_id, fee_id=fee_id).first()
            
            context = {
                'fee_name': sample_assignment.fee.name,
                'amount': str(sample_assignment.amount),
                'due_date': sample_assignment.due_date,
                'students_count': len(emails),
                'school_name': sample_assignment.school.name,
                'logo_url': sample_assignment.school.logo_url,
                'frontend_url': 'http://localhost:3000',  # From settings
            }
            
            html_message = render_to_string('emails/fee_bulk_assigned.html', context)
            
            result = _send_email(
                subject=f"New Fee Assigned to All Students - {sample_assignment.school.name} - {sample_assignment.fee.name}",
                html_message=html_message,
                recipient_emails=emails,
                email_type="bulk_fee_assignment"
            )
            results.append(result)
        
        return f"Bulk fee emails sent: {results}"
    
    except Exception as e:
        logger.error(f"Bulk fee email error: {e}")
        return f"Error: {str(e)}"


@shared_task
def send_fee_update_email(fee_assignment_id, update_type="created"):
    """Send fee update notification to student when a fee is assigned or updated."""
    try:
        from apps.billing.models import StudentFeeAssignment

        fee_assignment = StudentFeeAssignment.objects.select_related(
            'student', 'school', 'fee'
        ).get(id=fee_assignment_id)

        # Get student email
        student_email = fee_assignment.student.email
        if not student_email:
            return f"No email found for student {fee_assignment.student.get_full_name()}"

        context = {
            'recipient_name': fee_assignment.student.get_full_name() or 'Student',
            'school_name': fee_assignment.school.name,
            'student_name': fee_assignment.student.get_full_name(),
            'fee_name': fee_assignment.fee.name,
            'amount': str(fee_assignment.amount),
            'amount_paid': str(fee_assignment.amount_paid),
            'balance': str(fee_assignment.balance),
            'due_date': fee_assignment.due_date.strftime('%B %d, %Y'),
            'status': fee_assignment.status,
            'update_type': update_type,
        }

        if update_type == "created":
            subject = f"New Fee Assigned - {fee_assignment.school.name} - {fee_assignment.fee.name}"
            template = 'emails/fee_assigned.html'
        else:
            subject = f"Fee Updated - {fee_assignment.school.name} - {fee_assignment.fee.name}"
            template = 'emails/fee_updated.html'

        html_message = render_to_string(template, context)

        _send_email(
            subject=subject,
            html_message=html_message,
            recipient_emails=[student_email],
            email_type=f"fee_{update_type}"
        )

        return f"Fee {update_type} email sent for fee assignment {fee_assignment_id}"

    except Exception as e:
        logger.error(f"Error sending fee update email: {e}")
        return f"Error: {str(e)}"


# ==================== ANALYTICS & REPORT GENERATION TASKS ====================

@shared_task
def generate_school_analytics_report(school_id, report_type='daily'):
    """
    Generate analytics report for a school
    
    Args:
        school_id: The school ID
        report_type: Type of report ('daily', 'weekly', 'monthly')
    """
    try:
        from apps.billing.models import ManualPayment
        from apps.attendance.models import Attendance
        from apps.academics.models import ExamResult
        
        now = timezone.now()
        
        # Calculate date range
        if report_type == 'daily':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif report_type == 'weekly':
            start_date = now - timezone.timedelta(days=7)
        elif report_type == 'monthly':
            start_date = now - timezone.timedelta(days=30)
        else:
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Revenue in period
        revenue_data = ManualPayment.objects.filter(
            school_id=school_id,
            payment_date__gte=start_date
        ).aggregate(
            total_amount=Sum('amount'),
            payment_count=Count('id')
        )
        
        # Attendance stats
        attendance_data = Attendance.objects.filter(
            class_obj__school_id=school_id,
            date__gte=start_date
        ).values('status').annotate(count=Count('id'))
        
        # Build report
        report = {
            'school_id': school_id,
            'report_type': report_type,
            'period_start': start_date.isoformat(),
            'period_end': now.isoformat(),
            'revenue': {
                'total': float(revenue_data['total_amount'] or 0),
                'payment_count': revenue_data['payment_count'] or 0,
            },
            'attendance': {
                stat['status']: stat['count'] 
                for stat in attendance_data
            },
            'generated_at': now.isoformat(),
        }
        
        # Cache the report
        from core.cache import ActivityCache
        cache_key = f"analytics:{school_id}:{report_type}"
        try:
            from django.core.cache import cache
            cache.set(cache_key, report, 3600)  # Cache for 1 hour
        except Exception as e:
            logger.warning(f"Failed to cache analytics report: {e}")
        
        return report
        
    except Exception as e:
        logger.error(f"Error generating analytics report: {e}")
        return {'error': str(e)}


@shared_task
def generate_all_schools_monthly_report():
    """Generate monthly report for all active schools"""
    from apps.schools.models import School
    
    schools = School.objects.filter(status='active')
    results = []
    
    for school in schools:
        result = generate_school_analytics_report.delay(school.id, 'monthly')
        results.append({
            'school_id': school.id,
            'school_name': school.name,
            'task_id': result.id
        })
    
    return f"Queued monthly reports for {len(results)} schools"


@shared_task
def cleanup_old_sessions():
    """Clean up expired sessions and cache"""
    try:
        from django.contrib.sessions.models import Session
        from django.core.cache import cache
        
        # Delete expired sessions
        expired_count = Session.objects.filter(expire_date__lt=timezone.now()).delete()[0]
        
        # Clear old cache entries (if using redis)
        try:
            cache.clear()
        except Exception:
            pass
        
        return f"Cleaned up {expired_count} expired sessions"
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {e}")
        return f"Error: {str(e)}"


@shared_task
def send_daily_digest_emails():
    """Send daily digest emails to school admins"""
    from apps.schools.models import School
    from apps.billing.models import ManualPayment
    from apps.attendance.models import Attendance
    
    schools = School.objects.filter(status='active')
    today = timezone.now().date()
    
    for school in schools:
        # Get today's stats
        payments_today = ManualPayment.objects.filter(
            school=school,
            payment_date__date=today
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        attendance_today = Attendance.objects.filter(
            class_obj__school=school,
            date=today
        ).values('status').annotate(count=Count('id'))
        
        # Get school admin emails
        admin_users = User.objects.filter(
            school=school,
            role='school_admin',
            email__isnull=False
        ).values_list('email', flat=True)
        
        if admin_users:
            context = {
                'school_name': school.name,
                'date': today.strftime('%B %d, %Y'),
                'payments': {
                    'total': float(payments_today['total'] or 0),
                    'count': payments_today['count'] or 0,
                },
                'attendance': {
                    stat['status']: stat['count'] 
                    for stat in attendance_today
                },
            }
            
            # Send email (using existing email function)
            try:
                html_message = render_to_string('emails/daily_digest.html', context)
                _send_email(
                    subject=f"Daily Digest - {school.name} - {today.strftime('%B %d, %Y')}",
                    html_message=html_message,
                    recipient_emails=list(admin_users),
                    email_type="daily_digest"
                )
            except Exception as e:
                logger.error(f"Error sending daily digest to {school.name}: {e}")
    
    return f"Daily digest emails sent to {schools.count()} schools"


@shared_task
def send_fee_reminder_emails():
    """Send reminder emails for upcoming fee due dates"""
    from apps.billing.models import StudentFeeAssignment
    
    tomorrow = timezone.now().date() + timezone.timedelta(days=1)
    next_week = timezone.now().date() + timezone.timedelta(days=7)
    
    # Get fees due tomorrow
    fees_due_tomorrow = StudentFeeAssignment.objects.filter(
        due_date=tomorrow,
        status__in=['pending', 'partial']
    ).select_related('student', 'school', 'fee')
    
    # Get fees due next week
    fees_due_next_week = StudentFeeAssignment.objects.filter(
        due_date=next_week,
        status__in=['pending', 'partial']
    ).select_related('student', 'school', 'fee')
    
    sent_count = 0
    
    # Send reminders for tomorrow
    for fee in fees_due_tomorrow:
        if fee.student.email:
            context = {
                'recipient_name': fee.student.get_full_name() or 'Student',
                'school_name': fee.school.name,
                'fee_name': fee.fee.name,
                'amount': str(fee.balance),
                'due_date': fee.due_date.strftime('%B %d, %Y'),
                'days_until_due': '1',
            }
            
            try:
                html_message = render_to_string('emails/fee_reminder.html', context)
                _send_email(
                    subject=f"Fee Due Tomorrow - {fee.school.name}",
                    html_message=html_message,
                    recipient_emails=[fee.student.email],
                    email_type="fee_reminder"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Error sending fee reminder: {e}")
    
    return f"Fee reminder emails sent to {sent_count} students"


# ==================== CELERY BEAT SCHEDULE ====================

# Add these to your Celery beat schedule
CELERY_BEAT_SCHEDULE = {
    'cleanup-old-sessions': {
        'task': 'apps.billing.tasks.cleanup_old_sessions',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'send-daily-digest': {
        'task': 'apps.billing.tasks.send_daily_digest_emails',
        'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM
    },
    'send-fee-reminders': {
        'task': 'apps.billing.tasks.send_fee_reminder_emails',
        'schedule': crontab(hour=8, minute=0),  # Daily at 8 AM
    },
    'generate-monthly-reports': {
        'task': 'apps.billing.tasks.generate_all_schools_monthly_report',
        'schedule': crontab(day_of_month=1, hour=3, minute=0),  # First of month at 3 AM
    },
}

