"""Invalidate topic caches after committed changes to frequently-read models.

Every entry maps a Django model (``app_label.modelname``) to the cache
namespaces it feeds. When such a row is created, updated or deleted, the
matching namespace generations are bumped (after the transaction commits) so
the next request recomputes fresh data and no stale response is ever served.

Design notes
------------
* Over-invalidation is safe, under-invalidation is not. When unsure, map a
  model to every namespace that could read it.
* Invalidation is scoped by school when the instance carries a ``school``
  (or ``school_id``), and also bumps the global generation for platform-wide
  views. A tenant write never flushes another tenant's scoped entries.
  Models without a tenant fall back to a global bump for their namespace.
* The ``notifications`` namespace is intentionally NOT listed here: notification
  rows are per-recipient and are invalidated with a user-scoped generation by
  ``apps/notifications/signals.py`` so one user's notification never nukes
  another user's cached list.
"""
from django.db.models.signals import post_delete, post_save, pre_save
from django.db import transaction

from core.cache import CACHE_KEYS, DashboardCache, invalidate_keys, invalidate_model_cache


MODEL_NAMESPACES = {
    # ── Users / people ───────────────────────────────────────────────
    'users.user': ('students', 'teachers', 'parents', 'timetables'),
    'users.studentprofile': ('students',),
    'users.teacherprofile': ('teachers',),
    'users.parentstudentrelationship': ('parents',),

    # ── Academics structure ──────────────────────────────────────────
    'academics.class': ('courses', 'students', 'teachers', 'timetables'),
    'academics.subject': ('courses', 'teachers', 'timetables'),
    'academics.faculty': ('courses',),
    'academics.department': ('courses',),
    'academics.level': ('courses',),
    'academics.classsubject': ('courses', 'teachers'),
    'academics.classteacher': ('teachers', 'courses'),
    'academics.classsubjectteacher': ('teachers', 'courses'),
    'academics.studentclass': ('students', 'courses'),
    'academics.enrollment': ('students', 'courses'),
    'academics.studentenrollment': ('students', 'courses'),
    'academics.timetable': ('courses', 'calendar', 'timetables'),
    'academics.examresult': ('students',),
    'academics.terminalreport': ('students',),
    'academics.subjectscore': ('students',),
    'academics.assessment': ('students', 'courses'),
    'academics.assessmenttype': ('courses',),
    'academics.userprofilepicture': ('students', 'teachers'),
    'academics.gradingscale': ('courses',),
    'academics.gradingpolicy': ('courses',),
    'academics.academicsession': ('courses', 'calendar'),
    'academics.academiccalendarevent': ('calendar',),
    'academics.academicyear': ('calendar', 'courses'),
    'academics.schoolevent': ('calendar', 'notices'),
    'academics.notice': ('notices',),

    # ── Grades / attendance ──────────────────────────────────────────
    'students.grade': ('students',),
    'attendance.attendance': ('attendance', 'students'),

    # ── Assignments ──────────────────────────────────────────────────
    'assignments.assignment': ('assignments', 'students'),
    'assignments.assignmentsubmission': ('assignments', 'students'),

    # ── Billing / finance (feed the dashboard + billing lists) ────────
    'billing.fee': ('billing',),
    'billing.schoolfeeassignment': ('billing',),
    'billing.classfeeassignment': ('billing',),
    'billing.studentfeeassignment': ('billing',),
    'billing.manualpayment': ('billing',),
    'billing.onlinepayment': ('billing',),
    'billing.invoice': ('billing',),
    'billing.payment': ('billing',),

    # ── Messaging / notices ──────────────────────────────────────────
    'messaging.message': ('messages',),
    'messaging.announcement': ('notices', 'messages'),
    'messaging.notice': ('notices',),

    # ── Learning feed (public + personalized list caches) ────────────
    'feed.feedlesson': ('feed',),
    'feed.feedcomment': ('feed',),
    'feed.feedreport': ('feed',),

    # ── Schools / platform content ───────────────────────────────────
    'schools.school': ('schools', 'homepage'),
    'schools.announcement': ('notices', 'announcements'),
    'schools.plan': ('schools',),
    'schools.subscription': ('schools',),
    'platform.systemsetting': ('homepage',),
    'platform.featureflag': ('homepage',),
}

PLATFORM_ANALYTICS_MODELS = {
    'schools.school',
    'users.user',
    'billing.manualpayment',
    'billing.onlinepayment',
}

# Models whose ``school`` FK may change on update: remember the previous tenant
# so both the old and new school scopes are invalidated.
SCHOOL_MOVABLE_MODELS = {
    'users.user',
    'academics.class',
    'academics.subject',
    'academics.faculty',
    'academics.level',
    'academics.enrollment',
    'academics.studentenrollment',
    'billing.studentfeeassignment',
    'billing.classfeeassignment',
    'billing.schoolfeeassignment',
}

# SystemSetting keys whose change must bust the public homepage cache.
HOMEPAGE_SETTING_PREFIXES = ('homepage.', 'pages.hero_images')


def _resolve_school_id(sender, instance):
    if sender._meta.label_lower == 'schools.school':
        return instance.pk

    school_id = getattr(instance, 'school_id', None)
    if school_id:
        return school_id

    if sender._meta.label_lower in (
        'users.studentprofile',
        'users.teacherprofile',
        'academics.userprofilepicture',
    ):
        from apps.users.models import User
        return User.objects.filter(pk=instance.user_id).values_list('school_id', flat=True).first()

    class_obj_id = getattr(instance, 'class_obj_id', None)
    if class_obj_id:
        from apps.academics.models import Class
        return Class.objects.filter(pk=class_obj_id).values_list('school_id', flat=True).first()

    faculty_id = getattr(instance, 'faculty_id', None)
    if faculty_id:
        from apps.academics.models import Faculty
        return Faculty.objects.filter(pk=faculty_id).values_list('school_id', flat=True).first()

    # Fall back to the related user's school when only a user FK is present.
    user_id = getattr(instance, 'user_id', None)
    if user_id and sender._meta.label_lower in (
        'users.parentstudentrelationship',
    ):
        from apps.users.models import User
        return User.objects.filter(pk=user_id).values_list('school_id', flat=True).first()

    student_id = getattr(instance, 'student_id', None)
    if student_id and sender._meta.label_lower == 'students.grade':
        from apps.users.models import User
        return User.objects.filter(pk=student_id).values_list('school_id', flat=True).first()

    return None


def _remember_previous_school(sender, instance, **kwargs):
    if not instance.pk or not any(field.name == 'school' for field in sender._meta.get_fields()):
        return
    try:
        instance._cache_previous_school_id = sender.objects.filter(
            pk=instance.pk
        ).values_list('school_id', flat=True).first()
    except Exception:
        instance._cache_previous_school_id = None


def _invalidate_model_caches(sender, instance, **kwargs):
    namespaces = MODEL_NAMESPACES.get(sender._meta.label_lower)
    if not namespaces:
        return

    # SystemSetting only busts the homepage cache for public content keys.
    if sender._meta.label_lower == 'platform.systemsetting':
        key = getattr(instance, 'key', '') or ''
        if not key.startswith(HOMEPAGE_SETTING_PREFIXES):
            return

    if sender._meta.label_lower == 'schools.school':
        # One generation bump invalidates both this school's scope and
        # platform-wide (Super Admin) results, without flushing other schools.
        invalidate_model_cache(*namespaces, school_id=instance.pk)
        school_ids = {instance.pk}
    else:
        school_id = _resolve_school_id(sender, instance)
        previous_school_id = getattr(instance, '_cache_previous_school_id', None)
        school_ids = {value for value in (school_id, previous_school_id) if value}
        if school_ids:
            for tenant_id in school_ids:
                invalidate_model_cache(*namespaces, school_id=tenant_id)
        else:
            invalidate_model_cache(*namespaces)

    model_label = sender._meta.label_lower
    for tenant_id in school_ids:
        transaction.on_commit(
            lambda tenant_id=tenant_id: DashboardCache.invalidate_stats(tenant_id)
        )

    if model_label in PLATFORM_ANALYTICS_MODELS:
        platform_keys = (
            CACHE_KEYS['super_admin_usage'],
            CACHE_KEYS['super_admin_analytics'],
        )
        transaction.on_commit(lambda: invalidate_keys(*platform_keys))


def register_cache_signals():
    for model_label in MODEL_NAMESPACES:
        if model_label in SCHOOL_MOVABLE_MODELS:
            pre_save.connect(
                _remember_previous_school,
                sender=model_label,
                dispatch_uid=f'cache.previous_school.{model_label}',
            )
        post_save.connect(
            _invalidate_model_caches,
            sender=model_label,
            dispatch_uid=f'cache.invalidate_save.{model_label}',
        )
        post_delete.connect(
            _invalidate_model_caches,
            sender=model_label,
            dispatch_uid=f'cache.invalidate_delete.{model_label}',
        )
