"""
API views for the recommendation engine, interaction tracking, and blended feed.

These are new endpoints that extend the existing feed API with:
  - GET /api/feed/blended/          — 70/20/10 blended personalised feed
  - POST /api/feed/interactions/    — record a single interaction
  - POST /api/feed/interactions/batch/  — record multiple interactions
  - POST /api/feed/interactions/impressions/  — record feed impressions
  - POST /api/feed/interactions/watch/  — record watch progress
  - GET /api/feed/interactions/summary/  — get interaction summary
"""
from typing import List, Optional

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.feed.models_v2 import InteractionType
from apps.feed.serializers import LessonListSerializer
from apps.feed.pagination import FeedCursorPagination
from apps.feed.services.interaction_api_service import InteractionApiService
from apps.feed.services.personalized_recommendation_service import (
    PersonalizedRecommendationService,
)
from apps.feed.services.interest_scoring_service import InterestScoringService


class BlendedFeedView(APIView):
    """
    GET /api/feed/blended/

    TikTok/Reels-style personalised feed with session-stable ordering:

      - The full ranked id list is generated per refresh and cached under an
        opaque `feed_token` (30 min TTL). Scrolling pages never jumps or
        duplicates posts because pagination is a cursor (offset) into that
        stable snapshot.
      - Pull-to-refresh simply omits the token/cursor → a fresh snapshot is
        built (new posts included, ranking recalculated).

    Query params:
      - device_id: required for guest users
      - feed_token: opaque token returned by the previous response
      - cursor: offset into the snapshot (omit on first page / refresh)
      - page_size: 1-30 (default 12)
      - school_id: optional school filter
    """
    permission_classes = [AllowAny]
    MAX_PAGE_SIZE = 30

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        guest_device_id = request.query_params.get('device_id', '')
        school_id = request.query_params.get('school_id')
        feed_token = request.query_params.get('feed_token', '')
        raw_cursor = request.query_params.get('cursor')
        try:
            cursor = max(0, int(raw_cursor)) if raw_cursor is not None else None
        except (TypeError, ValueError):
            cursor = None
        try:
            page_size = min(
                self.MAX_PAGE_SIZE,
                max(1, int(request.query_params.get('page_size', '12'))),
            )
        except (TypeError, ValueError):
            page_size = 12

        if not user and not guest_device_id:
            # Anonymous user with no device_id — return trending feed
            from apps.feed.services.recommendation_service import RecommendationService
            qs = RecommendationService.get_guest_recommendations(
                strategy='trending', school_id=school_id
            )
            paginator = FeedCursorPagination()
            page_obj = paginator.paginate_queryset(qs, request, view=self)
            serializer = LessonListSerializer(
                page_obj, many=True, context={'request': request}
            )
            return paginator.get_paginated_response(serializer.data)

        # ── Resolve the ranked snapshot ──────────────────────────
        all_ids: Optional[List[int]] = None
        if cursor is not None:
            # Continuation of an existing session — reuse stored ordering.
            all_ids = PersonalizedRecommendationService.get_snapshot(
                user=user, guest_device_id=guest_device_id, token=feed_token,
            )
            if all_ids is not None and cursor > len(all_ids):
                cursor = len(all_ids)

        if all_ids is None:
            # First page or expired/invalid token → fresh ranked snapshot.
            # This also happens on pull-to-refresh, which intentionally
            # recalculates the recommendation order.
            feed_token, all_ids = PersonalizedRecommendationService.create_snapshot(
                user=user,
                guest_device_id=guest_device_id,
                school_id=school_id,
            )
            cursor = 0

        page_ids = all_ids[cursor:cursor + page_size]
        has_more = cursor + page_size < len(all_ids)
        next_cursor = (cursor + page_size) if has_more else None

        blended = PersonalizedRecommendationService.fetch_lessons_ordered(page_ids)

        # Record impressions for all returned lessons
        lesson_ids = [l.id for l in blended]
        InteractionApiService.record_impressions(
            user=user,
            guest_device_id=guest_device_id,
            lesson_ids=lesson_ids,
        )

        # Serialize
        serializer = LessonListSerializer(
            blended, many=True, context={'request': request}
        )

        # Inject guest-specific fields
        if not user:
            for lesson_data in serializer.data:
                from apps.feed.services.guest_service import GuestService
                lesson_data['is_liked'] = GuestService.is_liked(
                    guest_device_id, lesson_data['id']
                )
                lesson_data['is_saved'] = False
                lesson_data['is_following_teacher'] = False

        return Response({
            'results': serializer.data,
            'feed_token': feed_token,
            'cursor': cursor,
            'next_cursor': next_cursor,
            'has_more': has_more,
            'count': len(all_ids),
        })


@api_view(['POST'])
@permission_classes([AllowAny])
def record_interaction(request):
    """
    POST /api/feed/interactions/

    Record a single user interaction for recommendation tracking.

    Authenticated users: use JWT auth.
    Guest users: provide device_id in body.

    Body:
      { lesson_id: int, interaction_type: string, metadata?: object }
      + device_id (for guests)
    """
    user = request.user if request.user.is_authenticated else None
    guest_device_id = request.data.get('device_id', '')

    result = InteractionApiService.record(
        user=user,
        guest_device_id=guest_device_id,
        lesson_id=request.data.get('lesson_id'),
        interaction_type=request.data.get('interaction_type'),
        metadata=request.data.get('metadata', {}),
    )

    return Response(result, status=status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def record_batch_interactions(request):
    """
    POST /api/feed/interactions/batch/

    Record multiple interactions at once.

    Body:
      { interactions: [{ lesson_id, interaction_type, metadata? }] }
      + device_id (for guests)
    """
    user = request.user if request.user.is_authenticated else None
    guest_device_id = request.data.get('device_id', '')

    result = InteractionApiService.record_batch(
        user=user,
        guest_device_id=guest_device_id,
        interactions=request.data.get('interactions', []),
    )

    return Response(result)


@api_view(['POST'])
@permission_classes([AllowAny])
def record_impressions(request):
    """
    POST /api/feed/interactions/impressions/

    Record that a set of lessons were shown to the user.

    Body:
      { lesson_ids: [int, ...] }
      + device_id (for guests)
    """
    user = request.user if request.user.is_authenticated else None
    guest_device_id = request.data.get('device_id', '')

    result = InteractionApiService.record_impressions(
        user=user,
        guest_device_id=guest_device_id,
        lesson_ids=request.data.get('lesson_ids', []),
    )

    return Response(result)


@api_view(['POST'])
@permission_classes([AllowAny])
def record_watch_progress(request):
    """
    POST /api/feed/interactions/watch/

    Record watch progress for a video.

    Body:
      { lesson_id: int, watch_seconds: int, duration_seconds: int, resume_position?: int }
      + device_id (for guests)
    """
    user = request.user if request.user.is_authenticated else None
    guest_device_id = request.data.get('device_id', '')

    result = InteractionApiService.record_watch_progress(
        user=user,
        guest_device_id=guest_device_id,
        lesson_id=request.data.get('lesson_id'),
        watch_seconds=request.data.get('watch_seconds', 0),
        duration_seconds=request.data.get('duration_seconds', 0),
        resume_position=request.data.get('resume_position', 0),
    )

    return Response(result)


class InteractionSummaryView(APIView):
    """
    GET /api/feed/interactions/summary/

    Get a summary of the user's interactions for profile display.

    Query params:
      - device_id: required for guest users
    """
    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        guest_device_id = request.query_params.get('device_id', '')

        summary = InteractionApiService.get_interaction_summary(
            user=user,
            guest_device_id=guest_device_id,
        )

        return Response(summary)


class InterestScoresView(APIView):
    """
    GET /api/feed/interests/

    Get the user's current interest scores across all domains.

    Query params:
      - device_id: required for guest users
      - domain: optional filter (subject, teacher, level, class_obj, tag)
    """
    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        guest_device_id = request.query_params.get('device_id', '')
        domain = request.query_params.get('domain')
        limit = int(request.query_params.get('limit', '20'))

        interests = InterestScoringService.get_top_interest_ids(
            user=user,
            guest_device_id=guest_device_id,
            domain=domain,
            limit=limit,
        )

        should_prioritize_behavioural = InterestScoringService.should_prioritize_behavioural(
            user=user,
            guest_device_id=guest_device_id,
        )

        return Response({
            'interests': interests,
            'should_prioritize_behavioural': should_prioritize_behavioural,
        })
