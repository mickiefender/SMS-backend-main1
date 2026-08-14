"""
Guest learner service — persists unauthenticated learner profiles in the database.

Previously guest data was stored in Redis cache and was lost on cache expiry.
Now uses the GuestLearner model for permanent storage so preferences, likes,
and activity survive across sessions.

Requires the feed_guestlearner and feed_guestlike tables (see sql/guest_learner_schema.sql).
"""
from typing import List, Optional
from decimal import Decimal
from django.utils import timezone as django_timezone

from apps.feed.models import (
    GuestLearner,
    FeedLesson,
)
from apps.feed.services.recommendation_service import RecommendationService
from apps.feed.services.interest_scoring_service import InterestScoringService


# We reference the GuestLike model dynamically because it's defined in the SQL
# schema but not as a Django model. The GuestLearner model stores liked_lesson_ids
# as JSONB and we also have a feed_guestlike table managed by triggers.
# For the Python service, we use the GuestLearner.liked_lesson_ids JSONB field
# for reads and raw SQL for writes (to keep triggers in sync).

class GuestService:

    # ─── Profile ─────────────────────────────────────────────────

    @staticmethod
    def create_guest_profile(
        device_id: str,
        name: str,
        level_id: int,
        class_id: int,
        subject_ids: List[int],
    ) -> dict:
        """Create or update a guest learner profile in the database."""
        from django.db import transaction

        learner, created = GuestLearner.objects.update_or_create(
            device_id=device_id,
            defaults={
                'name': name,
                'level_id': level_id,
                'class_obj_id': class_id,
                'subject_ids': subject_ids,
                'onboarding_completed_at': django_timezone.now(),
            },
        )

        # Sync M2M subjects
        if subject_ids:
            learner.subjects.set(subject_ids)

        return GuestService._profile_to_dict(learner)

    @staticmethod
    def get_guest_profile(device_id: str) -> Optional[dict]:
        """Retrieve guest profile from the database."""
        try:
            learner = GuestLearner.objects.get(device_id=device_id)
            return GuestService._profile_to_dict(learner)
        except GuestLearner.DoesNotExist:
            return None

    @staticmethod
    def _profile_to_dict(learner: GuestLearner) -> dict:
        return {
            'device_id': str(learner.device_id),
            'name': learner.name,
            'level_id': learner.level_id,
            'class_obj_id': learner.class_obj_id,
            'subject_ids': learner.subject_ids,
            'liked_lesson_ids': learner.liked_lesson_ids,
            'onboarding_completed_at': (
                learner.onboarding_completed_at.isoformat()
                if learner.onboarding_completed_at else None
            ),
            'created_at': learner.created_at.isoformat(),
            'updated_at': learner.updated_at.isoformat(),
        }

    # ─── Feed ────────────────────────────────────────────────────

    @staticmethod
    def get_feed_for_guest(
        device_id: str,
        strategy: str = 'guest_personalized',
    ):
        """Return lessons matching the guest's academic level, class, and subjects.

        Falls back to progressively wider audiences so guests never see an
        empty feed when there are no published lessons for their exact
        level/class/subject combination:
          level+class+subject → level+class → level → subject → trending
        """
        try:
            learner = GuestLearner.objects.get(device_id=device_id)
        except GuestLearner.DoesNotExist:
            return RecommendationService.get_guest_recommendations(strategy='trending')

        level_id = learner.level_id
        class_id = learner.class_obj_id
        subject_ids = learner.subject_ids or []

        base = RecommendationService._base_public_queryset()

        def _personalized(level=None, cls=None, subjects=None):
            qs = base
            if level:
                qs = qs.filter(level_id=level)
            if cls:
                qs = qs.filter(class_obj_id=cls)
            if subjects:
                qs = qs.filter(subject_id__in=subjects)
            return qs

        # Progressive relaxation: pick the most specific filter that has content.
        candidates = None
        if level_id and class_id and subject_ids:
            candidate = _personalized(level_id, class_id, subject_ids)
            if candidate.exists():
                candidates = candidate
        if candidates is None and level_id and class_id:
            candidate = _personalized(level_id, class_id, None)
            if candidate.exists():
                candidates = candidate
        if candidates is None and level_id and subject_ids:
            candidate = _personalized(level_id, None, subject_ids)
            if candidate.exists():
                candidates = candidate
        if candidates is None and level_id:
            candidate = _personalized(level_id, None, None)
            if candidate.exists():
                candidates = candidate
        if candidates is None and subject_ids:
            candidate = _personalized(None, None, subject_ids)
            if candidate.exists():
                candidates = candidate

        if candidates is None:
            # No published lessons match the guest's preferences — show
            # trending public content instead of an empty feed.
            return RecommendationService.get_guest_recommendations(strategy='trending')

        from django.db.models import F
        from decimal import Decimal

        qs = candidates.annotate(
            rec_score=(
                F('trending_score') * Decimal('0.5') +
                RecommendationService._engagement_score() * Decimal('0.5')
            )
        ).order_by('-rec_score', '-published_at')

        return qs

    # ─── Likes (DB + trigger-safe) ───────────────────────────────

    @staticmethod
    def toggle_like(device_id: str, lesson_id: int) -> dict:
        """Toggle like on a lesson for a guest user."""
        from django.db import connection

        # Check if the guest learner exists
        try:
            learner = GuestLearner.objects.get(device_id=device_id)
        except GuestLearner.DoesNotExist:
            return {'liked': False, 'like_count': 0}

        with connection.cursor() as cursor:
            # Check if already liked using the feed_guestlike table
            cursor.execute(
                "SELECT id FROM feed_guestlike WHERE device_id = %s AND lesson_id = %s",
                [device_id, lesson_id],
            )
            existing = cursor.fetchone()

            if existing:
                # Unlike — delete the row; trigger updates liked_lesson_ids JSONB
                cursor.execute(
                    "DELETE FROM feed_guestlike WHERE device_id = %s AND lesson_id = %s",
                    [device_id, lesson_id],
                )
                liked = False
            else:
                # Like — insert; trigger updates liked_lesson_ids JSONB
                cursor.execute(
                    "INSERT INTO feed_guestlike (device_id, lesson_id) VALUES (%s, %s)",
                    [device_id, lesson_id],
                )
                liked = True

        # Get the current lesson like_count (from FeedLesson trigger-maintained counter)
        try:
            lesson = FeedLesson.objects.get(pk=lesson_id)
            like_count = lesson.like_count
        except FeedLesson.DoesNotExist:
            like_count = 0

        return {'liked': liked, 'like_count': like_count}

    @staticmethod
    def is_liked(device_id: str, lesson_id: int) -> bool:
        """Check if a guest has liked a lesson."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM feed_guestlike WHERE device_id = %s AND lesson_id = %s",
                [device_id, lesson_id],
            )
            return cursor.fetchone() is not None

    @staticmethod
    def get_liked_lesson_ids(device_id: str) -> List[int]:
        """Get list of lesson IDs liked by this guest."""
        try:
            learner = GuestLearner.objects.get(device_id=device_id)
            return learner.liked_lesson_ids or []
        except GuestLearner.DoesNotExist:
            return []
