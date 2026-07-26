"""
API views for unauthenticated (guest) learners.

These endpoints are used when a user skips login:
  - POST /api/feed/guest/onboard/        — create learner profile
  - GET  /api/feed/guest/feed/           — personalised feed for guest
  - POST /api/feed/guest/feed/           — feed with device_id in body
  - GET  /api/feed/guest/profile/        — get guest profile
"""
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.feed.services.guest_service import GuestService
from apps.feed.services.interest_scoring_service import InterestScoringService
from apps.feed.pagination import FeedCursorPagination
from apps.feed.serializers import LessonListSerializer


class GuestOnboardView(APIView):
    """
    POST /api/feed/guest/onboard/

    Body:
      device_id: str (UUID generated client-side)
      name: str
      level_id: int
      class_id: int
      subject_ids: List[int]

    Returns the guest profile.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        device_id = request.data.get('device_id')
        name = request.data.get('name')
        level_id = request.data.get('level_id')
        class_id = request.data.get('class_id')
        subject_ids = request.data.get('subject_ids', [])

        if not device_id or not name or not level_id or not class_id:
            return Response(
                {'error': 'device_id, name, level_id, and class_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(subject_ids, list):
            return Response(
                {'error': 'subject_ids must be a list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate references exist
        from apps.feed.models import FeedAcademicLevel, FeedAcademicClass, FeedSubject
        try:
            FeedAcademicLevel.objects.get(pk=level_id, is_active=True)
        except FeedAcademicLevel.DoesNotExist:
            return Response({'error': 'Invalid level_id.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            FeedAcademicClass.objects.get(pk=class_id, is_active=True)
        except FeedAcademicClass.DoesNotExist:
            return Response({'error': 'Invalid class_id.'}, status=status.HTTP_400_BAD_REQUEST)

        valid_subject_count = FeedSubject.objects.filter(
            pk__in=subject_ids, is_active=True
        ).count()
        if valid_subject_count != len(subject_ids):
            return Response({'error': 'One or more subject_ids are invalid.'}, status=status.HTTP_400_BAD_REQUEST)

        # Seed interest scores from onboarding preferences
        InterestScoringService.seed_from_onboarding(
            guest_device_id=device_id,
            subject_ids=subject_ids,
            level_id=level_id,
            class_id=class_id,
        )

        profile = GuestService.create_guest_profile(
            device_id=device_id,
            name=name,
            level_id=level_id,
            class_id=class_id,
            subject_ids=subject_ids,
        )

        return Response(profile, status=status.HTTP_201_CREATED)


class GuestProfileView(APIView):
    """
    GET /api/feed/guest/profile/?device_id=xxx
    """
    permission_classes = [AllowAny]

    def get(self, request):
        device_id = request.query_params.get('device_id')
        if not device_id:
            return Response({'error': 'device_id query parameter is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        profile = GuestService.get_guest_profile(device_id)
        if not profile:
            return Response({'error': 'Guest profile not found.'},
                            status=status.HTTP_404_NOT_FOUND)

        return Response(profile)


class GuestFeedView(APIView):
    """
    GET /api/feed/guest/feed/?device_id=xxx
    POST /api/feed/guest/feed/  (with device_id in body)
    """
    permission_classes = [AllowAny]
    pagination_class = FeedCursorPagination

    def get(self, request):
        device_id = request.query_params.get('device_id')
        if not device_id:
            return Response({'error': 'device_id query parameter is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        return self._get_feed(request, device_id)

    def post(self, request):
        device_id = request.data.get('device_id')
        if not device_id:
            return Response({'error': 'device_id is required in body.'},
                            status=status.HTTP_400_BAD_REQUEST)

        return self._get_feed(request, device_id)

    def _get_feed(self, request, device_id):
        qs = GuestService.get_feed_for_guest(device_id)

        paginator = self.pagination_class()
        paginator.ordering = ('-rec_score', '-published_at', '-pk')
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = LessonListSerializer(
            page, many=True, context={'request': request}
        )

        # Inject is_liked for guest
        for lesson_data in serializer.data:
            lesson_data['is_liked'] = GuestService.is_liked(
                device_id, lesson_data['id']
            )
            lesson_data['is_saved'] = False
            lesson_data['is_following_teacher'] = False

        return paginator.get_paginated_response(serializer.data)


class GuestLikeView(APIView):
    """
    POST /api/feed/guest/like/
    Body: { device_id: str, lesson_id: int }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        device_id = request.data.get('device_id')
        lesson_id = request.data.get('lesson_id')

        if not device_id or not lesson_id:
            return Response(
                {'error': 'device_id and lesson_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = GuestService.toggle_like(device_id, lesson_id)
        return Response(result)
