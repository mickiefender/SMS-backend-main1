"""
Personalized Recommendation Service for the Alara Learning Feed.

Implements a TikTok/Reels-style ranked feed for students:

Scoring signals (each normalised to 0-100, combined with fixed weights):
  - Freshness       — exponential half-life decay so newly uploaded posts can
                      appear near the top even with zero likes.
  - Relevance       — match against student interests (subject, teacher,
                      level, class, tags) learned from behaviour + onboarding.
  - Popularity      — views, likes, comments, shares, saves (log-scaled).
  - Quality         — completion rate and avg watch time.
  - Exploration     — small per-request random jitter so refreshes vary.

Additional behaviours:
  - Diversity spacing: never more than MAX_CONSECUTIVE_SAME_TEACHER posts from
    one teacher or MAX_CONSECUTIVE_SAME_SUBJECT posts from one subject.
  - Session-stable snapshots: the full ranked id list is cached under an
    opaque feed token so paginated scrolling never jumps or duplicates.
    Pull-to-refresh simply requests a new token (fresh ranking).
"""
import logging
import math
import random
import uuid
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from django.core.cache import cache
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Value
from django.utils import timezone

from apps.feed.models import FeedLesson
from apps.feed.models_v2 import (
    InterestDomain,
    InteractionType,
    UserInteraction,
)
from apps.feed.services.interest_scoring_service import InterestScoringService

logger = logging.getLogger(__name__)


class PersonalizedRecommendationService:

    # ── Snapshot / pagination ───────────────────────────────────
    SNAPSHOT_TTL_SECONDS = 1800          # 30 min session stability
    SNAPSHOT_MAX_IDS = 600               # hard cap on ranked snapshot length

    # ── Candidate pooling ───────────────────────────────────────
    RECENT_POOL_SIZE = 150               # newest posts always considered
    POPULAR_POOL_SIZE = 250              # high-engagement posts considered

    # ── Scoring ─────────────────────────────────────────────────
    FRESHNESS_HALF_LIFE_HOURS = 36       # score halves every 36h
    NEW_POST_WINDOW_HOURS = 24           # extra boost window for new uploads
    NEW_POST_BOOST = 25

    WEIGHT_FRESHNESS = 35.0
    WEIGHT_RELEVANCE = 30.0
    WEIGHT_POPULARITY = 20.0
    WEIGHT_QUALITY = 10.0
    EXPLORATION_JITTER_MAX = 5.0         # controlled randomisation

    BEHAVIOUR_WINDOW_DAYS = 14           # look-back for viewing behaviour
    COMPLETED_PENALTY = 45.0             # demote fully-watched lessons

    MIN_INTEREST_THRESHOLD = 5.0

    # ── Diversity constraints ───────────────────────────────────
    MAX_CONSECUTIVE_SAME_TEACHER = 2
    MAX_CONSECUTIVE_SAME_SUBJECT = 3
    DIVERSITY_LOOKAHEAD = 12             # how far ahead to search for a swap

    DISCOVERY_EVERY_N = 9                # inject a discovery post every N items
    DISCOVERY_FRACTION = 0.08            # ~8% serendipitous content

    # ════════════════════════════════════════════════════════════
    # Snapshot management (stable ordering across pages)
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _owner_key(user=None, guest_device_id: str = '') -> str:
        if user and getattr(user, 'is_authenticated', False):
            return f"user:{user.id}"
        return f"guest:{guest_device_id or 'anon'}"

    @staticmethod
    def _snapshot_cache_key(owner_key: str, token: str) -> str:
        return f"feed:blended-snapshot:{owner_key}:{token}"

    @classmethod
    def create_snapshot(
        cls,
        user=None,
        guest_device_id: str = '',
        school_id: Optional[int] = None,
    ) -> Tuple[str, List[int]]:
        """Build a fresh ranked id list and store it under a new token."""
        ranked = cls.build_ranked_feed(
            user=user, guest_device_id=guest_device_id, school_id=school_id,
        )
        token = uuid.uuid4().hex[:16]
        owner = cls._owner_key(user, guest_device_id)
        ids = [lesson.id for lesson in ranked][:cls.SNAPSHOT_MAX_IDS]
        try:
            cache.set(
                cls._snapshot_cache_key(owner, token),
                ids,
                timeout=cls.SNAPSHOT_TTL_SECONDS,
            )
        except Exception:
            logger.warning("Failed to persist blended feed snapshot", exc_info=True)
        return token, ids

    @classmethod
    def get_snapshot(cls, user=None, guest_device_id: str = '', token: str = '') -> Optional[List[int]]:
        """Return the stored ranked ids for a token, or None if expired."""
        if not token:
            return None
        owner = cls._owner_key(user, guest_device_id)
        try:
            ids = cache.get(cls._snapshot_cache_key(owner, token))
        except Exception:
            return None
        return ids if isinstance(ids, list) else None

    # ════════════════════════════════════════════════════════════
    # Ranking
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _visible_queryset(school_id: Optional[int] = None):
        qs = FeedLesson.objects.filter(
            status='approved',
            visibility='public',
            published_at__isnull=False,
        )
        if school_id:
            qs = qs.filter(school_id=school_id)
        return qs

    @staticmethod
    def _engagement_annotation():
        """Live engagement fallback while scheduled trending scores catch up."""
        return ExpressionWrapper(
            F('view_count') * Value(1.0) +
            F('unique_view_count') * Value(2.0) +
            F('like_count') * Value(4.0) +
            F('save_count') * Value(5.0) +
            F('comment_count') * Value(3.0) +
            F('share_count') * Value(6.0) +
            F('completion_rate') * Value(10.0) +
            F('avg_watch_seconds') * Value(0.1),
            output_field=DecimalField(max_digits=18, decimal_places=6),
        )

    @classmethod
    def build_ranked_feed(
        cls,
        user=None,
        guest_device_id: str = '',
        school_id: Optional[int] = None,
    ) -> List[FeedLesson]:
        """
        Produce a fully ranked, diversity-spaced list of lessons.

        Steps:
          1. Pool candidates (recent + popular).
          2. Gather interest / behavioural signals for this viewer.
          3. Score each candidate in Python (freshness, relevance,
             popularity, quality, exploration jitter).
          4. Rank, interleave a discovery slice, then enforce diversity
             spacing across teachers and subjects.
        """
        now = timezone.now()

        # ── 1. Candidate pool ───────────────────────────────────
        base_qs = cls._visible_queryset(school_id).prefetch_related('tags')

        recent_qs = base_qs.order_by('-published_at', '-pk')[:cls.RECENT_POOL_SIZE]

        popular_qs = base_qs.annotate(
            live_engagement=cls._engagement_annotation(),
        ).order_by('-live_engagement', '-trending_score', '-published_at', '-pk')[
            :cls.POPULAR_POOL_SIZE
        ]

        candidates: Dict[int, FeedLesson] = {}
        for lesson in list(recent_qs) + list(popular_qs):
            candidates.setdefault(lesson.id, lesson)
        if not candidates:
            return []

        # ── 2. Viewer signals ───────────────────────────────────
        signals = cls._gather_signals(user, guest_device_id, now)

        # ── 3. Score ────────────────────────────────────────────
        scored: List[Tuple[float, int, FeedLesson]] = []
        for lesson in candidates.values():
            score = cls._score_lesson(lesson, signals, now)
            scored.append((score, lesson.id, lesson))

        scored.sort(key=lambda item: (-item[0], -item[1]))
        ranked: List[FeedLesson] = [item[2] for item in scored]

        # ── 4a. Discovery interleaving ──────────────────────────
        ranked = cls._interleave_discovery(ranked, base_qs, signals['seen_ids'])

        # ── 4b. Diversity spacing ───────────────────────────────
        return cls.apply_diversity_spacing(ranked)

    @staticmethod
    def _gather_signals(user, guest_device_id: str, now) -> dict:
        """Collect interest + behavioural signals for the viewer."""
        interests = InterestScoringService.get_top_interest_ids(
            user=user, guest_device_id=guest_device_id,
            min_score=PersonalizedRecommendationService.MIN_INTEREST_THRESHOLD,
        )
        subject_ids = set(interests.get(InterestDomain.SUBJECT, []))
        teacher_ids = set(interests.get(InterestDomain.TEACHER, []))
        tag_ids = set(interests.get(InterestDomain.TAG, []))
        level_id = (
            interests.get(InterestDomain.LEVEL, [None])[0]
            if interests.get(InterestDomain.LEVEL) else None
        )
        class_id = (
            interests.get(InterestDomain.CLASS_OBJ, [None])[0]
            if interests.get(InterestDomain.CLASS_OBJ) else None
        )

        # Onboarding preferences (for users with little history yet).
        if user and getattr(user, 'is_authenticated', False):
            profile = getattr(user, 'learning_profile', None)
            if profile:
                subject_ids.update(profile.preferred_subjects.values_list('id', flat=True))
                level_id = level_id or profile.preferred_level_id
                class_id = class_id or profile.preferred_class_id

            from apps.feed.models import TeacherFollower
            teacher_ids.update(
                TeacherFollower.objects.filter(user=user).values_list('teacher_id', flat=True)
            )

        prioritize_behavioural = InterestScoringService.should_prioritize_behavioural(
            user=user, guest_device_id=guest_device_id,
        )

        # Previous viewing behaviour: subjects of recently watched lessons,
        # plus lessons already watched to completion (to be demoted).
        seen_ids: set = set()
        completed_ids: set = set()
        behaviour_subject_ids: set = set()
        try:
            viewer_q = Q()
            if user and getattr(user, 'is_authenticated', False):
                viewer_q |= Q(user=user)
            if guest_device_id:
                viewer_q |= Q(guest_device_id=guest_device_id)

            if viewer_q:
                cutoff = now - timedelta(days=PersonalizedRecommendationService.BEHAVIOUR_WINDOW_DAYS)
                interactions = UserInteraction.objects.filter(
                    viewer_q,
                    created_at__gte=cutoff,
                ).values_list('lesson_id', 'interaction_type')[:1000]
                for lesson_id, interaction_type in interactions:
                    seen_ids.add(lesson_id)
                    if interaction_type == InteractionType.WATCH_COMPLETE:
                        completed_ids.add(lesson_id)

                if seen_ids:
                    behaviour_subject_ids = set(
                        FeedLesson.objects.filter(id__in=list(seen_ids))
                        .exclude(subject_id=None)
                        .values_list('subject_id', flat=True)
                    )
        except Exception:
            logger.debug("Behavioural signal gathering failed", exc_info=True)

        return {
            'subject_ids': subject_ids,
            'teacher_ids': teacher_ids,
            'tag_ids': tag_ids,
            'level_id': level_id,
            'class_id': class_id,
            'prioritize_behavioural': prioritize_behavioural,
            'seen_ids': seen_ids,
            'completed_ids': completed_ids,
            'behaviour_subject_ids': behaviour_subject_ids,
        }

    @classmethod
    def _score_lesson(cls, lesson: FeedLesson, signals: dict, now) -> float:
        """Composite 0-100 recommendation score for a single lesson."""
        # ── Freshness (exponential decay, new-upload boost) ─────
        published_at = lesson.published_at or lesson.created_at
        age_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
        freshness = 100.0 * math.pow(0.5, age_hours / cls.FRESHNESS_HALF_LIFE_HOURS)
        if age_hours <= cls.NEW_POST_WINDOW_HOURS:
            freshness = min(100.0, freshness + cls.NEW_POST_BOOST)

        # ── Relevance (interests + viewing behaviour) ───────────
        relevance = 0.0
        if lesson.subject_id and lesson.subject_id in signals['subject_ids']:
            relevance += 30.0
        elif lesson.subject_id and lesson.subject_id in signals['behaviour_subject_ids']:
            relevance += 18.0
        if lesson.teacher_id and lesson.teacher_id in signals['teacher_ids']:
            relevance += 25.0
        if signals['level_id'] and lesson.level_id == signals['level_id']:
            relevance += 15.0
        if signals['class_id'] and lesson.class_obj_id == signals['class_id']:
            relevance += 15.0
        if signals['tag_ids']:
            lesson_tag_ids = {tag.id for tag in lesson.tags.all()}
            if lesson_tag_ids & signals['tag_ids']:
                relevance += 15.0
        relevance = min(relevance, 100.0)
        if signals['prioritize_behavioural']:
            relevance = min(relevance * 1.5, 100.0)

        # ── Popularity (log-scaled engagement) ──────────────────
        popularity = min(
            100.0,
            math.log10(1 + max(0, lesson.view_count)) * 15.0 +
            math.log10(1 + max(0, lesson.like_count)) * 20.0 +
            math.log10(1 + max(0, lesson.comment_count)) * 12.0 +
            math.log10(1 + max(0, lesson.share_count)) * 18.0 +
            math.log10(1 + max(0, lesson.save_count)) * 14.0,
        )

        # ── Quality (completion + watch-through signals) ────────
        quality = (
            float(lesson.completion_rate or 0) * 0.6 +
            float(lesson.quality_score or 0) * 0.4
        )

        # ── Exploration jitter (controlled randomisation) ───────
        jitter = random.uniform(0.0, cls.EXPLORATION_JITTER_MAX)

        score = (
            freshness * (cls.WEIGHT_FRESHNESS / 100.0) +
            relevance * (cls.WEIGHT_RELEVANCE / 100.0) +
            popularity * (cls.WEIGHT_POPULARITY / 100.0) +
            quality * (cls.WEIGHT_QUALITY / 100.0) +
            jitter
        )

        # Demote lessons the viewer already watched to completion so the
        # feed surfaces fresh material first (they can still reappear later).
        if lesson.id in signals['completed_ids']:
            score -= cls.COMPLETED_PENALTY

        return score

    @classmethod
    def _interleave_discovery(
        cls,
        ranked: List[FeedLesson],
        base_qs,
        exclude_ids: set,
    ) -> List[FeedLesson]:
        """Inject ~8% serendipitous quality content into the ranked list."""
        existing_ids = {lesson.id for lesson in ranked}
        target_count = max(1, int(len(ranked) * cls.DISCOVERY_FRACTION))

        discovery_pool = list(
            base_qs.filter(quality_score__gte=40)
            .exclude(id__in=list(existing_ids | exclude_ids))
            .order_by('?')
            .values_list('id', flat=True)[:target_count * 2]
        )
        if not discovery_pool:
            return ranked

        random.shuffle(discovery_pool)

        result: List[FeedLesson] = []
        discovery_iter = iter(discovery_pool)
        for index, lesson in enumerate(ranked):
            result.append(lesson)
            if (index + 1) % cls.DISCOVERY_EVERY_N == 0:
                discovery_id = next(discovery_iter, None)
                if discovery_id is not None and discovery_id not in existing_ids:
                    discovered = FeedLesson.objects.filter(id=discovery_id).first()
                    if discovered is not None:
                        result.append(discovered)
                        existing_ids.add(discovery_id)
        return result

    @classmethod
    def apply_diversity_spacing(cls, ranked: List[FeedLesson]) -> List[FeedLesson]:
        """
        Greedy reorder enforcing limits on consecutive same-teacher /
        same-subject runs, searching a small lookahead window for a
        replacement when a constraint would be violated.
        """
        result: List[FeedLesson] = []
        pending = list(ranked)

        while pending:
            placed = False
            window = pending[:cls.DIVERSITY_LOOKAHEAD]
            for offset, candidate in enumerate(window):
                if cls._can_append(result, candidate):
                    result.append(pending.pop(offset))
                    placed = True
                    break
            if not placed:
                # Constraints cannot be satisfied within the lookahead;
                # take the next best item anyway.
                result.append(pending.pop(0))
        return result

    @classmethod
    def _can_append(cls, result: List[FeedLesson], candidate: FeedLesson) -> bool:
        teacher_run = 0
        subject_run = 0
        for lesson in reversed(result):
            if lesson.teacher_id == candidate.teacher_id:
                teacher_run += 1
            else:
                break
        if teacher_run >= cls.MAX_CONSECUTIVE_SAME_TEACHER:
            return False

        for lesson in reversed(result):
            if lesson.subject_id and lesson.subject_id == candidate.subject_id:
                subject_run += 1
            else:
                break
        if subject_run >= cls.MAX_CONSECUTIVE_SAME_SUBJECT:
            return False
        return True

    # ════════════════════════════════════════════════════════════
    # Backwards-compatible entry point (page-based callers)
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def get_blended_feed(
        user=None,
        guest_device_id: str = '',
        page: int = 1,
        page_size: int = 12,
        school_id: Optional[int] = None,
    ) -> List[FeedLesson]:
        """
        Legacy page-based API retained for compatibility. New callers
        should use create_snapshot()/get_snapshot() for stable cursored
        pagination.
        """
        _, ids = PersonalizedRecommendationService.create_snapshot(
            user=user, guest_device_id=guest_device_id, school_id=school_id,
        )
        page_ids = ids[(page - 1) * page_size: page * page_size]
        return PersonalizedRecommendationService.fetch_lessons_ordered(page_ids)

    @staticmethod
    def fetch_lessons_ordered(ids: List[int]) -> List[FeedLesson]:
        """Fetch lessons preserving the given id order."""
        if not ids:
            return []
        lessons = {
            lesson.id: lesson
            for lesson in FeedLesson.objects.filter(id__in=ids)
                .prefetch_related('tags')
        }
        return [lessons[lid] for lid in ids if lid in lessons]
