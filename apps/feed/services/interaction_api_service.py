"""
API-level service for recording and bulk tracking user interactions.

This bridges the raw API requests to the InterestScoringService and handles
the mapping between user/guest identification.
"""
import logging
from typing import Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.feed.models_v2 import InteractionType
from apps.feed.services.interest_scoring_service import InterestScoringService
from apps.feed.services.personalized_recommendation_service import (
    PersonalizedRecommendationService,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class InteractionApiService:

    @staticmethod
    def record(
        user=None,
        guest_device_id: str = '',
        lesson_id: int = None,
        interaction_type: str = None,
        metadata: dict = None,
    ) -> dict:
        """
        Record a single interaction.

        Returns a dict with success status and optional context for the client.
        """
        if not lesson_id:
            return {'success': False, 'error': 'lesson_id is required'}

        success = InterestScoringService.record_interaction(
            user=user,
            guest_device_id=guest_device_id,
            lesson_id=lesson_id,
            interaction_type=interaction_type,
            metadata=metadata or {},
        )

        # Invalidate feed caches so the next request reflects updated interests
        if success:
            PersonalizedRecommendationService.invalidate_caches(
                user=user, guest_device_id=guest_device_id
            )

        return {'success': success}

    @staticmethod
    def record_batch(
        user=None,
        guest_device_id: str = '',
        interactions: List[Dict] = None,
    ) -> dict:
        """
        Record multiple interactions in a single request.

        interactions: list of {lesson_id, interaction_type, metadata?}
        """
        if not interactions:
            return {'success': False, 'error': 'interactions list is required'}

        count = 0
        for item in interactions:
            try:
                ok = InterestScoringService.record_interaction(
                    user=user,
                    guest_device_id=guest_device_id,
                    lesson_id=item.get('lesson_id'),
                    interaction_type=item.get('interaction_type'),
                    metadata=item.get('metadata', {}),
                )
                if ok:
                    count += 1
            except Exception as e:
                logger.warning("Failed to record batch interaction: %s", e)

        # Invalidate caches if any were recorded
        if count > 0:
            PersonalizedRecommendationService.invalidate_caches(
                user=user, guest_device_id=guest_device_id
            )

        return {'success': True, 'recorded_count': count}

    @staticmethod
    def record_impressions(
        user=None,
        guest_device_id: str = '',
        lesson_ids: List[int] = None,
    ) -> dict:
        """
        Record that a list of lessons were shown to the user (impressions).

        This is called when the feed is loaded so the recommendation engine
        knows which content the user has seen.
        """
        if not lesson_ids:
            return {'success': True, 'recorded_count': 0}

        count = 0
        for lid in lesson_ids:
            ok = InterestScoringService.record_interaction(
                user=user,
                guest_device_id=guest_device_id,
                lesson_id=lid,
                interaction_type=InteractionType.IMPRESSION,
                metadata={},
            )
            if ok:
                count += 1

        return {'success': True, 'recorded_count': count}

    @staticmethod
    def record_watch_progress(
        user=None,
        guest_device_id: str = '',
        lesson_id: int = None,
        watch_seconds: int = 0,
        duration_seconds: int = 0,
        resume_position: int = 0,
    ) -> dict:
        """
        Record a watch progress update. If the user completed the video,
        record a WATCH_COMPLETE instead of WATCH_UPDATE.
        """
        completion_pct = (watch_seconds / duration_seconds * 100) if duration_seconds > 0 else 0

        if completion_pct >= 90:
            interaction_type = InteractionType.WATCH_COMPLETE
        else:
            interaction_type = InteractionType.WATCH_UPDATE

        metadata = {
            'watch_seconds': watch_seconds,
            'duration_seconds': duration_seconds,
            'completion_percentage': round(completion_pct, 1),
            'resume_position': resume_position,
        }

        return InteractionApiService.record(
            user=user,
            guest_device_id=guest_device_id,
            lesson_id=lesson_id,
            interaction_type=interaction_type,
            metadata=metadata,
        )

    @staticmethod
    def get_interaction_summary(
        user=None,
        guest_device_id: str = '',
    ) -> dict:
        """Get a summary of the user's interactions for profile display."""
        from apps.feed.models_v2 import UserInteraction

        filters = {}
        if user and user.is_authenticated:
            filters['user'] = user
        elif guest_device_id:
            filters['guest_device_id'] = guest_device_id
        else:
            return {}

        qs = UserInteraction.objects.filter(**filters)

        total = qs.count()
        likes = qs.filter(interaction_type=InteractionType.LIKE).count()
        saves = qs.filter(interaction_type=InteractionType.SAVE).count()
        shares = qs.filter(interaction_type=InteractionType.SHARE).count()
        completions = qs.filter(interaction_type=InteractionType.WATCH_COMPLETE).count()
        impressions = qs.filter(interaction_type=InteractionType.IMPRESSION).count()
        skips = qs.filter(interaction_type=InteractionType.SKIP).count()

        return {
            'total_interactions': total,
            'likes': likes,
            'saves': saves,
            'shares': shares,
            'completions': completions,
            'impressions': impressions,
            'skips': skips,
        }
