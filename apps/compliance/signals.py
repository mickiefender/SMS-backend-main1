from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.compliance.models import ComplianceProfile
from apps.schools.models import School


@receiver(post_save, sender=School)
def create_school_compliance_profile(sender, instance, created, **kwargs):
    if not created:
        return

    ComplianceProfile.objects.get_or_create(school=instance)

    if instance.status == 'pending_compliance' and not instance.compliance_status:
        School.objects.filter(pk=instance.pk).update(compliance_status='pending')


def register_signal_handlers():
    post_save.connect(create_school_compliance_profile, sender=School, dispatch_uid='compliance.create_profile')
