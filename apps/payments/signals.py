from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Payment


@receiver(post_save, sender=Payment)
def update_invoice_on_payment(sender, instance, created, **kwargs):
    """Update invoice status when a payment is saved."""
    if instance.status == 'success':
        invoice = instance.invoice
        # Recalculate total paid
        total_paid = Payment.objects.filter(
            invoice=invoice,
            status='success'
        ).aggregate(
            total=Sum('amount')
        )['total'] or 0

        invoice.amount_paid = total_paid
        invoice.balance = invoice.total_amount - total_paid

        if total_paid >= invoice.total_amount:
            invoice.status = 'paid'
        elif total_paid > 0:
            invoice.status = 'partially_paid'

        invoice.save(update_fields=['amount_paid', 'balance', 'status', 'updated_at'])
