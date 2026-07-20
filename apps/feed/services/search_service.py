"""
Search service using PostgreSQL full-text search and trigram fallback.
"""
from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramSimilarity
from django.db.models import F, Q, Value
from django.db.models.functions import Concat

from apps.feed import models
from apps.feed.services.analytics_service import AnalyticsService


class SearchService:
    DEFAULT_SEARCH_FIELDS = ['title', 'topic', 'description']

    @staticmethod
    def search(
        query_text: str,
        user=None,
        school_id=None,
        level_id=None,
        class_id=None,
        subject_id=None,
        teacher_id=None,
    ):
        """
        Full-text search over lessons. Returns a queryset annotated with rank.
        """
        if not query_text or not query_text.strip():
            return models.FeedLesson.objects.none()

        qs = models.FeedLesson.objects.filter(
            status='approved',
            visibility='public',
        )

        # Apply optional filters
        if school_id:
            qs = qs.filter(school_id=school_id)
        if level_id:
            qs = qs.filter(level_id=level_id)
        if class_id:
            qs = qs.filter(class_obj_id=class_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)

        # Save search query for analytics
        AnalyticsService.track_search(query_text, user=user, school_id=school_id)

        search_query = SearchQuery(query_text, config='english')
        qs = qs.annotate(
            rank=SearchRank(F('search_vector'), search_query)
        ).filter(search_vector=search_query)

        # Fallback to trigram similarity when no full-text matches found
        if not qs.exists():
            qs = models.FeedLesson.objects.filter(
                status='approved',
                visibility='public',
            ).annotate(
                similarity=TrigramSimilarity('title', query_text)
            ).filter(similarity__gt=0.1).order_by('-similarity')

            if school_id:
                qs = qs.filter(school_id=school_id)
            if level_id:
                qs = qs.filter(level_id=level_id)
            if class_id:
                qs = qs.filter(class_obj_id=class_id)
            if subject_id:
                qs = qs.filter(subject_id=subject_id)
            if teacher_id:
                qs = qs.filter(teacher_id=teacher_id)

        return qs.order_by('-rank', '-published_at')

    @staticmethod
    def autocomplete_tags(query_text: str, limit: int = 10):
        return models.FeedTag.objects.annotate(
            similarity=TrigramSimilarity('name', query_text)
        ).filter(similarity__gt=0.2).order_by('-similarity')[:limit]

    @staticmethod
    def autocomplete_subjects(query_text: str, limit: int = 10):
        return models.FeedSubject.objects.annotate(
            similarity=TrigramSimilarity('name', query_text)
        ).filter(similarity__gt=0.2).order_by('-similarity')[:limit]

    @staticmethod
    def teacher_search(query_text: str):
        """Search verified teachers by name or bio."""
        from apps.users.models import TeacherProfile
        return TeacherProfile.objects.annotate(
            full_name=Concat(
                F('user__first_name'), Value(' '), F('user__last_name')
            )
        ).filter(
            Q(user__first_name__icontains=query_text) |
            Q(user__last_name__icontains=query_text) |
            Q(bio__icontains=query_text) |
            Q(specialization__icontains=query_text)
        ).distinct()
