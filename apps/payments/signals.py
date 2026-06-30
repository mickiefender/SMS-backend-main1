import logging
from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Payment, Notification, SchoolRevenue

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=Payment)
def handle_payment_success(sender, instance, created, **kwargs):
    """Handle all post-payment-success actions: update invoice, notify, email, track revenue."""
    if instance.status != 'success':
        return

    invoice = instance.invoice

    # --- 1. Recalculate invoice totals ---
    total_paid = Payment.objects.filter(
        invoice=invoice,
        status='success'
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')

    invoice.amount_paid = total_paid
    invoice.balance = invoice.total_amount - total_paid

    if total_paid >= invoice.total_amount:
        invoice.status = 'paid'
    elif total_paid > 0:
        invoice.status = 'partially_paid'

    invoice.save(update_fields=['amount_paid', 'balance', 'status', 'updated_at'])

    # --- 2. Create dashboard notification for school admins ---
    try:
        school_admins = User.objects.filter(
            school=instance.school,
            role__in=['school_admin', 'finance_officer'],
            is_active=True
        )
        for admin in school_admins:
            Notification.objects.create(
                school=instance.school,
                user=admin,
                title='Payment Received',
                message=(
                    f'₦{instance.amount} payment received from '
                    f'{instance.student.get_full_name()} for invoice '
                    f'{invoice.invoice_number}. '
                    f'Outstanding balance: ₦{invoice.balance}'
                ),
                notification_type='payment_received',
                related_payment=instance,
                metadata={
                    'payment_id': str(instance.id),
                    'invoice_id': str(invoice.id),
                    'student_name': instance.student.get_full_name(),
                    'amount': str(instance.amount),
                    'balance': str(invoice.balance),
                }
            )
    except Exception as e:
        logger.error(f"Error creating payment notification: {e}")

    # --- 3. Create notification for the student ---
    try:
        Notification.objects.create(
            school=instance.school,
            user=instance.student,
            title='Payment Confirmed',
            message=(
                f'Your payment of ₦{instance.amount} for invoice '
                f'{invoice.invoice_number} has been confirmed. '
                f'Remaining balance: ₦{invoice.balance}'
            ),
            notification_type='payment_confirmed',
            related_payment=instance,
            metadata={
                'payment_id': str(instance.id),
                'invoice_id': str(invoice.id),
                'amount': str(instance.amount),
                'balance': str(invoice.balance),
            }
        )
    except Exception as e:
        logger.error(f"Error creating student payment notification: {e}")

    # --- 4. Send email notification to school (via Celery) ---
    try:
        from .tasks import send_payment_confirmed_email
        send_payment_confirmed_email.delay(str(instance.id))
    except Exception as e:
        logger.error(f"Error queuing payment confirmation email: {e}")

    # --- 5. Track revenue for the school ---
    try:
        revenue, _ = SchoolRevenue.objects.get_or_create(
            school=instance.school,
            defaults={
                'total_revenue': Decimal('0'),
                'total_withdrawn': Decimal('0'),
                'available_balance': Decimal('0'),
            }
        )
        revenue.add_revenue(instance.amount)
    except Exception as e:
        logger.error(f"Error updating school revenue: {e}")
