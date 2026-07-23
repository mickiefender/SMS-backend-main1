"""
Feed service: orchestrates feed endpoints, caching, and personalization.
"""
from typing import Optional

from django.core.cache import cache
from django.db.models import Q, Case, When, Value

from apps.feed import models
from apps.feed.services.recommendation_service import RecommendationService
from apps.feed.services.lesson_service import LessonService


class FeedService:
    CACHE_TIMEOUT = 300  # 5 minutes

    @staticmethod
    def visible_lessons(user, school_id: Optional[int] = None):
        """Return the base queryset a user is allowed to see."""
        if user and user.is_authenticated:
            q = Q(status='approved', visibility='public')
            if school_id and user.school_id == school_id:
                q |= Q(status='approved', visibility='school_only', school_id=school_id)
            q |= Q(teacher=user)
            return models.FeedLesson.objects.filter(q)
        return models.FeedLesson.objects.filter(status='approved', visibility='public')

    @staticmethod
    def get_feed(user, strategy: str = 'trending', school_id: Optional[int] = None):
        """Public feed endpoint used by both guests and authenticated users."""
        # Ranked querysets contain a user-specific rec_score annotation. IDs
        # alone cannot restore that ordering on a cache hit.
        cache_ranked_feed = not (
            user and user.is_authenticated and strategy in ('recommended', 'personalized')
        )
        cache_key = None
        if cache_ranked_feed and user and user.is_authenticated:
            cache_key = RecommendationService.cache_key(user, strategy, school_id)
        elif cache_ranked_feed:
            from apps.feed.utils import hash_ip
            cache_key = f"feed:guest:{strategy}:{school_id or 'global'}:anon"

        cached = cache.get(cache_key) if cache_key else None
        if cached is not None:
            return models.FeedLesson.objects.filter(id__in=cached).order_by(
                Case(*[When(id=pk, then=Value(idx)) for idx, pk in enumerate(cached)])
            )

        if user and user.is_authenticated:
            qs = RecommendationService.get_recommendations_for_user(user, strategy=strategy, school_id=school_id)
        else:
            qs = RecommendationService.get_guest_recommendations(strategy=strategy, school_id=school_id)

        # Cache only IDs to avoid serialization cost
        ids = list(qs.values_list('id', flat=True)[:200])
        if ids and cache_key:
            cache.set(cache_key, ids, timeout=FeedService.CACHE_TIMEOUT)
        return qs

    @staticmethod
    def get_trending(user, school_id: Optional[int] = None):
        return FeedService.get_feed(user, strategy='trending', school_id=school_id)

    @staticmethod
    def get_latest(user, school_id: Optional[int] = None):
        return FeedService.get_feed(user, strategy='latest', school_id=school_id)

    @staticmethod
    def get_teacher_feed(teacher_id: int, user):
        """Lessons published by a specific teacher visible to the requesting user."""
        qs = models.FeedLesson.objects.filter(teacher_id=teacher_id)
        if not user or not user.is_authenticated:
            qs = qs.filter(status='approved', visibility='public')
        elif user.role not in ['super_admin', 'school_admin'] and user.id != teacher_id:
            q = Q(status='approved', visibility='public')
            if user.school_id:
                q |= Q(status='approved', visibility='school_only', school_id=user.school_id)
            qs = qs.filter(q)
        return qs.order_by('-published_at')

    @staticmethod
    def get_teacher_profile(teacher_id: int, user):
        from apps.users.models import TeacherProfile
        profile = TeacherProfile.objects.select_related('user').get(user_id=teacher_id)
        lessons = FeedService.get_teacher_feed(teacher_id, user)
        follower_count = models.TeacherFollower.objects.filter(teacher_id=teacher_id).count()
        is_following = False
        if user and user.is_authenticated:
            is_following = models.TeacherFollower.objects.filter(user=user, teacher_id=teacher_id).exists()
        return {
            'profile': profile,
            'lessons': lessons,
            'follower_count': follower_count,
            'is_following': is_following,
        }

    @staticmethod
    def invalidate_feed_caches(lesson: Optional[models.FeedLesson] = None):
        """Invalidate public/guest caches when content changes."""
        try:
            client = cache.client.get_client()
            for key in client.scan_iter(match='feed:guest:*'):
                client.delete(key)
        except Exception:
            pass
        if lesson and lesson.teacher_id:
            RecommendationService.invalidate_user_cache(lesson.teacher)
