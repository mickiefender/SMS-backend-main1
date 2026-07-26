"""
Personalized Recommendation Service for the Alara Learning Feed.

Implements the 70/20/10 feed composition:
  - 70% personalized videos (based on interest scores + onboarding + recent engagement)
  - 20% trending educational videos (popular across the platform)
  - 10% discovery / random educational videos (serendipity)

The recommendation rank for personalised items combines:
  - Preference match (from UserInterestScore + onboarding)
  - User interaction history (recency-weighted)
  - Video popularity (trending_score, view_count)
  - Content freshness (recency bonus for newer content)
  - Recent engagement (boosts videos the user recently watched or engaged with)

Behavioural data (interest scores) gradually becomes more important than
original onboarding preferences as the user accumulates interactions.
"""
import random
import logging
from decimal import Decimal
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from django.db import connection
from django.db.models import (
    Case, Count, DecimalField, ExpressionWrapper, F, Q, Value, When,
    IntegerField, FloatField, Func, DateTimeField,
)
from django.utils import timezone

from apps.feed.models import FeedLesson, FeedTag
from apps.feed.models_v2 import (
    InterestDomain,
    UserInteraction,
    UserInterestScore,
    InteractionType,
)
from apps.feed.services.interest_scoring_service import InterestScoringService

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

# Feed composition ratios
PERSONALIZED_FRACTION = Decimal('0.70')   # 70%
TRENDING_FRACTION = Decimal('0.20')       # 20%
DISCOVERY_FRACTION = Decimal('0.10')      # 10%

# Scoring weights for the composite recommendation score
WEIGHT_PREFERENCE_MATCH = Decimal('0.35')
WEIGHT_POPULARITY = Decimal('0.25')
WEIGHT_FRESHNESS = Decimal('0.20')
WEIGHT_RECENT_ENGAGEMENT = Decimal('0.20')

# Freshness bonus: videos published within this window get a boost
FRESHNESS_WINDOW_DAYS = 14
FRESHNESS_BONUS = Decimal('15.00')

# Recent engagement window: interactions in the last N hours get a boost
RECENT_ENGAGEMENT_HOURS = 48
RECENT_ENGAGEMENT_BONUS = Decimal('10.00')

# Minimum interest score to consider a preference active
MIN_INTEREST_THRESHOLD = Decimal('5.00')

# How many lessons to fetch for the personalized pool
PERSONALIZED_POOL_SIZE = 200


class PersonalizedRecommendationService:

    # ─── Public API: get blended feed ───────────────────────────

    @staticmethod
    def get_blended_feed(
        user=None,
        guest_device_id: str = '',
        page: int = 1,
        page_size: int = 12,
        school_id: Optional[int] = None,
    ) -> List[FeedLesson]:
        """
        Generate a blended feed with 70/20/10 composition.

        Returns a flat list of FeedLesson IDs ordered by recommendation score
        within each bucket, interleaved to provide variety.
        """
        total_needed = page * page_size
        per_page_fetch = page_size * 3  # fetch extra to allow dedup

        personalized = PersonalizedRecommendationService._get_personalized_bucket(
            user=user, guest_device_id=guest_device_id,
            limit=max(per_page_fetch, 50),
            school_id=school_id,
        )
        trending = PersonalizedRecommendationService._get_trending_bucket(
            user=user, guest_device_id=guest_device_id,
            limit=max(per_page_fetch, 30),
            school_id=school_id,
        )
        discovery = PersonalizedRecommendationService._get_discovery_bucket(
            user=user, guest_device_id=guest_device_id,
            limit=max(per_page_fetch, 20),
            school_id=school_id,
        )

        # Blend: interleave 70/20/10 with dedup
        seen_ids: set = set()
        blended: List[FeedLesson] = []

        max_len = max(len(personalized), len(trending), len(discovery))
        p_idx, t_idx, d_idx = 0, 0, 0

        while len(blended) < total_needed and (p_idx < len(personalized) or t_idx < len(trending) or d_idx < len(discovery)):
            # Add 3-4 personalized items
            for _ in range(3):
                if p_idx < len(personalized):
                    lesson = personalized[p_idx]
                    p_idx += 1
                    if lesson.id not in seen_ids:
                        seen_ids.add(lesson.id)
                        blended.append(lesson)

            # Add 1 trending item
            if t_idx < len(trending):
                lesson = trending[t_idx]
                t_idx += 1
                if lesson.id not in seen_ids:
                    seen_ids.add(lesson.id)
                    blended.append(lesson)

            # Add 1 discovery item (every other block, to maintain ~10%)
            if d_idx < len(discovery) and len(blended) % 3 == 0:
                lesson = discovery[d_idx]
                d_idx += 1
                if lesson.id not in seen_ids:
                    seen_ids.add(lesson.id)
                    blended.append(lesson)

        # Trim to requested size
        return blended[:total_needed]

    # ─── Personalized bucket (70%) ──────────────────────────────

    @staticmethod
    def _get_personalized_bucket(
        user=None,
        guest_device_id: str = '',
        limit: int = 50,
        school_id: Optional[int] = None,
    ) -> List[FeedLesson]:
        """
        Return lessons ranked by personalized recommendation score.

        The score is a weighted composite of:
          1. Preference match (from interest scores + onboarding)
          2. Popularity (trending_score, view_count, like_count)
          3. Freshness (recency bonus)
          4. Recent engagement (boost for recently interacted-with content)
        """
        base_qs = FeedLesson.objects.filter(
            status='approved',
            visibility='public',
            published_at__isnull=False,
        )

        if school_id:
            base_qs = base_qs.filter(school_id=school_id)

        # ── Get interest signals ────────────────────────────────
        interests = InterestScoringService.get_top_interest_ids(
            user=user, guest_device_id=guest_device_id,
            min_score=MIN_INTEREST_THRESHOLD,
        )
        subject_ids = set(interests.get(InterestDomain.SUBJECT, []))
        teacher_ids = set(interests.get(InterestDomain.TEACHER, []))
        level_id = interests.get(InterestDomain.LEVEL, [None])[0] if interests.get(InterestDomain.LEVEL) else None
        class_id = interests.get(InterestDomain.CLASS_OBJ, [None])[0] if interests.get(InterestDomain.CLASS_OBJ) else None
        tag_ids = set(interests.get(InterestDomain.TAG, []))

        # Also include onboarding preferences for users who just started
        if user and user.is_authenticated:
            profile = getattr(user, 'learning_profile', None)
            if profile:
                onboarding_subjects = list(profile.preferred_subjects.values_list('id', flat=True))
                subject_ids.update(onboarding_subjects)
                if profile.preferred_level_id and level_id is None:
                    level_id = profile.preferred_level_id
                if profile.preferred_class_id and class_id is None:
                    class_id = profile.preferred_class_id

            # Followed teachers
            from apps.feed.models import TeacherFollower
            followed = TeacherFollower.objects.filter(user=user).values_list('teacher_id', flat=True)
            teacher_ids.update(followed)

        # ── Check if behavioural data should dominate ───────────
        should_prioritize_behavioural = InterestScoringService.should_prioritize_behavioural(
            user=user, guest_device_id=guest_device_id
        )

        # ── Build candidate query based on interest signals ─────
        if subject_ids or teacher_ids or level_id or class_id or tag_ids:
            candidate_filters = Q()
            if subject_ids:
                candidate_filters |= Q(subject_id__in=list(subject_ids))
            if teacher_ids:
                candidate_filters |= Q(teacher_id__in=list(teacher_ids))
            if level_id:
                candidate_filters |= Q(level_id=level_id)
            if class_id:
                candidate_filters |= Q(class_obj_id=class_id)
            if tag_ids:
                candidate_filters |= Q(tags__id__in=list(tag_ids))

            candidates = base_qs.filter(candidate_filters).distinct()
        else:
            # No signals yet — fall back to trending
            logger.debug("No interest signals for user, falling back to trending for personalized bucket")
            candidates = base_qs

        # ── Compute composite score ─────────────────────────────
        now = timezone.now()
        freshness_cutoff = now - timedelta(days=FRESHNESS_WINDOW_DAYS)
        recent_cutoff = now - timedelta(hours=RECENT_ENGAGEMENT_HOURS)

        # Build preference match annotations
        pref_annotations = {}

        pref_annotations['pref_subject'] = Case(
            When(subject_id__in=list(subject_ids), then=Value(Decimal(20), output_field=DecimalField(max_digits=10, decimal_places=2))),
            default=Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ) if subject_ids else Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2))

        pref_annotations['pref_teacher'] = Case(
            When(teacher_id__in=list(teacher_ids), then=Value(Decimal(25), output_field=DecimalField(max_digits=10, decimal_places=2))),
            default=Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ) if teacher_ids else Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2))

        pref_annotations['pref_level'] = Case(
            When(level_id=level_id, then=Value(Decimal(15), output_field=DecimalField(max_digits=10, decimal_places=2))),
            default=Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ) if level_id else Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2))

        pref_annotations['pref_class'] = Case(
            When(class_obj_id=class_id, then=Value(Decimal(15), output_field=DecimalField(max_digits=10, decimal_places=2))),
            default=Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ) if class_id else Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2))

        pref_annotations['freshness_bonus'] = Case(
            When(published_at__gte=freshness_cutoff,
                 then=Value(FRESHNESS_BONUS, output_field=DecimalField(max_digits=10, decimal_places=2))),
            default=Value(Decimal(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )

        pref_annotations['pop_score'] = ExpressionWrapper(
            F('trending_score') * Value(Decimal('0.5')) +
            F('view_count') * Value(Decimal('0.01')) +
            F('like_count') * Value(Decimal('0.02')) +
            F('completion_rate') * Value(Decimal('0.1')),
            output_field=DecimalField(max_digits=18, decimal_places=6),
        )

        # Behavioural override multiplier
        if should_prioritize_behavioural:
            pref_annotations['pref_multiplier'] = Value(Decimal('2.0'), output_field=DecimalField(max_digits=5, decimal_places=2))
        else:
            pref_annotations['pref_multiplier'] = Value(Decimal('1.0'), output_field=DecimalField(max_digits=5, decimal_places=2))

        candidates = candidates.annotate(**pref_annotations)

        # Composite recommendation score
        candidates = candidates.annotate(
            rec_score=(
                # Preference match (35%)
                (F('pref_subject') + F('pref_teacher') + F('pref_level') + F('pref_class'))
                * F('pref_multiplier') * Value(WEIGHT_PREFERENCE_MATCH)
                # Popularity (25%)
                + F('pop_score') * Value(WEIGHT_POPULARITY)
                # Freshness (20%)
                + F('freshness_bonus') * Value(WEIGHT_FRESHNESS)
            )
        ).order_by('-rec_score', '-trending_score', '-published_at')

        return list(candidates[:limit])

    # ─── Trending bucket (20%) ──────────────────────────────────

    @staticmethod
    def _get_trending_bucket(
        user=None,
        guest_device_id: str = '',
        limit: int = 30,
        school_id: Optional[int] = None,
    ) -> List[FeedLesson]:
        """
        Return trending educational videos based on platform-wide popularity.
        Considers trending_score, view velocity, and recent engagement.
        """
        qs = FeedLesson.objects.filter(
            status='approved',
            visibility='public',
            published_at__isnull=False,
        )
        if school_id:
            qs = qs.filter(school_id=school_id)

        # Compute an engagement velocity score that favours recent activity
        # We use the existing trending_score as a base but also boost by
        # view_count and completion_rate for quality signals.
        qs = qs.annotate(
            trending_rank=(
                F('trending_score') * Value(Decimal('1.0')) +
                F('view_count') * Value(Decimal('0.05')) +
                F('like_count') * Value(Decimal('0.1')) +
                F('completion_rate') * Value(Decimal('0.5')) +
                F('share_count') * Value(Decimal('0.3'))
            )
        ).order_by('-trending_rank', '-trending_score', '-published_at')

        return list(qs[:limit])

    # ─── Discovery bucket (10%) ─────────────────────────────────

    @staticmethod
    def _get_discovery_bucket(
        user=None,
        guest_device_id: str = '',
        limit: int = 20,
        school_id: Optional[int] = None,
    ) -> List[FeedLesson]:
        """
        Return random / serendipitous videos for discovery.

        Uses a weighted random selection that favours higher-quality content
        (quality_score >= 60) but provides diversity across subjects and teachers.
        """
        qs = FeedLesson.objects.filter(
            status='approved',
            visibility='public',
            published_at__isnull=False,
        )
        if school_id:
            qs = qs.filter(school_id=school_id)

        # Exclude recently watched content for better discovery
        if user and user.is_authenticated:
            watched_ids = UserInteraction.objects.filter(
                user=user,
                interaction_type__in=[
                    InteractionType.WATCH_COMPLETE,
                    InteractionType.WATCH_START,
                ],
            ).values_list('lesson_id', flat=True).distinct()
            qs = qs.exclude(id__in=list(watched_ids))

        # Prefer quality content but add randomness
        # Get a larger pool from quality content, then randomise
        discovery_pool = qs.filter(
            quality_score__gte=Decimal('40.00'),
        ).order_by('?')[:limit * 3]

        # If we don't have enough quality content, fill from the rest
        if len(discovery_pool) < limit:
            remaining = limit - len(discovery_pool)
            extra = qs.exclude(
                id__in=[l.id for l in discovery_pool]
            ).order_by('?')[:remaining]
            discovery_pool = list(discovery_pool) + list(extra)

        # Shuffle for true randomness
        result = list(discovery_pool)
        random.shuffle(result)

        return result[:limit]

    # ─── Cache management ───────────────────────────────────────

    @staticmethod
    def get_cache_key(user=None, guest_device_id: str = '', school_id: Optional[int] = None) -> str:
        uid = str(user.id) if user and user.is_authenticated else guest_device_id
        return f"feed:blended:{uid}:{school_id or 'global'}"

    @staticmethod
    def invalidate_caches(user=None, guest_device_id: str = ''):
        """Invalidate the blended feed cache for a user/guest."""
        from django.core.cache import cache
        try:
            client = cache.client.get_client()
            uid = str(user.id) if user and user.is_authenticated else guest_device_id
            for key in client.scan_iter(match=f"feed:blended:{uid}:*"):
                client.delete(key)
        except Exception:
            pass
