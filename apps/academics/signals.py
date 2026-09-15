"""
Signal handlers for the academics app.

The handler here keeps a student's *year-based* enrollment
(``StudentEnrollment``) in step with their live class assignment
(``StudentClass``). Without it, placing a student in a class would leave their
current academic year empty in the promotion/history views until a manual
backfill ran.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)


def _handle_student_class_saved(sender, instance, **kwargs):
    """Mirror a live class assignment onto the student's academic year."""
    if not instance.is_active:
        return

    from apps.academics.enrollment_service import sync_student_year_enrollment

    # Never let a bookkeeping failure break class assignment itself - the
    # enrollment row is derived data and can be rebuilt by the backfill.
    try:
        # Keep a bookkeeping failure inside a savepoint. Catching a database
        # exception directly inside the caller's transaction leaves Django's
        # connection rollback-only and breaks the promotion batch.
        with transaction.atomic():
            sync_student_year_enrollment(instance.student, class_obj=instance.class_obj)
    except Exception:
        logger.exception(
            'Failed to sync year enrollment for student %s', instance.student_id
        )


def register_signal_handlers():
    """Connect the academics signal handlers. Called from ``apps.ready()``."""
    from apps.academics.models import StudentClass

    post_save.connect(
        _handle_student_class_saved,
        sender=StudentClass,
        dispatch_uid='academics.sync_student_year_enrollment',
    )
