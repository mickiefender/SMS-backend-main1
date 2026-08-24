"""
Super Admin Feed Supervisor APIs.

Global supervision over the EXISTING Alara Feed infrastructure
(FeedLesson / FeedReport / ModerationService). Introduces NO new feed
models — restrictions and policies are stored in the existing platform
SystemSetting table via feed_policy_service, and every moderation action is
recorded in the platform AuditLog.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count, Max, Prefetch, Q
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.feed import models as feed_models
from apps.feed.services.feed_policy_service import (
    DEFAULT_FEED_POLICIES,
    FEED_POLICIES_KEY,
    MODERATION_MODES,
    get_feed_policies,
    get_feed_restricted_user_ids,
    is_feed_restricted,
    save_feed_policies,
    set_creator_restricted,
)
from apps.feed.services.moderation_service import ModerationService
from apps.platform.models import AuditLog, write_audit_log

# Re-exported so existing consumers (`apps.feed.views`) keep working.
__all__ = [
    'FeedSupervisorViewSet', 'IsSuperAdmin', 'is_feed_restricted',
]


# ---------------------------------------------------------------------------
# Permissions & helpers
# ---------------------------------------------------------------------------

class IsSuperAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        return (
            super().has_permission(request, view)
            and getattr(request.user, 'role', '') == 'super_admin'
        )


OPEN_REPORT_STATUSES = ('pending', 'reviewing')

# Content states surfaced by the supervisor (requirement 6). Derived from
# existing status/visibility/report fields — no schema change needed.
CONTENT_STATES = (
    'published', 'pending_review', 'under_review',
    'flagged', 'hidden', 'removed', 'restored',
)


def _open_reports_qs():
    return feed_models.FeedReport.objects.filter(status__in=OPEN_REPORT_STATUSES)


def _annotate_posts(qs):
    """Annotate report counts once — avoids N+1 in list endpoints."""
    return qs.annotate(
        open_reports_count=Count(
            'reports',
            filter=Q(reports__status='pending'),
            distinct=True,
        ),
        reviewing_reports_count=Count(
            'reports',
            filter=Q(reports__status='reviewing'),
            distinct=True,
        ),
        total_reports_count=Count('reports', distinct=True),
    ).select_related('teacher', 'school', 'content_type')


def content_state(l) -> str:
    """Derive the supervisor-facing content state for a post."""
    if l.status == 'suspended' or l.visibility == 'suspended':
        return 'removed'
    if l.visibility == 'hidden':
        return 'hidden'
    if getattr(l, 'reviewing_reports_count', 0):
        return 'under_review'
    if getattr(l, 'open_reports_count', 0):
        return 'flagged'
    if l.status == 'pending_review':
        return 'pending_review'
    return 'published'


def _post_row(l) -> dict:
    return {
        'id': l.id,
        'title': l.title,
        'preview': (l.description or '')[:160],
        'thumbnail_url': l.cloudflare_thumbnail_url or l.thumbnail_url or '',
        'playback_url': l.cloudflare_playback_url,
        'content_type': l.content_type.name if l.content_type else '',
        'content_state': content_state(l),
        'status': l.status,
        'visibility': l.visibility,
        'teacher_id': l.teacher_id,
        'teacher_name': l.teacher.get_full_name() if l.teacher else '—',
        'school_id': l.school_id,
        'school_name': l.school.name if l.school else None,
        'open_reports_count': getattr(l, 'open_reports_count', 0),
        'total_reports_count': getattr(l, 'total_reports_count', 0),
        'view_count': l.view_count,
        'like_count': l.like_count,
        'comment_count': l.comment_count,
        'created_at': l.created_at,
        'published_at': l.published_at,
    }


def _report_row(r) -> dict:
    lesson = r.lesson
    lesson_data = None
    if lesson:
        lesson_data = {
            'id': lesson.id,
            'title': lesson.title,
            'status': lesson.status,
            'visibility': lesson.visibility,
            'teacher_id': lesson.teacher_id,
            'teacher_name': lesson.teacher.get_full_name() if lesson.teacher else '—',
            'school_name': lesson.school.name if lesson.school else None,
        }
    return {
        'id': r.id,
        'target_type': r.target_type,
        'reason': r.reason,
        'description': r.description,
        'status': r.status,
        'resolution': r.resolution,
        'reporter_name': r.reporter.get_full_name() if r.reporter else 'Anonymous',
        'lesson': lesson_data,
        'comment_id': r.comment_id,
        'teacher_target_id': r.teacher_id,
        'resolved_by_name': r.resolved_by.get_full_name() if r.resolved_by else None,
        'resolved_at': r.resolved_at,
        'created_at': r.created_at,
    }


class SupervisorPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


def _apply_state_filter(qs, state: str):
    """Filter posts by the derived supervisor content state."""
    published_q = Q(status='approved') & ~Q(visibility__in=['hidden', 'suspended'])
    removed_q = Q(status='suspended') | Q(visibility='suspended')
    if state == 'published':
        return qs.filter(published_q)
    if state == 'restored':
        # Restored posts are back in circulation — same visibility as published.
        return qs.filter(published_q)
    if state == 'pending_review':
        return qs.filter(status='pending_review')
    if state == 'hidden':
        return qs.filter(visibility='hidden')
    if state == 'removed':
        return qs.filter(removed_q)
    if state == 'flagged':
        return qs.filter(open_reports_count__gt=0).exclude(removed_q).exclude(
            visibility='hidden')
    if state == 'under_review':
        return qs.filter(reviewing_reports_count__gt=0).exclude(removed_q).exclude(
            visibility='hidden')
    return qs


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class FeedSupervisorViewSet(ViewSet):
    """
    Super Admin Feed Supervisor:
      GET  /api/feed/supervisor/overview/
      GET  /api/feed/supervisor/posts/?state=&q=&school=...
      POST /api/feed/supervisor/posts/{id}/moderate/       {action, notes}
      GET  /api/feed/supervisor/reports/?status=
      POST /api/feed/supervisor/reports/{id}/handle/       {action, notes}
      GET  /api/feed/supervisor/creators/?q=&ordering=
      GET  /api/feed/supervisor/creators/{id}/
      POST /api/feed/supervisor/creators/{id}/restrict/     {notes}
      POST /api/feed/supervisor/creators/{id}/suspend/      {notes}
      POST /api/feed/supervisor/creators/{id}/unrestrict/   {notes}
      GET  /api/feed/supervisor/schools/?school_id=
      GET|PUT /api/feed/supervisor/settings/
    """
    permission_classes = [IsSuperAdmin]

    # -- 1. Overview ------------------------------------------------------

    @action(detail=False, methods=['get'])
    def overview(self, request):
        cached = cache.get('feed_supervisor_overview')
        if cached:
            return Response(cached)

        now = timezone.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        lessons = feed_models.FeedLesson.objects.all()

        by_resource = dict(
            feed_models.LessonResource.objects.values('resource_type')
            .annotate(n=Count('id')).values_list('resource_type', 'n')
        )
        reported_lessons = lessons.annotate(
            open_reports=Count(
                'reports', filter=Q(reports__status__in=OPEN_REPORT_STATUSES),
                distinct=True)
        ).filter(open_reports__gt=0)

        # One-query content-state breakdown (conditional aggregation).
        published_q = Q(status='approved') & ~Q(visibility__in=['hidden', 'suspended'])
        removed_q = Q(status='suspended') | Q(visibility='suspended')
        state_counts = dict(lessons.aggregate(
            published=Count('id', filter=published_q),
            pending_review=Count('id', filter=Q(status='pending_review')),
            hidden=Count('id', filter=Q(visibility='hidden')),
            removed=Count('id', filter=removed_q),
        ))

        most_reported = [
            {'id': l.id, 'title': l.title, 'reports': l.total_reports_count}
            for l in _annotate_posts(lessons)
            .filter(total_reports_count__gt=0)
            .order_by('-total_reports_count')[:5]
        ]
        recent_activity = [
            {
                'id': log.id, 'actor': log.actor_name, 'action': log.action,
                'target': log.target_label, 'created_at': log.created_at,
            }
            for log in AuditLog.objects.filter(action__startswith='feed.')[:12]
        ]

        data = {
            'total_posts': lessons.count(),
            'posts_today': lessons.filter(created_at__gte=day_start).count(),
            'videos': by_resource.get('video', 0),
            'images': by_resource.get('image', 0),
            'documents': by_resource.get('pdf', 0) + by_resource.get('audio', 0),
            'reported_posts': reported_lessons.count(),
            'flagged_posts': reported_lessons.count(),  # alias until dedicated flag field exists
            'hidden_posts': state_counts['hidden'],
            'removed_posts': state_counts['removed'],
            'pending_review': state_counts['pending_review'],
            'published_posts': state_counts['published'],
            'active_creators_30d': lessons.filter(
                created_at__gte=now - timezone.timedelta(days=30)
            ).values('teacher').distinct().count(),
            'most_active_schools': [
                {'id': s['school'], 'name': s['school__name'], 'posts': s['n']}
                for s in lessons.exclude(school=None).values(
                    'school', 'school__name').annotate(n=Count('id'))
                .order_by('-n')[:5]
            ],
            'most_reported_content': most_reported,
            'recent_activity': recent_activity,
        }
        cache.set('feed_supervisor_overview', data, 60)
        return Response(data)

    # -- 2. All posts ------------------------------------------------------

    @action(detail=False, methods=['get'])
    def posts(self, request):
        qs = _annotate_posts(feed_models.FeedLesson.objects.all())

        params = request.query_params
        if q := (params.get('q') or '').strip():
            qs = qs.filter(Q(title__icontains=q) | Q(topic__icontains=q))
        if school := params.get('school'):
            qs = qs.filter(school_id=school)
        if teacher := params.get('teacher'):
            qs = qs.filter(teacher_id=teacher)
        if ctype := params.get('content_type'):
            qs = qs.filter(content_type__slug=ctype)
        if vis := params.get('visibility'):
            qs = qs.filter(visibility=vis)
        if st := params.get('status'):
            qs = qs.filter(status=st)
        qs = _apply_state_filter(qs, params.get('state', ''))
        if date_from := params.get('date_from'):
            qs = qs.filter(created_at__gte=date_from)
        if date_to := params.get('date_to'):
            qs = qs.filter(created_at__lte=f'{date_to}T23:59:59')

        order_map = {
            '-created_at': '-created_at', 'created_at': 'created_at',
            '-reports': '-total_reports_count', '-views': '-view_count',
            '-likes': '-like_count',
        }
        qs = qs.order_by(order_map.get(params.get('ordering'), '-created_at'))

        paginator = SupervisorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([_post_row(l) for l in page])

    # -- 7. Post moderation (audited) ---------------------------------------

    @action(detail=False, methods=['post'],
            url_path=r'posts/(?P<post_id>\d+)/moderate')
    def moderate_post(self, request, post_id=None):
        lesson = feed_models.FeedLesson.objects.select_related(
            'teacher', 'school').filter(pk=post_id).first()
        if not lesson:
            return Response({'error': 'Post not found'}, status=404)

        action_name = request.data.get('action')
        notes = (request.data.get('notes') or '').strip()
        previous_status = lesson.status
        previous_visibility = lesson.visibility

        actions = {
            'hide': lambda: setattr(lesson, 'visibility', 'hidden'),
            'remove': lambda: (
                setattr(lesson, 'status', 'suspended'),
                setattr(lesson, 'visibility', 'suspended')),
            'restore': lambda: (
                setattr(lesson, 'status', 'approved'),
                setattr(lesson, 'visibility', 'public'),
                setattr(lesson, 'published_at', lesson.published_at or timezone.now())),
        }
        if action_name == 'approve':
            ModerationService.approve_lesson(lesson, request.user)
        elif action_name == 'suspend':
            ModerationService.suspend_lesson(lesson, request.user, reason=notes)
        elif action_name in actions:
            actions[action_name]()
            lesson.save(update_fields=[
                f for f in ('status', 'visibility', 'published_at')
                if hasattr(lesson, f)] or None)
            lesson.refresh_from_db(fields=['status', 'visibility'])
        else:
            return Response({'error': f'Unknown action "{action_name}"'}, status=400)

        write_audit_log(
            request, request.user, f'feed.post_{action_name}',
            'feed_lesson', lesson.id, lesson.title,
            {
                'teacher_id': lesson.teacher_id,
                'school_id': lesson.school_id,
                'previous_status': previous_status,
                'new_status': lesson.status,
                'previous_visibility': previous_visibility,
                'new_visibility': lesson.visibility,
                'notes': notes,
            })
        cache.delete('feed_supervisor_overview')
        return Response(_post_row(_annotate_posts(
            feed_models.FeedLesson.objects.filter(pk=lesson.id)).first()))

    # -- 3. Reported content queue -------------------------------------------

    @action(detail=False, methods=['get'])
    def reports(self, request):
        qs = feed_models.FeedReport.objects.select_related(
            'reporter', 'resolved_by', 'lesson', 'lesson__teacher', 'lesson__school',
        ).order_by('-created_at')

        if st := request.query_params.get('status'):
            qs = qs.filter(status=st)
        elif request.query_params.get('queue') == 'open':
            qs = qs.filter(status__in=OPEN_REPORT_STATUSES)
        if tt := request.query_params.get('target_type'):
            qs = qs.filter(target_type=tt)

        paginator = SupervisorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([_report_row(r) for r in page])

    @action(detail=False, methods=['post'],
            url_path=r'reports/(?P<report_id>\d+)/handle')
    def handle_report(self, request, report_id=None):
        report = feed_models.FeedReport.objects.select_related(
            'lesson', 'lesson__teacher', 'teacher').filter(pk=report_id).first()
        if not report:
            return Response({'error': 'Report not found'}, status=404)

        handle_action = request.data.get('action')
        notes = (request.data.get('notes') or '').strip()
        lesson = report.lesson
        teacher_id = report.teacher_id or (lesson.teacher_id if lesson else None)

        resolutions = {
            'dismiss': 'Report dismissed.',
            'hide_post': 'Report upheld — post hidden.',
            'remove_post': 'Report upheld — post removed.',
            'warn_creator': 'Creator warned.',
            'restrict_creator': 'Creator restricted from the Feed.',
            'suspend_creator': 'Creator suspended.',
        }
        if handle_action not in resolutions:
            return Response({'error': f'Unknown action "{handle_action}"'}, status=400)

        if handle_action == 'dismiss':
            ModerationService.dismiss_report(report, request.user, notes)
        else:
            if handle_action == 'hide_post' and lesson:
                ModerationService.hide_lesson(lesson)
            elif handle_action == 'remove_post' and lesson:
                ModerationService.suspend_lesson(lesson, request.user, reason=notes)
            elif handle_action in ('restrict_creator', 'suspend_creator'):
                self._apply_restriction(request, teacher_id, handle_action, notes)
            elif handle_action == 'warn_creator':
                feed_models.FeedNotification.objects.create(
                    user_id=teacher_id,
                    notification_type='general',
                    title='Feed moderation warning',
                    message=notes or 'A moderator reviewed your content following a report.',
                    lesson=lesson,
                    actor=request.user,
                    priority='high',
                )
            ModerationService.resolve_report(
                report, request.user, f'{resolutions[handle_action]} {notes}'.strip())

        write_audit_log(
            request, request.user, f'feed.{handle_action}',
            'feed_report', report.id, str(report.reason),
            {
                'teacher_id': teacher_id,
                'school_id': lesson.school_id if lesson else None,
                'lesson_id': lesson.id if lesson else None,
                'previous_status': report.status,
                'new_status': 'resolved' if handle_action != 'dismiss' else 'dismissed',
                'notes': notes,
            })
        cache.delete('feed_supervisor_overview')
        return Response({'ok': True})

    # -- 4. Creator monitoring ----------------------------------------------

    @action(detail=False, methods=['get'])
    def creators(self, request):
        """Paginated list of teachers with their feed activity summary."""
        User = get_user_model()
        qs = User.objects.filter(role='teacher').annotate(
            total_posts=Count('feed_lessons', distinct=True),
            removed_posts=Count(
                'feed_lessons',
                filter=Q(feed_lessons__status='suspended')
                | Q(feed_lessons__visibility='suspended'),
                distinct=True,
            ),
            last_post_at=Max('feed_lessons__created_at'),
        )

        params = request.query_params
        if q := (params.get('q') or '').strip():
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q)
                           | Q(email__icontains=q))
        order_map = {
            '-posts': '-total_posts',
            '-last_post_at': '-last_post_at',
        }
        ordering = order_map.get(params.get('ordering'))
        # '-reports' is sorted in Python after the page is materialised
        # (report counts are computed per-page to avoid join fanout).
        if ordering:
            qs = qs.order_by(ordering, '-total_posts')
        else:
            qs = qs.order_by('-total_posts')

        paginator = SupervisorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        # Report counts fetched separately to avoid multi-join fanout.
        ids = [u.pk for u in page]
        report_totals: dict = {}
        if ids:
            direct = dict(
                feed_models.FeedReport.objects.filter(teacher_id__in=ids)
                .values('teacher_id').annotate(n=Count('id'))
                .values_list('teacher_id', 'n'))
            via_lessons = dict(
                feed_models.FeedReport.objects.filter(
                    target_type='lesson', lesson__teacher_id__in=ids)
                .values('lesson__teacher_id').annotate(n=Count('id'))
                .values_list('lesson__teacher_id', 'n'))
            for tid in ids:
                report_totals[tid] = max(direct.get(tid, 0), via_lessons.get(tid, 0))

        restricted = get_feed_restricted_user_ids()
        rows = []
        for u in page:
            rows.append({
                'id': u.pk,
                'name': u.get_full_name() or u.username,
                'email': u.email,
                'is_active': bool(getattr(u, 'is_active_user', u.is_active)),
                'restricted': u.pk in restricted,
                'total_posts': getattr(u, 'total_posts', 0),
                'removed_posts': getattr(u, 'removed_posts', 0),
                'reports_received': report_totals.get(u.pk, 0),
                'last_post_at': getattr(u, 'last_post_at', None),
            })

        if params.get('ordering') == '-reports':
            rows.sort(key=lambda r: -r['reports_received'])

        return paginator.get_paginated_response(rows)

    @action(detail=False, methods=['get'], url_path=r'creators/(?P<teacher_id>\d+)')
    def creator_detail(self, request, teacher_id=None):
        teacher = get_user_model().objects.filter(
            pk=teacher_id, role='teacher').first()
        if not teacher:
            return Response({'error': 'Teacher not found'}, status=404)

        lessons = feed_models.FeedLesson.objects.filter(teacher=teacher)
        reports_against = feed_models.FeedReport.objects.filter(
            Q(teacher=teacher)
            | Q(target_type='lesson', lesson__teacher=teacher)
        ).select_related('lesson')[:20]

        warnings = AuditLog.objects.filter(
            action='feed.warn_creator', changes__teacher_id=int(teacher_id))[:20]
        history = AuditLog.objects.filter(
            action__startswith='feed.', changes__teacher_id=int(teacher_id))[:20]

        return Response({
            'teacher': {
                'id': teacher.id,
                'name': teacher.get_full_name() or teacher.username,
                'email': teacher.email,
                'school_id': teacher.school_id,
                'is_active': bool(getattr(teacher, 'is_active_user', teacher.is_active)),
                'restricted': teacher.pk in get_feed_restricted_user_ids(),
            },
            'stats': {
                'total_posts': lessons.count(),
                'published': lessons.filter(status='approved').count(),
                'pending_review': lessons.filter(status='pending_review').count(),
                'hidden': lessons.filter(visibility='hidden').count(),
                'removed': lessons.filter(
                    Q(visibility='suspended') | Q(status='suspended')).count(),
                'reports_received': feed_models.FeedReport.objects.filter(
                    Q(teacher=teacher)
                    | Q(target_type='lesson', lesson__teacher=teacher)).count(),
            },
            'warnings': [{'note': w.changes.get('notes', ''), 'at': w.created_at}
                         for w in warnings],
            'moderation_history': [
                {'action': h.action, 'target': h.target_label,
                 'by': h.actor_name, 'at': h.created_at}
                for h in history],
            'recent_posts': [_post_row(l) for l in _annotate_posts(lessons)[:20]],
            'recent_reports': [_report_row(r) for r in reports_against],
        })

    def _apply_restriction(self, request, teacher_id, kind, notes=''):
        if kind == 'suspend_creator':
            ModerationService.suspend_teacher(teacher_id, request.user, reason=notes)
            write_audit_log(
                request, request.user, 'feed.creator_suspended',
                'user', teacher_id, '', {'notes': notes})
            return
        # restrict_creator: hide the creator's public content + block posting.
        feed_models.FeedLesson.objects.filter(
            teacher_id=teacher_id,
            visibility__in=['public', 'school_only']).update(
            visibility='hidden', updated_at=timezone.now())
        set_creator_restricted(int(teacher_id), True)
        write_audit_log(
            request, request.user, 'feed.creator_restricted',
            'user', int(teacher_id), '', {'notes': notes})

    @action(detail=False, methods=['post'],
            url_path=r'creators/(?P<teacher_id>\d+)/restrict')
    def restrict_creator(self, request, teacher_id=None):
        self._apply_restriction(
            request, teacher_id, 'restrict_creator',
            (request.data.get('notes') or '').strip())
        cache.delete('feed_supervisor_overview')
        return Response({'ok': True, 'restricted': True})

    @action(detail=False, methods=['post'],
            url_path=r'creators/(?P<teacher_id>\d+)/suspend')
    def suspend_creator(self, request, teacher_id=None):
        self._apply_restriction(
            request, teacher_id, 'suspend_creator',
            (request.data.get('notes') or '').strip())
        cache.delete('feed_supervisor_overview')
        return Response({'ok': True, 'suspended': True})

    @action(detail=False, methods=['post'],
            url_path=r'creators/(?P<teacher_id>\d+)/unrestrict')
    def unrestrict_creator(self, request, teacher_id=None):
        set_creator_restricted(int(teacher_id), False)
        write_audit_log(
            request, request.user, 'feed.creator_unrestricted',
            'user', int(teacher_id), '',
            {'notes': (request.data.get('notes') or '').strip()})
        return Response({'ok': True, 'restricted': False})

    # -- 5. School monitoring -------------------------------------------------

    @action(detail=False, methods=['get'])
    def schools(self, request):
        from apps.schools.models import School
        school_id = request.query_params.get('school_id')
        if school_id:
            school = School.objects.filter(pk=school_id).first()
            if not school:
                return Response({'error': 'School not found'}, status=404)
            lessons = feed_models.FeedLesson.objects.filter(school=school)
            teacher_counts = (
                lessons.values('teacher_id', 'teacher__first_name', 'teacher__last_name')
                .annotate(posts=Count('id')).order_by('-posts')[:10])
            return Response({
                'school': {'id': school.id, 'name': school.name},
                'stats': {
                    'total_posts': lessons.count(),
                    'active_creators': lessons.filter(
                        created_at__gte=timezone.now() - timezone.timedelta(days=30)
                    ).values('teacher').distinct().count(),
                    'reported': _annotate_posts(lessons).filter(
                        total_reports_count__gt=0).count(),
                    'removed': lessons.filter(
                        Q(visibility='suspended') | Q(status='suspended')).count(),
                },
                'top_teachers': [
                    {'id': t['teacher_id'],
                     'name': f"{t['teacher__first_name']} {t['teacher__last_name']}".strip(),
                     'posts': t['posts']} for t in teacher_counts],
                'recent_posts': [
                    _post_row(l) for l in _annotate_posts(lessons)[:15]],
            })

        rows = (
            feed_models.FeedLesson.objects.exclude(school=None)
            .values('school_id', 'school__name')
            .annotate(
                total_posts=Count('id'),
                active_creators=Count('teacher', distinct=True),
                removed=Count('id', filter=Q(visibility='suspended')),
            )
            .order_by('-total_posts'))
        return Response([
            {'id': r['school_id'], 'name': r['school__name'],
             'total_posts': r['total_posts'],
             'active_creators': r['active_creators'],
             'removed': r['removed']}
            for r in rows])

    # -- 8. Feed settings -----------------------------------------------------
    # NOTE: the method is named `feed_settings` (not `settings`) because a
    # method named `settings` would shadow APIView.settings (the DRF settings
    # accessor used by the exception handler), causing
    # "AttributeError: 'function' object has no attribute 'EXCEPTION_HANDLER'".
    @action(detail=False, methods=['get', 'put'], url_path='settings')
    def feed_settings(self, request):
        current = get_feed_policies()
        if request.method == 'GET':
            return Response(current)

        allowed = set(DEFAULT_FEED_POLICIES.keys())
        updates = {k: v for k, v in request.data.items() if k in allowed}
        if not updates:
            return Response(
                {'error': 'No valid setting keys provided'},
                status=http_status.HTTP_400_BAD_REQUEST)
        if 'moderation_mode' in updates and updates['moderation_mode'] not in MODERATION_MODES:
            return Response(
                {'error': f'moderation_mode must be one of {MODERATION_MODES}'},
                status=http_status.HTTP_400_BAD_REQUEST)
        merged = save_feed_policies(updates)
        write_audit_log(
            request, request.user, 'feed.settings_updated',
            'system_setting', FEED_POLICIES_KEY, 'Feed moderation policies',
            {'changed': sorted(updates.keys())})
        return Response(merged)
