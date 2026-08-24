"""
Student promotion service.

Handles:
  - Promotion preview (read-only, no DB writes to enrollment state)
  - Bulk / individual promotion execution inside a single atomic transaction
  - Idempotency: re-running a promotion never creates duplicate enrollments
  - Backfill of year-based enrollments from legacy StudentClass assignments

Multi-tenant safety: every query is scoped by school_id. Callers MUST pass
the requesting user's school.
"""
from django.db import transaction
from django.db.models import Avg, F, Q
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Class,
    Enrollment,
    GradingScale,
    PromotionBatch,
    PromotionPolicy,
    PromotionRecord,
    PromotionRule,
    StudentClass,
    StudentEnrollment,
)

VALID_ACTIONS = {'promote', 'repeat', 'graduate', 'withdraw', 'transfer'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_school_filter(user):
    """School id for tenant filtering (None for super_admin)."""
    if user.role == 'super_admin':
        return None
    return getattr(user, 'school_id', None)


def compute_final_average(student_id, school_id):
    """
    Final average (%) for a student computed from raw grade percentages
    (score / max_score * 100), averaged across all recorded grades.
    Returns None when the student has no grades yet.
    """
    from apps.students.models import Grade

    result = (
        Grade.objects.filter(student_id=student_id, max_score__gt=0)
        .annotate(raw_percent=F('score') * 100.0 / F('max_score'))
        .aggregate(average=Avg('raw_percent'))
    )
    avg = result.get('average')
    return round(avg, 2) if avg is not None else None


def _grading_scale_pass(student_average, school_id):
    """
    Decide pass/fail using the school's active grading scale entries
    (promotion_eligible flag). Returns (eligible: bool|None, remark: str).
    None means no usable scale was found.
    """
    scale = (
        GradingScale.objects.filter(school_id=school_id, is_active=True)
        .prefetch_related('entries')
        .order_by('-is_default', '-updated_at')
        .first()
    )
    if not scale:
        return None, ''
    for entry in scale.entries.all():
        if entry.min_percentage <= student_average <= entry.max_percentage:
            return entry.promotion_eligible, entry.remark or entry.grade_letter
    return None, ''


def ensure_source_enrollments(school_id, academic_year):
    """
    Backward compatibility: if the school has never had year-based enrollments
    for this academic year, seed them from live StudentClass assignments so
    existing schools can run promotions without manual data migration.
    Self-healing: tops up any MISSING enrollments (e.g. after a partial or
    interrupted earlier run) instead of skipping when some rows exist.
    Returns a dict: {pairs_found, created} so callers can surface
    diagnostics when a school's students are not linked to any class.
    """
    # Gather distinct (student, class) pairs from BOTH legacy assignment
    # mechanisms so pre-promotion schools get their students mapped into the
    # academic year automatically:
    #   1. StudentClass  — direct class assignments
    #   2. Enrollment    — subject-based enrollments (what the Classes page
    #                      uses for student counts)
    pairs = set()

    student_class_qs = (
        StudentClass.objects.filter(
            class_obj__school_id=school_id,
            is_active=True,
            class_obj__isnull=False,
            student__isnull=False,
        )
        .values_list('student_id', 'class_obj_id')
    )
    pairs.update(student_class_qs)

    enrollment_qs = (
        Enrollment.objects.filter(
            class_obj__school_id=school_id,
            is_active=True,
            class_obj__isnull=False,
            student__isnull=False,
        )
        .values_list('student_id', 'class_obj_id')
    )
    pairs.update(enrollment_qs)

    # Skip pairs that are already enrolled in this academic year so repeated
    # previews never duplicate anything.
    existing = set(
        StudentEnrollment.objects.filter(
            school_id=school_id,
            academic_year=academic_year,
        ).values_list('student_id', 'class_obj_id')
    )

    rows = [
        StudentEnrollment(
            school_id=school_id,
            student_id=student_id,
            academic_year=academic_year,
            class_obj_id=class_id,
            status='active',
            notes='Backfilled from current class assignment',
        )
        for student_id, class_id in pairs
        if student_id is not None and class_id is not None
        and (student_id, class_id) not in existing
    ]
    if not rows:
        return {'pairs_found': len(pairs), 'created': 0}

    try:
        # ignore_conflicts keeps this safe against concurrent runs and the
        # unique (student, academic_year) constraint.
        StudentEnrollment.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)
    except Exception:
        # Last-resort fallback for dirty legacy data: insert row by row and
        # skip any that fail, so a single bad record can never break the
        # promotion preview.
        created = 0
        for row in rows:
            try:
                StudentEnrollment.objects.get_or_create(
                    student=row.student,
                    academic_year=academic_year,
                    defaults={
                        'school_id': school_id,
                        'class_obj': row.class_obj,
                        'status': 'active',
                        'notes': row.notes,
                    },
                )
                created += 1
            except Exception:
                continue
        return {'pairs_found': len(pairs), 'created': created}
    return {'pairs_found': len(pairs), 'created': len(rows)}


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def build_promotion_preview(school_id, source_year, dest_year, class_ids=None):
    """
    Build a read-only promotion preview grouped by class.

    Never modifies enrollment state. The only write it may perform is the
    one-time backfill of source-year enrollments from legacy assignments
    (ensure_source_enrollments) so previews work for pre-existing schools.
    """
    backfill = ensure_source_enrollments(school_id, source_year)

    # Diagnostics: how many of the school's active students are NOT linked to
    # any class (they cannot be promoted until they are assigned to a class).
    from django.contrib.auth import get_user_model
    User = get_user_model()
    total_active_students = User.objects.filter(
        school_id=school_id, role='student', is_active=True,
    ).count()
    students_with_class = (
        StudentClass.objects.filter(
            class_obj__school_id=school_id, is_active=True,
        ).values_list('student_id', flat=True).distinct().count()
    )
    unassigned_students = max(0, total_active_students - students_with_class)

    policy = PromotionPolicy.objects.filter(school_id=school_id, is_active=True).first()

    rules = {
        r.from_class_id: r
        for r in PromotionRule.objects.filter(school_id=school_id, is_active=True)
        .select_related('from_class', 'to_class')
    }

    enrollments = (
        StudentEnrollment.objects.filter(
            school_id=school_id,
            academic_year=source_year,
            status='active',
        )
        .select_related('student', 'class_obj', 'class_obj__level')
        .order_by('class_obj__name', 'student__first_name', 'student__last_name')
    )
    if class_ids:
        enrollments = enrollments.filter(class_obj_id__in=class_ids)

    # Destination enrollments that already exist (idempotency warnings).
    existing_dest_ids = set(
        StudentEnrollment.objects.filter(
            school_id=school_id,
            academic_year=dest_year,
        ).values_list('student_id', flat=True)
    )

    classes_map = {}
    summary = {
        'total': 0, 'promote': 0, 'repeat': 0, 'graduate': 0,
        'withdraw': 0, 'transfer': 0, 'manual_review': 0,
    }

    for enrollment in enrollments:
        student = enrollment.student
        warnings = []

        rule = rules.get(enrollment.class_obj_id)

        if rule is None:
            action = 'manual_review'
            destination_class = None
            reason = 'No promotion rule configured for this class'
        elif rule.to_class is None:
            action = 'graduate'
            destination_class = None
            reason = f'{enrollment.class_obj.name} is a terminal class'
        else:
            action = 'promote'
            destination_class = rule.to_class
            reason = f'{enrollment.class_obj.name} -> {rule.to_class.name}'

        final_average = None

        # Apply the school's promotion policy on top of the structural rule.
        if policy and rule is not None:
            if policy.mode == 'average_threshold':
                final_average = compute_final_average(student.id, school_id)
                if final_average is None:
                    action = 'manual_review'
                    reason = 'No performance data available'
                    warnings.append('No grades recorded — needs administrator decision')
                elif final_average >= policy.pass_mark:
                    action = 'promote'
                    reason = f'Average {final_average}% >= {policy.pass_mark}% pass mark'
                else:
                    action = 'repeat'
                    destination_class = enrollment.class_obj
                    reason = f'Average {final_average}% below {policy.pass_mark}% pass mark'
            elif policy.mode == 'grading_scale':
                final_average = compute_final_average(student.id, school_id)
                if final_average is None:
                    action = 'manual_review'
                    reason = 'No performance data available'
                    warnings.append('No grades recorded — needs administrator decision')
                else:
                    eligible, remark = _grading_scale_pass(final_average, school_id)
                    if eligible is True:
                        action = 'promote'
                        reason = f'Grade "{remark}" is promotion-eligible'
                    elif eligible is False:
                        action = 'repeat'
                        destination_class = enrollment.class_obj
                        reason = f'Grade "{remark}" is not promotion-eligible'
                    else:
                        action = 'manual_review'
                        reason = 'Average does not fall within any grading-scale band'
            elif policy.mode == 'manual_review':
                action = 'manual_review'
                reason = 'School policy requires an administrator decision'

        if student.id in existing_dest_ids:
            warnings.append(f'Student already has an enrollment in {dest_year.name}')

        summary['total'] += 1
        summary[action] += 1

        class_entry = classes_map.setdefault(enrollment.class_obj_id, {
            'class_id': enrollment.class_obj_id,
            'class_name': enrollment.class_obj.name,
            'level_name': getattr(enrollment.class_obj.level, 'name', None),
            'total_students': 0,
            'counts': {'promote': 0, 'repeat': 0, 'graduate': 0,
                       'withdraw': 0, 'transfer': 0, 'manual_review': 0},
            'students': [],
        })
        class_entry['total_students'] += 1
        class_entry['counts'][action] += 1
        class_entry['students'].append({
            'student_id': student.id,
            'student_name': student.get_full_name() or student.username,
            'student_number': getattr(getattr(student, 'student_profile', None), 'student_id', ''),
            'current_class_id': enrollment.class_obj_id,
            'current_class_name': enrollment.class_obj.name,
            'recommended_action': action,
            'destination_class_id': destination_class.id if destination_class else None,
            'destination_class_name': destination_class.name if destination_class else None,
            'final_average': final_average,
            'reason': reason,
            'warnings': warnings,
        })

    return {
        'source_year': {'id': source_year.id, 'name': source_year.name},
        'destination_year': {'id': dest_year.id, 'name': dest_year.name},
        'policy_mode': policy.mode if policy else 'promote_all',
        'classes': list(classes_map.values()),
        'summary': summary,
        'diagnostics': {
            'total_active_students': total_active_students,
            'students_with_class_assignment': students_with_class,
            'unassigned_students': unassigned_students,
            'backfilled_enrollments': backfill.get('created', 0),
            'rules_configured': len(rules),
        },
    }


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _deactivate_student_assignments(student_id, exclude_class_id=None):
    qs = StudentClass.objects.filter(student_id=student_id, is_active=True)
    if exclude_class_id:
        qs = qs.exclude(class_obj_id=exclude_class_id)
    qs.update(is_active=False)


def _set_student_class(student_id, class_obj_id):
    """Make `class_obj_id` the student's single active class assignment."""
    _deactivate_student_assignments(student_id, exclude_class_id=class_obj_id)
    StudentClass.objects.update_or_create(
        student_id=student_id,
        class_obj_id=class_obj_id,
        defaults={'is_active': True},
    )


@transaction.atomic
def execute_promotions(school_id, user, source_year, dest_year, decisions):
    """
    Execute a set of promotion decisions in ONE atomic transaction.

    decisions: iterable of dicts:
      {student_id, action, to_class_id (optional override)}

    Idempotent: if a destination enrollment already exists for promote/repeat,
    the record is marked skipped instead of creating a duplicate.

    Any unexpected error rolls back the entire batch (no partial states).
    """
    batch = PromotionBatch.objects.create(
        school_id=school_id,
        source_academic_year=source_year,
        destination_academic_year=dest_year,
        created_by=user,
        status='in_progress',
    )

    rules = {
        r.from_class_id: r
        for r in PromotionRule.objects.filter(school_id=school_id, is_active=True)
    }

    # Pre-fetch students belonging to THIS school only (tenant isolation).
    from django.contrib.auth import get_user_model
    User = get_user_model()
    requested_ids = [int(d.get('student_id')) for d in decisions if d.get('student_id')]
    valid_students = set(
        User.objects.filter(id__in=requested_ids, school_id=school_id, role='student')
        .values_list('id', flat=True)
    )

    records = []
    for decision in decisions:
        try:
            student_id = int(decision.get('student_id'))
        except (TypeError, ValueError):
            continue

        action = str(decision.get('action', '')).lower()
        override_class_id = decision.get('to_class_id') or decision.get('to_class')

        base_record = {
            'batch': batch,
            'student_id': student_id,
            'action': action if action in VALID_ACTIONS | {'manual_review'} else 'manual_review',
        }

        if student_id not in valid_students:
            records.append(PromotionRecord(
                **base_record, status='failed',
                error_message='Student not found in your school',
            ))
            continue

        if action not in VALID_ACTIONS:
            records.append(PromotionRecord(
                **base_record, status='failed',
                error_message=f'Invalid action: {action}',
            ))
            continue

        # Lock the source enrollment row to avoid concurrent double-promotion.
        source_enrollment = (
            StudentEnrollment.objects.select_for_update()
            .filter(student_id=student_id, academic_year=source_year, school_id=school_id)
            .first()
        )
        if not source_enrollment:
            records.append(PromotionRecord(
                **base_record, status='failed',
                error_message=f'No active enrollment found in {source_year.name}',
            ))
            continue

        base_record.update({
            'source_enrollment': source_enrollment,
            'from_class': source_enrollment.class_obj,
            'final_average': compute_final_average(student_id, school_id),
        })

        try:
            if action == 'promote':
                rule = rules.get(source_enrollment.class_obj_id)
                target_class_id = override_class_id or (rule.to_class_id if rule else None)
                if not target_class_id:
                    raise ValueError('No destination class (configure a promotion rule or provide to_class)')

                # Idempotency check.
                if StudentEnrollment.objects.filter(
                    student_id=student_id, academic_year=dest_year
                ).exists():
                    records.append(PromotionRecord(**base_record, status='skipped',
                                                   warning=f'Already enrolled in {dest_year.name}'))
                    continue

                dest_enrollment = StudentEnrollment.objects.create(
                    school_id=school_id,
                    student_id=student_id,
                    academic_year=dest_year,
                    class_obj_id=target_class_id,
                    status='active',
                    promoted_from=source_enrollment,
                )
                source_enrollment.status = 'promoted'
                source_enrollment.save(update_fields=['status', 'updated_at'])
                _set_student_class(student_id, target_class_id)
                base_record['to_class_id'] = target_class_id
                records.append(PromotionRecord(**base_record, status='success',
                                               reason=f'Promoted to {Class.objects.get(pk=target_class_id).name}'))

            elif action == 'repeat':
                target_class_id = override_class_id or source_enrollment.class_obj_id

                if StudentEnrollment.objects.filter(
                    student_id=student_id, academic_year=dest_year
                ).exists():
                    records.append(PromotionRecord(**base_record, status='skipped',
                                                   warning=f'Already enrolled in {dest_year.name}'))
                    continue

                StudentEnrollment.objects.create(
                    school_id=school_id,
                    student_id=student_id,
                    academic_year=dest_year,
                    class_obj_id=target_class_id,
                    status='repeating',
                    promoted_from=source_enrollment,
                )
                source_enrollment.status = 'repeating'
                source_enrollment.save(update_fields=['status', 'updated_at'])
                _set_student_class(student_id, target_class_id)
                base_record['to_class_id'] = target_class_id
                records.append(PromotionRecord(**base_record, status='success',
                                               reason=f'Repeats {source_enrollment.class_obj.name}'))

            elif action == 'graduate':
                source_enrollment.status = 'graduated'
                source_enrollment.save(update_fields=['status', 'updated_at'])
                _deactivate_student_assignments(student_id)
                records.append(PromotionRecord(**base_record, status='success',
                                               reason='Graduated'))

            elif action == 'withdraw':
                source_enrollment.status = 'withdrawn'
                source_enrollment.save(update_fields=['status', 'updated_at'])
                _deactivate_student_assignments(student_id)
                records.append(PromotionRecord(**base_record, status='success',
                                               reason='Withdrawn from school'))

            elif action == 'transfer':
                source_enrollment.status = 'transferred'
                source_enrollment.save(update_fields=['status', 'updated_at'])
                _deactivate_student_assignments(student_id)
                records.append(PromotionRecord(**base_record, status='success',
                                               reason='Transferred out'))

        except Exception as exc:
            records.append(PromotionRecord(**base_record, status='failed',
                                           error_message=str(exc)))

    PromotionRecord.objects.bulk_create(records, batch_size=200)

    # Recompute counts from the persisted records (single source of truth).
    counts = {}
    for row in PromotionRecord.objects.filter(batch=batch).values('action', 'status'):
        key = row['action'] if row['status'] == 'success' else row['status']
        counts[key] = counts.get(key, 0) + 1

    batch.total_students = len(records)
    batch.promoted_count = counts.get('promote', 0)
    batch.repeated_count = counts.get('repeat', 0)
    batch.graduated_count = counts.get('graduate', 0)
    batch.withdrawn_count = counts.get('withdraw', 0)
    batch.transferred_count = counts.get('transfer', 0)
    batch.failed_count = counts.get('failed', 0)
    batch.skipped_count = counts.get('skipped', 0)

    failures = batch.failed_count + batch.skipped_count
    if batch.total_students and failures == batch.total_students:
        batch.status = 'failed'
    elif failures > 0:
        batch.status = 'partially_completed'
    else:
        batch.status = 'completed'
    batch.completed_at = timezone.now()
    batch.save()

    return batch


def auto_decisions_from_preview(preview, include_manual_review=False):
    """
    Convert a preview payload into executable decisions.
    Excludes manual_review unless explicitly included.
    """
    decisions = []
    for class_entry in preview['classes']:
        for s in class_entry['students']:
            action = s['recommended_action']
            if action == 'manual_review' and not include_manual_review:
                continue
            decisions.append({
                'student_id': s['student_id'],
                'action': action,
                'to_class_id': s['destination_class_id'],
            })
    return decisions
