from celery import shared_task
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

User = get_user_model()


@shared_task
def send_faculty_advisor_notification(club_id):
    """
    Asynchronously notifies the faculty advisor via email upon the creation of a new social club.
    """
    from apps.students.models import StudentSocialClub
    
    try:
        club = StudentSocialClub.objects.get(id=club_id)
        if club.faculty_advisor:
            subject = f"You have been assigned as the faculty advisor for {club.name}"
            message = f"""
            Dear {club.faculty_advisor.get_full_name()},

            You have been assigned as the faculty advisor for the newly created social club, "{club.name}".

            Club Details:
            - Name: {club.name}
            - Description: {club.description}

            Please log in to the school portal to view more details.

            Thank you,
            School Administration
            """
            send_mail(
                subject,
                message,
                'noreply@school.com',
                [club.faculty_advisor.email],
                fail_silently=False,
            )
    except StudentSocialClub.DoesNotExist:
        # Handle case where club might be deleted before task runs
        pass
