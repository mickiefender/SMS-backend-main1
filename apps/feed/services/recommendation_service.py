"""
Recommendation engine for the Alara Learning Feed.

Authenticated recommendations blend:
  - Academic level / class / preferred subjects
  - Watch history, completion, liked/saved lessons, followed teachers
  - Trending score, teacher quality, freshness, popularity, diversity
  - Random exploration

Guest recommendations are based solely on popularity signals.
"""
import random
from datetime import timedelta
from decimal import Decimal
from typing import List, Optional

from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, Value, When
from django.utils import timezone

from apps.feed import models
from apps.feed.utils import hash_ip


class RecommendationService:
    EXPLORATION_FRACTION = 0.10
    CACHE_TTL_SECONDS = 900  # 15 minutes

    @staticmethod
    def _base_public_queryset():
        return models.FeedLesson.objects.filter(
            status='approved',
            visibility='public',
            published_at__isnull=False,
        )

    @staticmethod
    def get_guest_recommendations(
        strategy: str = 'trending',
        school_id: Optional[int] = None,
        ip: Optional[str] = None,
    ):
        """
        Guest feeds: trending, latest, most_viewed, most_liked, highest_completion,
        featured_teachers, editor_picks.
        """
        qs = RecommendationService._base_public_queryset()
        if school_id:
            qs = qs.filter(school_id=school_id)

        if strategy == 'trending':
            qs = qs.annotate(
                engagement_score=RecommendationService._engagement_score()
            )
            return qs.order_by(
                '-engagement_score', '-trending_score', '-published_at', '-pk'
            )
        if strategy == 'latest':
            return qs.order_by('-published_at')
        if strategy == 'most_viewed':
            return qs.order_by('-view_count', '-published_at')
        if strategy == 'most_liked':
            return qs.order_by('-like_count', '-published_at')
        if strategy == 'highest_completion':
            return qs.order_by('-completion_rate', '-published_at')
        if strategy == 'featured_teachers':
            # Boost lessons from teachers with high aggregate quality.
            featured = models.FeedLesson.objects.raw(
                """
                SELECT l.*
                FROM feed_feedlesson l
                JOIN (
                    SELECT teacher_id, AVG(quality_score) AS avg_quality
                    FROM feed_feedlesson
                    WHERE status = 'approved' AND visibility = 'public'
                    GROUP BY teacher_id
                    HAVING AVG(quality_score) >= 70
                ) t ON t.teacher_id = l.teacher_id
                WHERE l.status = 'approved' AND l.visibility = 'public'
                ORDER BY t.avg_quality DESC, l.published_at DESC
                """
            )
            return models.FeedLesson.objects.filter(
                id__in=[x.id for x in featured]
            ).order_by('-published_at')
        if strategy == 'editor_picks':
            return qs.filter(extra_metadata__editor_pick=True).order_by('-published_at')

        return qs.annotate(
            engagement_score=RecommendationService._engagement_score()
        ).order_by('-engagement_score', '-trending_score', '-published_at', '-pk')

    @staticmethod
    def _engagement_score():
        """Calculate a live fallback while scheduled trending scores catch up."""
        return ExpressionWrapper(
            F('view_count')
            + F('unique_view_count') * Decimal('2.0')
            + F('like_count') * Decimal('4.0')
            + F('save_count') * Decimal('5.0')
            + F('comment_count') * Decimal('3.0')
            + F('share_count') * Decimal('6.0')
            + F('completion_rate') * Decimal('10.0')
            + F('avg_watch_seconds') * Decimal('0.1'),
            output_field=DecimalField(max_digits=18, decimal_places=6),
        )

    @staticmethod
    def get_recommendations_for_user(
        user,
        strategy: str = 'personalized',
        school_id: Optional[int] = None,
    ):
        """
        Personalized recommendations for authenticated users.
        """
        qs = RecommendationService._base_public_queryset()
        if school_id:
            qs = qs.filter(school_id=school_id)

        profile = getattr(user, 'learning_profile', None)
        followed_teacher_ids = list(
            models.TeacherFollower.objects.filter(user=user).values_list('teacher_id', flat=True)
        )
        liked_lesson_ids = list(
            models.FeedLike.objects.filter(user=user).values_list('lesson_id', flat=True)
        )
        saved_lesson_ids = list(
            models.FeedSave.objects.filter(user=user).values_list('lesson_id', flat=True)
        )
        watched_lesson_ids = list(
            models.WatchHistory.objects.filter(user=user).values_list('lesson_id', flat=True)
        )

        # Build candidate queryset
        candidates = qs
        subject_ids = []
        level_id = None
        class_id = None

        if profile:
            level_id = profile.preferred_level_id
            class_id = profile.preferred_class_id
            subject_ids = list(profile.preferred_subjects.values_list('id', flat=True))

        filters = Q()
        if level_id:
            filters |= Q(level_id=level_id)
        if class_id:
            filters |= Q(class_obj_id=class_id)
        if subject_ids:
            filters |= Q(subject_id__in=subject_ids)
        if followed_teacher_ids:
            filters |= Q(teacher_id__in=followed_teacher_ids)

        # Always include some recent content for freshness
        recent_window = timezone.now() - timedelta(days=30)
        filters |= Q(published_at__gte=recent_window)

        candidates = candidates.filter(filters)

        # Exclude already watched content unless user explicitly wants "continue"
        if strategy != 'continue_watching':
            candidates = candidates.exclude(id__in=watched_lesson_ids)

        # Scoring annotations
        candidates = candidates.annotate(
            engagement_score=RecommendationService._engagement_score(),
            pref_subject_match=Case(
                When(subject_id__in=subject_ids, then=Value(20)),
                default=Value(0),
            ),
            pref_level_match=Case(
                When(level_id=level_id, then=Value(15)),
                default=Value(0),
            ),
            pref_class_match=Case(
                When(class_obj_id=class_id, then=Value(15)),
                default=Value(0),
            ),
            followed_match=Case(
                When(teacher_id__in=followed_teacher_ids, then=Value(25)),
                default=Value(0),
            ),
            liked_similarity=Case(
                When(id__in=liked_lesson_ids, then=Value(5)),
                default=Value(0),
            ),
        )

        # Composite recommendation score
        candidates = candidates.annotate(
            rec_score=(
                F('trending_score') * Decimal('0.5') +
                F('engagement_score') * Decimal('0.5') +
                F('quality_score') * Decimal('0.3') +
                F('completion_rate') * Decimal('0.2') +
                F('pref_subject_match') +
                F('pref_level_match') +
                F('pref_class_match') +
                F('followed_match') +
                F('liked_similarity')
            )
        ).order_by('-rec_score', '-published_at')

        # Diversity injection: swap every Nth item with a random high-quality lesson
        candidate_ids = list(candidates.values_list('id', flat=True)[:500])
        if strategy == 'personalized' and candidate_ids:
            diversified = RecommendationService._inject_diversity(
                candidate_ids, subject_ids, watched_lesson_ids
            )
            candidates = models.FeedLesson.objects.filter(id__in=diversified).order_by(
                Case(*[When(id=pk, then=Value(idx)) for idx, pk in enumerate(diversified)])
            )

        return candidates

    @staticmethod
    def get_continue_watching(user):
        """Lessons the user started but did not finish."""
        return models.FeedLesson.objects.filter(
            watch_history__user=user,
            watch_history__is_completed=False,
            status='approved',
            visibility='public',
        ).order_by('-watch_history__last_watched_at')

    @staticmethod
    def _inject_diversity(
        candidate_ids: List[int],
        subject_ids: List[int],
        exclude_ids: List[int],
    ) -> List[int]:
        """
        Replace roughly EXPLORATION_FRACTION of the top results with random
        high-quality lessons from subjects the user has NOT explicitly chosen.
        """
        result = list(candidate_ids)
        count = max(1, int(len(result) * RecommendationService.EXPLORATION_FRACTION))
        explore_qs = models.FeedLesson.objects.filter(
            status='approved',
            visibility='public',
        ).exclude(
            id__in=exclude_ids + result
        )
        if subject_ids:
            explore_qs = explore_qs.exclude(subject_id__in=subject_ids)

        explore_qs = explore_qs.filter(
            quality_score__gte=Decimal('60.00')
        ).order_by('?')[:count * 2]

        explore_ids = list(explore_qs.values_list('id', flat=True))
        random.shuffle(explore_ids)

        for idx in range(0, min(count, len(explore_ids)) * 3, 3):
            if explore_ids:
                replace_idx = min(idx + 2, len(result) - 1)
                result[replace_idx] = explore_ids.pop()
        return result

    @staticmethod
    def cache_key(user, strategy: str, school_id: Optional[int]) -> str:
        return f"feed:rec:{user.id}:{strategy}:{school_id or 'global'}"

    @staticmethod
    def invalidate_user_cache(user):
        from django.core.cache import cache
        keys = [f"feed:rec:{user.id}:*"]
        # Redis wildcard deletion helper
        try:
            client = cache.client.get_client()
            for pattern in keys:
                for key in client.scan_iter(match=pattern):
                    client.delete(key)
        except Exception:
            pass

    @staticmethod
    def get_guest_cache_key(strategy: str, school_id: Optional[int], ip: Optional[str]) -> str:
        ip_hash = hash_ip(ip or 'unknown')
        return f"feed:guest:{strategy}:{school_id or 'global'}:{ip_hash}"
