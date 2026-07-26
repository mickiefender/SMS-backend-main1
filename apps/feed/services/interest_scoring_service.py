"""
Interest Scoring Service for the Alara Learning Feed.

Maps user interactions to weighted interest scores across multiple domains:
subject, academic level, class, teacher, and tags.

Positive interactions (like, save, watch_complete, share, comment, follow)
increase the score; negative interactions (skip, unlike, unsave, unfollow)
decrease it.

The score is cumulative in range [-100, +100] and decays slowly over time
if not reinforced. Behavioral data gradually outweighs onboarding preferences.
"""
import logging
from decimal import Decimal
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from apps.feed.models import FeedLesson, FeedTag
from apps.feed.models_v2 import (
    InteractionType,
    InterestDomain,
    UserInteraction,
    UserInterestScore,
)

logger = logging.getLogger(__name__)

# ---- Interaction weight map -------------------------------------------------
# Each interaction type maps to a signed weight and a list of domains it affects.
# Weights are heuristic; tune via experimentation.

_INTERACTION_WEIGHTS: Dict[str, Dict] = {
    InteractionType.IMPRESSION: {
        'weight': Decimal('0.1'),
        'domains': ['subject'],
        'is_positive': True,
    },
    InteractionType.WATCH_START: {
        'weight': Decimal('0.5'),
        'domains': ['subject', 'level'],
        'is_positive': True,
    },
    InteractionType.WATCH_UPDATE: {
        'weight': Decimal('0.3'),
        'domains': ['subject', 'level', 'teacher'],
        'is_positive': True,
    },
    InteractionType.WATCH_COMPLETE: {
        'weight': Decimal('3.0'),
        'domains': ['subject', 'level', 'class_obj', 'teacher'],
        'is_positive': True,
    },
    InteractionType.LIKE: {
        'weight': Decimal('2.0'),
        'domains': ['subject', 'teacher'],
        'is_positive': True,
    },
    InteractionType.UNLIKE: {
        'weight': Decimal('-1.5'),
        'domains': ['subject', 'teacher'],
        'is_positive': False,
    },
    InteractionType.COMMENT: {
        'weight': Decimal('1.5'),
        'domains': ['subject', 'teacher'],
        'is_positive': True,
    },
    InteractionType.SHARE: {
        'weight': Decimal('3.0'),
        'domains': ['subject', 'teacher', 'level'],
        'is_positive': True,
    },
    InteractionType.SAVE: {
        'weight': Decimal('2.5'),
        'domains': ['subject', 'teacher', 'tag'],
        'is_positive': True,
    },
    InteractionType.UNSAVE: {
        'weight': Decimal('-1.0'),
        'domains': ['subject', 'teacher', 'tag'],
        'is_positive': False,
    },
    InteractionType.SKIP: {
        'weight': Decimal('-2.0'),
        'domains': ['subject', 'level'],
        'is_positive': False,
    },
    InteractionType.FOLLOW_TEACHER: {
        'weight': Decimal('4.0'),
        'domains': ['teacher'],
        'is_positive': True,
    },
    InteractionType.UNFOLLOW_TEACHER: {
        'weight': Decimal('-3.0'),
        'domains': ['teacher'],
        'is_positive': False,
    },
}

# Decay: interest loses 5% of its value each day if not reinforced
_DAILY_DECAY_FACTOR = Decimal('0.95')
# Onboarding preferences decay more slowly
_ONBOARDING_DECAY_FACTOR = Decimal('0.98')

# Score bounds
_MAX_SCORE = Decimal('100.00')
_MIN_SCORE = Decimal('-100.00')

# Behavioural override threshold — when behavioural score magnitude exceeds this,
# it overrides onboarding in the recommendation ranking
_BEHAVIOURAL_OVERRIDE_THRESHOLD = Decimal('30.00')


class InterestScoringService:

    # ─── Recording interactions ─────────────────────────────────

    @staticmethod
    def record_interaction(
        user=None,
        guest_device_id: str = '',
        lesson_id: int = None,
        interaction_type: str = None,
        metadata: dict = None,
        lesson_obj: Optional[FeedLesson] = None,
    ) -> bool:
        """
        Record a user interaction and update interest scores atomically.

        Accepts either a lesson_id (fetches the lesson) or a pre-loaded
        lesson_obj to avoid N+1 queries in batch scenarios.
        """
        if not user and not guest_device_id:
            logger.warning("record_interaction called without user or guest_device_id")
            return False

        if interaction_type not in _INTERACTION_WEIGHTS:
            logger.debug("Unknown interaction type: %s — skipping score update", interaction_type)
            return False

        weight_config = _INTERACTION_WEIGHTS[interaction_type]

        # For follow/unfollow, the lesson_id may not exist; the teacher_id is in metadata
        if interaction_type in (InteractionType.FOLLOW_TEACHER, InteractionType.UNFOLLOW_TEACHER):
            teacher_id = (metadata or {}).get('teacher_id')
            if not teacher_id:
                logger.warning("Follow/unfollow interaction requires teacher_id in metadata")
                return False
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                teacher_user = User.objects.get(pk=teacher_id)
            except Exception:
                logger.warning("Teacher user %d not found", teacher_id)
                return False

            # Create raw interaction record (no lesson)
            try:
                UserInteraction.objects.create(
                    user=user if user and user.is_authenticated else None,
                    guest_device_id=guest_device_id if not (user and user.is_authenticated) else '',
                    lesson_id=lesson_id or 0,
                    interaction_type=interaction_type,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.error("Failed to create UserInteraction: %s", e)
                return False

            # Update teacher interest score directly
            InterestScoringService._update_single_score(
                user=user,
                guest_device_id=guest_device_id,
                domain=InterestDomain.TEACHER,
                entity_id=teacher_id,
                weight=weight_config['weight'],
                is_positive=weight_config['is_positive'],
            )
            return True

        # Resolve lesson
        if lesson_obj is None and lesson_id:
            try:
                lesson_obj = FeedLesson.objects.select_related(
                    'subject', 'level', 'class_obj', 'teacher'
                ).prefetch_related('tags').get(pk=lesson_id)
            except FeedLesson.DoesNotExist:
                logger.warning("Lesson %d not found for interaction recording", lesson_id)
                return False

        if lesson_obj is None:
            return False

        # Create the raw interaction record
        try:
            UserInteraction.objects.create(
                user=user if user and user.is_authenticated else None,
                guest_device_id=guest_device_id if not (user and user.is_authenticated) else '',
                lesson=lesson_obj,
                interaction_type=interaction_type,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error("Failed to create UserInteraction: %s", e)
            return False

        # Update interest scores
        try:
            InterestScoringService._update_scores(
                user=user,
                guest_device_id=guest_device_id,
                lesson=lesson_obj,
                weight_config=weight_config,
            )
        except Exception as e:
            logger.error("Failed to update interest scores: %s", e)
            return False

        return True

    @staticmethod
    def _update_scores(
        user,
        guest_device_id: str,
        lesson: FeedLesson,
        weight_config: dict,
    ):
        """Update all relevant interest score rows for a given interaction."""
        domains = weight_config['domains']
        weight = weight_config['weight']
        is_positive = weight_config['is_positive']

        domain_entity_pairs = []

        for domain in domains:
            if domain == 'subject' and lesson.subject_id:
                domain_entity_pairs.append((InterestDomain.SUBJECT, lesson.subject_id))
            elif domain == 'level' and lesson.level_id:
                domain_entity_pairs.append((InterestDomain.LEVEL, lesson.level_id))
            elif domain == 'class_obj' and lesson.class_obj_id:
                domain_entity_pairs.append((InterestDomain.CLASS_OBJ, lesson.class_obj_id))
            elif domain == 'teacher':
                domain_entity_pairs.append((InterestDomain.TEACHER, lesson.teacher_id))
            elif domain == 'tag':
                for tag in lesson.tags.all():
                    domain_entity_pairs.append((InterestDomain.TAG, tag.id))
            elif domain == 'content_type' and lesson.content_type_id:
                domain_entity_pairs.append((InterestDomain.CONTENT_TYPE, lesson.content_type_id))
            elif domain == 'difficulty' and lesson.difficulty_level_id:
                domain_entity_pairs.append((InterestDomain.DIFFICULTY, lesson.difficulty_level_id))

        for domain, entity_id in domain_entity_pairs:
            InterestScoringService._update_single_score(
                user=user,
                guest_device_id=guest_device_id,
                domain=domain,
                entity_id=entity_id,
                weight=weight,
                is_positive=is_positive,
            )

    @staticmethod
    def _update_single_score(
        user,
        guest_device_id: str,
        domain: str,
        entity_id: int,
        weight: Decimal,
        is_positive: bool,
    ):
        """
        Atomic upsert + increment for a single interest score row.
        Uses select_for_update within a transaction to avoid races.
        """
        now = timezone.now()

        # Determine the lookup
        filters = {}
        if user and user.is_authenticated:
            filters['user'] = user
            filters['guest_device_id'] = ''
        else:
            filters['user'] = None
            filters['guest_device_id'] = guest_device_id

        filters['interest_domain'] = domain
        filters['interest_id'] = entity_id

        with transaction.atomic():
            score_row, created = UserInterestScore.objects.select_for_update().get_or_create(
                defaults=filters | {
                    'score': weight,
                    'positive_interactions': 1 if is_positive else 0,
                    'negative_interactions': 0 if is_positive else 1,
                    'last_interaction_at': now,
                },
                **filters,
            )

            if created:
                return

            # Update existing
            score_row.score += weight

            # Clamp
            if score_row.score > _MAX_SCORE:
                score_row.score = _MAX_SCORE
            elif score_row.score < _MIN_SCORE:
                score_row.score = _MIN_SCORE

            if is_positive:
                score_row.positive_interactions += 1
            else:
                score_row.negative_interactions += 1

            score_row.last_interaction_at = now
            score_row.save(update_fields=[
                'score', 'positive_interactions', 'negative_interactions',
                'last_interaction_at', 'updated_at',
            ])

    # ─── Session-based decay ─────────────────────────────────────

    @staticmethod
    def apply_decay(user=None, guest_device_id: str = ''):
        """
        Apply time-based decay to all interest scores for a user/guest.
        Should be called periodically (e.g. once per day via Celery).
        """
        filters = {}
        if user and user.is_authenticated:
            filters['user'] = user
        elif guest_device_id:
            filters['guest_device_id'] = guest_device_id
        else:
            return

        scores = UserInterestScore.objects.filter(**filters)
        now = timezone.now()

        for score in scores:
            if score.last_interaction_at is None:
                continue

            days_since = (now - score.last_interaction_at).days
            if days_since <= 0:
                continue

            decay_factor = (
                _ONBOARDING_DECAY_FACTOR ** days_since
                if score.is_onboarding_preference
                else _DAILY_DECAY_FACTOR ** days_since
            )

            new_score = score.score * decay_factor

            # If score is very small after decay, reset to 0
            if abs(new_score) < Decimal('0.1'):
                new_score = Decimal('0')

            score.score = new_score
            score.save(update_fields=['score', 'updated_at'])

    # ─── Reading scores for recommendations ──────────────────────

    @staticmethod
    def get_top_interest_ids(
        user=None,
        guest_device_id: str = '',
        domain: Optional[str] = None,
        limit: int = 10,
        min_score: Decimal = Decimal('0'),
    ) -> Dict[str, List[int]]:
        """
        Return interest domains and entity IDs where score > min_score,
        sorted descending by score.

        Returns dict like:
          {'subject': [3, 7, 1], 'teacher': [12], 'level': [2], ...}
        """
        filters = {}
        if user and user.is_authenticated:
            filters['user'] = user
        elif guest_device_id:
            filters['guest_device_id'] = guest_device_id
        else:
            return {}

        qs = UserInterestScore.objects.filter(**filters, score__gt=min_score)
        if domain:
            qs = qs.filter(interest_domain=domain)

        qs = qs.order_by('-score')[:limit]

        result: Dict[str, List[int]] = {}
        for row in qs:
            result.setdefault(row.interest_domain, []).append(row.interest_id)
        return result

    @staticmethod
    def get_behavioural_override_score(
        user=None,
        guest_device_id: str = '',
        domain: Optional[str] = None,
    ) -> Decimal:
        """
        Calculate the aggregate behavioural score across all domains.
        Returns the maximum absolute score found; when this exceeds the
        BEHAVIOURAL_OVERRIDE_THRESHOLD, behavioural data should dominate
        onboarding preferences in the recommendation algorithm.
        """
        filters = {}
        if user and user.is_authenticated:
            filters['user'] = user
        elif guest_device_id:
            filters['guest_device_id'] = guest_device_id
        else:
            return Decimal('0')

        qs = UserInterestScore.objects.filter(**filters)
        if domain:
            qs = qs.filter(interest_domain=domain)

        # Use Django ORM
        scores = list(qs.values_list('score', flat=True))
        if not scores:
            return Decimal('0')

        max_abs = max(abs(s) for s in scores)
        return max_abs

    @staticmethod
    def should_prioritize_behavioural(
        user=None,
        guest_device_id: str = '',
    ) -> bool:
        """Check if behavioural data has accumulated enough to override onboarding."""
        max_abs = InterestScoringService.get_behavioural_override_score(
            user=user, guest_device_id=guest_device_id
        )
        return max_abs >= _BEHAVIOURAL_OVERRIDE_THRESHOLD

    # ─── Seeding from onboarding preferences ─────────────────────

    @staticmethod
    def seed_from_onboarding(
        user=None,
        guest_device_id: str = '',
        subject_ids: Optional[List[int]] = None,
        level_id: Optional[int] = None,
        class_id: Optional[int] = None,
    ):
        """
        Seed interest scores from onboarding preferences with a modest
        initial score so the user gets relevant content immediately.
        """
        now = timezone.now()
        base_score = Decimal('15.00')  # Starting score for onboarding

        pairs = []
        if subject_ids:
            for sid in subject_ids:
                pairs.append((InterestDomain.SUBJECT, sid))
        if level_id:
            pairs.append((InterestDomain.LEVEL, level_id))
        if class_id:
            pairs.append((InterestDomain.CLASS_OBJ, class_id))

        for domain, entity_id in pairs:
            filters = {}
            if user and user.is_authenticated:
                filters['user'] = user
                filters['guest_device_id'] = ''
            else:
                filters['user'] = None
                filters['guest_device_id'] = guest_device_id

            filters['interest_domain'] = domain
            filters['interest_id'] = entity_id

            UserInterestScore.objects.update_or_create(
                defaults=filters | {
                    'score': base_score,
                    'is_onboarding_preference': True,
                    'last_interaction_at': now,
                },
                **filters,
            )
