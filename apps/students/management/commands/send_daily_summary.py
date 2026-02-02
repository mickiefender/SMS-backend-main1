from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from apps.students.models import StudentSocialClub, StudentSocialClubMember
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Sends a daily summary of new members to faculty advisors.'

    def handle(self, *args, **options):
        yesterday = timezone.now() - timezone.timedelta(days=1)
        clubs = StudentSocialClub.objects.all()

        for club in clubs:
            if club.faculty_advisor:
                new_members = StudentSocialClubMember.objects.filter(
                    club=club,
                    joined_at__gte=yesterday
                )
                if new_members:
                    subject = f"Daily new member summary for {club.name}"
                    message = f""
                    Dear {club.faculty_advisor.get_full_name()},

                    Here is a summary of new members who joined {club.name} in the last 24 hours:

                    "
                    for member in new_members:
                        message += f"- {member.student.get_full_name()} ({member.student.email})\n"

                    message += ""
                    Thank you,
                    School Administration
                    ""
                    send_mail(
                        subject,
                        message,
                        'noreply@school.com',
                        [club.faculty_advisor.email],
                        fail_silently=False,
                    )
        self.stdout.write(self.style.SUCCESS('Daily summaries sent successfully.'))