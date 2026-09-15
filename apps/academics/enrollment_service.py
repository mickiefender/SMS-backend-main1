"""
Shared helpers for keeping a student's academic-year enrollment in sync.

Two related concepts live in this codebase:

  * ``StudentProfile.academic_year`` - the academic year a student is
    *currently* in. It is assigned automatically when a student is onboarded
    and can be changed by a school admin from the student detail page.

  * ``StudentEnrollment`` - one row per (student, academic year) recording the
    class the student belonged to that year. This is what the promotion system
    reads and what the per-year enrollment timeline displays.

This module keeps the two consistent: whenever a student is placed in a class
(``StudentClass``) or their academic year changes, a matching
``StudentEnrollment`` row is created for their current academic year.
"""
from django.db import transaction

# StudentEnrollment uses a non-null class FK, so a row can only exist once the
# student actually has a class. Everything here degrades gracefully to a no-op
# when the year or the class is unknown.
ENROLLMENT_STATUS_ACTIVE = 'active'


def get_current_academic_year(school_id):
    """Return the school's current ``AcademicYear`` or ``None``.

    Prefers the explicitly flagged current year; falls back to the most recent
    year that is still marked active so schools that never toggled the flag
    still get automatic assignment.
    """
    if not school_id:
        return None

    from apps.academics.models import AcademicYear

    current = AcademicYear.objects.filter(school_id=school_id, is_current=True).first()
    if current is not None:
        return current

    return (
        AcademicYear.objects.filter(school_id=school_id, status='active')
        .order_by('-start_date')
        .first()
    )


def get_student_academic_year(student):
    """The academic year recorded on the student's profile, if any."""
    profile = getattr(student, 'student_profile', None)
    if profile is not None and profile.academic_year_id:
        return profile.academic_year
    return None


def resolve_student_academic_year(student, fallback_to_current=True):
    """Profile year first, then the school's current year."""
    year = get_student_academic_year(student)
    if year is None and fallback_to_current:
        year = get_current_academic_year(getattr(student, 'school_id', None))
    return year


def get_active_class(student_id):
    """The class a student is actively assigned to, or ``None``."""
    from apps.academics.models import StudentClass

    row = (
        StudentClass.objects.filter(student_id=student_id, is_active=True)
        .select_related('class_obj')
        .order_by('-assigned_date', '-id')
        .first()
    )
    return row.class_obj if row else None


@transaction.atomic
def sync_student_year_enrollment(student, academic_year=None, class_obj=None):
    """Ensure a ``StudentEnrollment`` exists for the student's academic year.

    ``academic_year`` defaults to the student's profile year, then the school's
    current year. ``class_obj`` defaults to the student's active class. Returns
    the enrollment, or ``None`` when there is no year/class to record yet.
    """
    from apps.academics.models import StudentEnrollment

    school_id = getattr(student, 'school_id', None)
    if not school_id:
        return None

    year = academic_year or resolve_student_academic_year(student)
    if year is None:
        return None

    klass = class_obj or get_active_class(student.id)
    if klass is None:
        return None

    enrollment, created = StudentEnrollment.objects.get_or_create(
        student=student,
        academic_year=year,
        defaults={
            'school_id': school_id,
            'class_obj': klass,
            'status': ENROLLMENT_STATUS_ACTIVE,
        },
    )

    # Keep the class on an *active* row in step with the student's current
    # class. Historical rows (promoted/repeating/graduated/...) are never
    # touched - they are the permanent record of past years.
    if not created and enrollment.status == ENROLLMENT_STATUS_ACTIVE and enrollment.class_obj_id != klass.id:
        enrollment.class_obj = klass
        enrollment.save(update_fields=['class_obj', 'updated_at'])

    return enrollment
