from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from apps.students.models import StudentSocialClubMember


@receiver(post_save, sender=StudentSocialClubMember)
def send_membership_approval_email(sender, instance, created, **kwargs):
    """
    Asynchronously sends an email to a student when their social club membership is approved.
    """
    if not created and instance.status == 'active' and instance._previous_status == 'pending':
        subject = f"Your membership for {instance.club.name} has been approved"
        message = f"""
        Dear {instance.student.get_full_name()},

        Your membership for the social club, "{instance.club.name}", has been approved.

        You can now participate in the club's activities.

        Thank you,
        School Administration
        """
        send_mail(
            subject,
            message,
            'noreply@school.com',
            [instance.student.email],
            fail_silently=False,
        )

@receiver(post_save, sender=StudentSocialClubMember)
def cache_previous_status(sender, instance, **kwargs):
    instance._previous_status = instance.status
