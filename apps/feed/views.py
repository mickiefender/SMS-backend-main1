"""
DRF viewsets and API views for the Alara Learning Feed.

All business logic is delegated to services. Views are thin.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.feed import models, serializers
from apps.feed.pagination import (
    CommentCursorPagination, FeedCursorPagination, TrendingCursorPagination,
)
from apps.feed.permissions import (
    IsGuestReadOnly, IsTeacher, IsTeacherOwner, IsOwnerOrAdmin,
    IsCommentOwnerOrAdmin, IsModerator,
)
from apps.feed.services.feed_service import FeedService
from apps.feed.services.lesson_service import LessonService
from apps.feed.services.recommendation_service import RecommendationService
from apps.feed.services.search_service import SearchService
from apps.feed.services.analytics_service import AnalyticsService
from apps.feed.services.notification_service import NotificationService
from apps.feed.services.feed_policy_service import (
    FeedPolicyError, assert_can_comment, assert_can_report,
)
from apps.feed.services.moderation_service import ModerationService
from apps.feed.services.upload_service import UploadService
from apps.feed.models_v2 import InteractionType as InteractionTypeEnum
from apps.feed.services.interest_scoring_service import InterestScoringService


class FeedLessonViewSet(viewsets.ModelViewSet):
    """
    Lessons endpoint:
      GET  /api/feed/lesson/           (public / school-only per user)
      POST /api/feed/lesson/           (teachers)
      GET  /api/feed/lesson/{id}/
      PATCH /api/feed/lesson/{id}/     (owner / admin)
      DELETE /api/feed/lesson/{id}/    (owner / admin)
      POST /api/feed/lesson/{id}/like/
      POST /api/feed/lesson/{id}/save/
      POST /api/feed/lesson/{id}/watch/
      POST /api/feed/lesson/{id}/share/
      POST /api/feed/lesson/{id}/download/
    """
    pagination_class = FeedCursorPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['published_at', 'trending_score', 'created_at']

    def get_queryset(self):
        return FeedService.visible_lessons(
            self.request.user,
            school_id=self.request.query_params.get('school_id')
        )

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return serializers.LessonWriteSerializer
        if self.action == 'retrieve':
            return serializers.LessonDetailSerializer
        return serializers.LessonListSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacher()]
        if self.action in ['like', 'save', 'watch', 'share', 'download']:
            return [IsAuthenticated()]
        return [IsGuestReadOnly()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        if request.user.role != 'teacher':
            raise PermissionDenied('Only teachers can upload lessons.')
        # Feed Supervisor enforcement: restricted creators cannot post.
        from apps.feed.supervisor_views import is_feed_restricted
        if is_feed_restricted(request.user):
            raise PermissionDenied(
                'Your Feed posting privileges are currently restricted by a platform moderator.'
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lesson = LessonService.create_lesson(request.user, serializer.validated_data)
        output = serializers.LessonDetailSerializer(lesson, context={'request': request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not IsTeacherOwner().has_object_permission(request, self, instance):
            raise PermissionDenied('You can only edit your own lessons.')
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lesson = LessonService.update_lesson(instance, serializer.validated_data)
        output = serializers.LessonDetailSerializer(lesson, context={'request': request})
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not IsTeacherOwner().has_object_permission(request, self, instance):
            raise PermissionDenied('You can only delete your own lessons.')
        LessonService.delete_lesson(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if not LessonService.can_view_lesson(instance, request.user):
            raise PermissionDenied('You do not have permission to view this lesson.')
        if request.user and request.user.is_authenticated:
            AnalyticsService.track_view(instance, request.user)
        else:
            AnalyticsService.track_view(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        lesson = self.get_object()
        user = request.user
        like_qs = models.FeedLike.objects.filter(user=user, lesson=lesson)
        if like_qs.exists():
            like_qs.delete()
            AnalyticsService.track_unlike(lesson)
            InterestScoringService.record_interaction(
                user=user, lesson_id=lesson.id,
                interaction_type=InteractionTypeEnum.UNLIKE,
            )
            return Response({'liked': False, 'like_count': lesson.like_count})
        models.FeedLike.objects.create(user=user, lesson=lesson)
        AnalyticsService.track_like(lesson)
        InterestScoringService.record_interaction(
            user=user, lesson_id=lesson.id,
            interaction_type=InteractionTypeEnum.LIKE,
        )
        return Response({'liked': True, 'like_count': lesson.like_count})

    @action(detail=True, methods=['post'])
    def save(self, request, pk=None):
        lesson = self.get_object()
        user = request.user
        save_qs = models.FeedSave.objects.filter(user=user, lesson=lesson)
        if save_qs.exists():
            save_qs.delete()
            AnalyticsService.track_unsave(lesson)
            InterestScoringService.record_interaction(
                user=user, lesson_id=lesson.id,
                interaction_type=InteractionTypeEnum.UNSAVE,
            )
            return Response({'saved': False, 'save_count': lesson.save_count})
        models.FeedSave.objects.create(
            user=user,
            lesson=lesson,
            offline_download_metadata=request.data.get('offline_metadata')
        )
        AnalyticsService.track_save(lesson)
        InterestScoringService.record_interaction(
            user=user, lesson_id=lesson.id,
            interaction_type=InteractionTypeEnum.SAVE,
        )
        return Response({'saved': True, 'save_count': lesson.save_count})

    @action(detail=True, methods=['post'])
    def watch(self, request, pk=None):
        lesson = self.get_object()
        serializer = serializers.WatchEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        history = LessonService.record_watch(
            user=request.user,
            lesson=lesson,
            watch_seconds=serializer.validated_data['watch_seconds'],
            resume_position=serializer.validated_data.get('resume_position', 0),
        )
        # Determine if this is a completion or progress update
        watch_seconds = serializer.validated_data['watch_seconds']
        duration = lesson.duration_seconds or lesson.video_duration or 0
        completion_pct = (watch_seconds / duration * 100) if duration > 0 else 0
        if completion_pct >= 90:
            interaction_type = InteractionTypeEnum.WATCH_COMPLETE
        else:
            interaction_type = InteractionTypeEnum.WATCH_UPDATE
        InterestScoringService.record_interaction(
            user=request.user, lesson_id=lesson.id,
            interaction_type=interaction_type,
            metadata={
                'watch_seconds': watch_seconds,
                'duration_seconds': duration,
                'completion_percentage': round(completion_pct, 1),
            },
        )
        return Response(serializers.WatchHistorySerializer(history).data)

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        lesson = self.get_object()
        AnalyticsService.track_share(lesson)
        InterestScoringService.record_interaction(
            user=request.user, lesson_id=lesson.id,
            interaction_type=InteractionTypeEnum.SHARE,
        )
        return Response({'share_count': lesson.share_count})

    @action(detail=True, methods=['post'])
    def download(self, request, pk=None):
        lesson = self.get_object()
        AnalyticsService.track_download(lesson)
        return Response({'download_count': lesson.download_count})


class FeedView(APIView):
    """
    GET /api/feed/
    Generic public / personalized feed.
    Query params: strategy (trending|latest|recommended), school_id
    """
    permission_classes = [AllowAny]
    pagination_class = FeedCursorPagination

    def get(self, request):
        strategy = request.query_params.get('strategy', 'trending')
        school_id = request.query_params.get('school_id')
        qs = FeedService.get_feed(request.user, strategy=strategy, school_id=school_id)
        if strategy in ('recommended', 'personalized'):
            paginator = self.pagination_class()
            paginator.ordering = (
                ('-rec_score', '-published_at', '-pk')
                if request.user and request.user.is_authenticated
                else ('-trending_score', '-published_at', '-pk')
            )
        elif strategy == 'trending':
            paginator = TrendingCursorPagination()
        else:
            paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = serializers.LessonListSerializer(
            page, many=True, context={'request': request}
        )
        return paginator.get_paginated_response(serializer.data)


class RecommendedFeedView(APIView):
    """GET /api/feed/recommended/"""
    permission_classes = [IsAuthenticated]
    pagination_class = FeedCursorPagination

    def get(self, request):
        school_id = request.query_params.get('school_id')
        qs = RecommendationService.get_recommendations_for_user(
            request.user, strategy='personalized', school_id=school_id
        )
        paginator = self.pagination_class()
        paginator.ordering = ('-rec_score', '-published_at', '-pk')
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = serializers.LessonListSerializer(
            page, many=True, context={'request': request}
        )
        return paginator.get_paginated_response(serializer.data)


class TrendingFeedView(APIView):
    """GET /api/feed/trending/"""
    permission_classes = [AllowAny]
    pagination_class = TrendingCursorPagination

    def get(self, request):
        school_id = request.query_params.get('school_id')
        qs = RecommendationService.get_guest_recommendations(
            strategy='trending', school_id=school_id
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = serializers.LessonListSerializer(
            page, many=True, context={'request': request}
        )
        return paginator.get_paginated_response(serializer.data)


class LatestFeedView(APIView):
    """GET /api/feed/latest/"""
    permission_classes = [AllowAny]
    pagination_class = FeedCursorPagination

    def get(self, request):
        school_id = request.query_params.get('school_id')
        qs = RecommendationService.get_guest_recommendations(
            strategy='latest', school_id=school_id
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = serializers.LessonListSerializer(
            page, many=True, context={'request': request}
        )
        return paginator.get_paginated_response(serializer.data)


class SearchFeedView(APIView):
    """GET /api/feed/search/?q=..."""
    permission_classes = [AllowAny]
    pagination_class = FeedCursorPagination

    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if not q:
            raise ValidationError({'q': 'Search query is required.'})
        qs = SearchService.search(
            q,
            user=request.user if request.user.is_authenticated else None,
            school_id=request.query_params.get('school_id'),
            level_id=request.query_params.get('level_id'),
            class_id=request.query_params.get('class_id'),
            subject_id=request.query_params.get('subject_id'),
            teacher_id=request.query_params.get('teacher_id'),
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = serializers.LessonListSerializer(
            page, many=True, context={'request': request}
        )
        return paginator.get_paginated_response(serializer.data)


class TeacherFeedView(APIView):
    """GET /api/feed/teacher/{id}/"""
    permission_classes = [AllowAny]
    pagination_class = FeedCursorPagination

    def get(self, request, pk):
        data = FeedService.get_teacher_profile(pk, request.user)
        lessons = data['lessons']
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(lessons, request, view=self)
        lesson_serializer = serializers.LessonListSerializer(
            page, many=True, context={'request': request}
        )
        paginated_response = paginator.get_paginated_response(lesson_serializer.data)
        lesson_results = paginated_response.data.get('results', [])
        profile_picture_url = None
        try:
            profile_pic = getattr(data['profile'].user, 'profile_picture', None)
            if profile_pic:
                profile_picture_url = profile_pic.display_url
        except Exception:
            pass

        response_data = {
            'teacher': {
                'id': data['profile'].user_id,
                'name': data['profile'].user.get_full_name(),
                'profile_picture': profile_picture_url,
                'bio': data['profile'].bio,
                'specialization': data['profile'].specialization,
                'follower_count': data['follower_count'],
                'is_following': data['is_following'],
            },
            'lessons': lesson_results,
            'results': lesson_results,
            'next': paginated_response.data.get('next'),
            'previous': paginated_response.data.get('previous'),
            'count': paginated_response.data.get('count'),
        }
        return Response(response_data)


class TeacherFollowView(APIView):
    """POST /api/feed/teacher/{id}/follow/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        relation, created = models.TeacherFollower.objects.get_or_create(
            user=request.user, teacher_id=pk
        )
        if created:
            NotificationService.notify_new_follower(relation)
            InterestScoringService.record_interaction(
                user=request.user, lesson_id=None,
                interaction_type=InteractionTypeEnum.FOLLOW_TEACHER,
                metadata={'teacher_id': pk},
            )
        return Response({'following': True})

    def delete(self, request, pk):
        models.TeacherFollower.objects.filter(user=request.user, teacher_id=pk).delete()
        InterestScoringService.record_interaction(
            user=request.user, lesson_id=None,
            interaction_type=InteractionTypeEnum.UNFOLLOW_TEACHER,
            metadata={'teacher_id': pk},
        )
        return Response({'following': False})


class FeedCommentViewSet(viewsets.ModelViewSet):
    """
    Comments endpoint:
      GET  /api/feed/lesson/{lesson_id}/comments/
      POST /api/feed/lesson/{id}/comment/
    """
    pagination_class = CommentCursorPagination
    filter_backends = []

    def get_queryset(self):
        lesson_id = self.kwargs.get('lesson_id') or self.request.query_params.get('lesson_id')
        if lesson_id:
            return models.FeedComment.objects.filter(
                lesson_id=lesson_id,
                parent__isnull=True
            ).prefetch_related('replies')
        return models.FeedComment.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return serializers.CommentCreateSerializer
        return serializers.FeedCommentSerializer

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsCommentOwnerOrAdmin()]
        return [IsGuestReadOnly()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        # Feed Supervisor policy: comments can be globally disabled.
        try:
            assert_can_comment()
        except FeedPolicyError as exc:
            raise PermissionDenied(str(exc))
        lesson_id = self.kwargs.get('lesson_id') or request.query_params.get('lesson_id')
        lesson = models.FeedLesson.objects.get(pk=lesson_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent = serializer.validated_data.get('parent')
        comment = models.FeedComment.objects.create(
            lesson=lesson,
            user=request.user,
            parent=parent,
            body=serializer.validated_data['body'],
        )
        AnalyticsService.track_comment(lesson)
        output = serializers.FeedCommentSerializer(comment, context={'request': request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def like(self, request, lesson_id=None, pk=None):
        comment = self.get_object()
        like_qs = models.CommentLike.objects.filter(user=request.user, comment=comment)
        if like_qs.exists():
            like_qs.delete()
            return Response({'liked': False, 'like_count': comment.like_count})
        models.CommentLike.objects.create(user=request.user, comment=comment)
        return Response({'liked': True, 'like_count': comment.like_count})


class LearningProfileView(APIView):
    """
    GET/PUT /api/feed/learning-profile/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, _ = models.LearningProfile.objects.get_or_create(user=request.user)
        serializer = serializers.LearningProfileSerializer(profile)
        return Response(serializer.data)

    def put(self, request):
        profile, _ = models.LearningProfile.objects.get_or_create(user=request.user)
        serializer = serializers.LearningProfileSerializer(
            profile, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Seed interest scores from updated preferences
        subject_ids = serializer.instance.preferred_subject_ids or []
        InterestScoringService.seed_from_onboarding(
            user=request.user,
            subject_ids=subject_ids,
            level_id=serializer.instance.preferred_level_id,
            class_id=serializer.instance.preferred_class_id,
        )

        RecommendationService.invalidate_user_cache(request.user)
        return Response(serializer.data)


class WatchHistoryView(APIView):
    """
    GET /api/feed/watch-history/
    """
    permission_classes = [IsAuthenticated]
    pagination_class = FeedCursorPagination

    def get(self, request):
        qs = models.WatchHistory.objects.filter(user=request.user)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = serializers.WatchHistorySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ContinueWatchingView(APIView):
    """
    GET /api/feed/continue-watching/
    """
    permission_classes = [IsAuthenticated]
    pagination_class = FeedCursorPagination

    def get(self, request):
        qs = RecommendationService.get_continue_watching(request.user)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = serializers.LessonListSerializer(
            page, many=True, context={'request': request}
        )
        return paginator.get_paginated_response(serializer.data)


class FeedNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/feed/notifications/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.FeedNotificationSerializer
    pagination_class = FeedCursorPagination

    def get_queryset(self):
        return models.FeedNotification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])
        return Response({'status': 'marked read'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({'status': 'all marked read'})


class FeedReportViewSet(viewsets.ModelViewSet):
    """
    POST /api/feed/report/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.FeedReportSerializer
    pagination_class = FeedCursorPagination

    def get_queryset(self):
        if self.request.user.role in ['super_admin', 'school_admin', 'academic_admin']:
            return models.FeedReport.objects.all()
        return models.FeedReport.objects.filter(reporter=self.request.user)

    def create(self, request, *args, **kwargs):
        # Feed Supervisor policy: reporting can be globally disabled.
        try:
            assert_can_report()
        except FeedPolicyError as exc:
            raise PermissionDenied(str(exc))
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target_id = data.get('lesson_id') or data.get('comment_id') or data.get('teacher_id')
        report = ModerationService.create_report(
            reporter=request.user,
            target_type=data['target_type'],
            target_id=target_id,
            reason=data['reason'],
            description=data.get('description', ''),
        )
        output = serializers.FeedReportSerializer(report)
        return Response(output.data, status=status.HTTP_201_CREATED)


class ModerationViewSet(viewsets.ViewSet):
    """
    Moderation actions:
      POST /api/feed/moderation/lesson/{id}/approve/
      POST /api/feed/moderation/lesson/{id}/suspend/
      POST /api/feed/moderation/lesson/{id}/hide/
      POST /api/feed/moderation/report/{id}/resolve/
      POST /api/feed/moderation/teacher/{id}/suspend/
    """
    permission_classes = [IsModerator]

    @action(detail=False, methods=['post'], url_path=r'lesson/(?P<lesson_id>\d+)/approve')
    def approve_lesson(self, request, lesson_id=None):
        lesson = models.FeedLesson.objects.get(pk=lesson_id)
        ModerationService.approve_lesson(lesson, request.user)
        return Response({'status': 'approved'})

    @action(detail=False, methods=['post'], url_path=r'lesson/(?P<lesson_id>\d+)/suspend')
    def suspend_lesson(self, request, lesson_id=None):
        lesson = models.FeedLesson.objects.get(pk=lesson_id)
        reason = request.data.get('reason', '')
        ModerationService.suspend_lesson(lesson, request.user, reason=reason)
        return Response({'status': 'suspended'})

    @action(detail=False, methods=['post'], url_path=r'lesson/(?P<lesson_id>\d+)/hide')
    def hide_lesson(self, request, lesson_id=None):
        lesson = models.FeedLesson.objects.get(pk=lesson_id)
        ModerationService.hide_lesson(lesson)
        return Response({'status': 'hidden'})

    @action(detail=False, methods=['post'], url_path=r'report/(?P<report_id>\d+)/resolve')
    def resolve_report(self, request, report_id=None):
        report = models.FeedReport.objects.get(pk=report_id)
        ModerationService.resolve_report(report, request.user, request.data.get('resolution', ''))
        return Response({'status': 'resolved'})

    @action(detail=False, methods=['post'], url_path=r'teacher/(?P<teacher_id>\d+)/suspend')
    def suspend_teacher(self, request, teacher_id=None):
        reason = request.data.get('reason', '')
        ModerationService.suspend_teacher(teacher_id, request.user, reason=reason)
        return Response({'status': 'teacher suspended'})


class ReferenceLevelsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedAcademicLevel.objects.filter(is_active=True)
        serializer = serializers.FeedAcademicLevelSerializer(qs, many=True)
        return Response(serializer.data)


class ReferenceClassesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedAcademicClass.objects.filter(is_active=True)
        level_id = request.query_params.get('level_id')
        if level_id:
            qs = qs.filter(level_id=level_id)
        serializer = serializers.FeedAcademicClassSerializer(qs, many=True)
        return Response(serializer.data)


class ReferenceSubjectsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedSubject.objects.filter(is_active=True)
        serializer = serializers.FeedSubjectSerializer(qs, many=True)
        return Response(serializer.data)


class ReferenceTagsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedTag.objects.all()
        serializer = serializers.FeedTagSerializer(qs, many=True)
        return Response(serializer.data)


class ReferenceContentTypesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedContentType.objects.filter(is_active=True)
        serializer = serializers.FeedContentTypeSerializer(qs, many=True)
        return Response(serializer.data)


class ReferenceDifficultyLevelsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedDifficultyLevel.objects.filter(is_active=True)
        serializer = serializers.FeedDifficultyLevelSerializer(qs, many=True)
        return Response(serializer.data)


class ReferenceCurriculaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedCurriculum.objects.filter(is_active=True)
        serializer = serializers.FeedCurriculumSerializer(qs, many=True)
        return Response(serializer.data)


class ReferenceLearningObjectivesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedLearningObjective.objects.filter(is_active=True)
        serializer = serializers.FeedLearningObjectiveSerializer(qs, many=True)
        return Response(serializer.data)


class ReferenceVisibilityScopesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = models.FeedVisibilityScope.objects.all()
        serializer = serializers.FeedVisibilityScopeSerializer(qs, many=True)
        return Response(serializer.data)
