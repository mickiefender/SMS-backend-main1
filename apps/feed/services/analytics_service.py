"""
Analytics service: records events, updates counters, and aggregates daily metrics.
"""
from datetime import date
from django.db.models import F, Avg
from django.utils import timezone

from apps.feed import models


class AnalyticsService:
    @staticmethod
    def _get_or_create_analytics(lesson: models.FeedLesson) -> models.LessonAnalytics:
        obj, _ = models.LessonAnalytics.objects.get_or_create(lesson=lesson)
        return obj

    @staticmethod
    def track_view(lesson: models.FeedLesson, user=None):
        """Track a lesson view. For unique views, rely on watch history."""
        lesson.view_count = F('view_count') + 1
        lesson.save(update_fields=['view_count'])
        lesson.refresh_from_db()

        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.views = F('views') + 1
        analytics.save(update_fields=['views'])

        if user and user.is_authenticated:
            already_watched = models.WatchHistory.objects.filter(
                user=user, lesson=lesson
            ).exists()
            if not already_watched:
                lesson.unique_view_count = F('unique_view_count') + 1
                lesson.save(update_fields=['unique_view_count'])
                analytics.unique_views = F('unique_views') + 1
                analytics.save(update_fields=['unique_views'])

        AnalyticsService._bump_daily_metric('views', lesson.school_id)

    @staticmethod
    def track_like(lesson: models.FeedLesson):
        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.likes = F('likes') + 1
        analytics.save(update_fields=['likes'])
        AnalyticsService._bump_daily_metric('likes', lesson.school_id)

    @staticmethod
    def track_unlike(lesson: models.FeedLesson):
        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.likes = F('likes') - 1
        analytics.save(update_fields=['likes'])

    @staticmethod
    def track_save(lesson: models.FeedLesson):
        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.saves = F('saves') + 1
        analytics.save(update_fields=['saves'])
        AnalyticsService._bump_daily_metric('saves', lesson.school_id)

    @staticmethod
    def track_unsave(lesson: models.FeedLesson):
        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.saves = F('saves') - 1
        analytics.save(update_fields=['saves'])

    @staticmethod
    def track_comment(lesson: models.FeedLesson):
        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.comments = F('comments') + 1
        analytics.save(update_fields=['comments'])
        AnalyticsService._bump_daily_metric('comments', lesson.school_id)

    @staticmethod
    def track_share(lesson: models.FeedLesson):
        lesson.share_count = F('share_count') + 1
        lesson.save(update_fields=['share_count'])
        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.shares = F('shares') + 1
        analytics.save(update_fields=['shares'])
        AnalyticsService._bump_daily_metric('shares', lesson.school_id)

    @staticmethod
    def track_download(lesson: models.FeedLesson):
        lesson.download_count = F('download_count') + 1
        lesson.save(update_fields=['download_count'])
        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.downloads = F('downloads') + 1
        analytics.save(update_fields=['downloads'])

    @staticmethod
    def track_completion(lesson: models.FeedLesson):
        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.completions = F('completions') + 1
        analytics.save(update_fields=['completions'])
        AnalyticsService._bump_daily_metric('completions', lesson.school_id)

    @staticmethod
    def update_watch_metrics(lesson: models.FeedLesson):
        """Recompute average watch time and completion rate from watch history."""
        stats = models.WatchHistory.objects.filter(lesson=lesson).aggregate(
            avg_watch=Avg('watch_seconds'),
            avg_completion=Avg('completion_percentage'),
        )
        lesson.avg_watch_seconds = stats['avg_watch'] or 0
        lesson.completion_rate = stats['avg_completion'] or 0
        lesson.save(update_fields=['avg_watch_seconds', 'completion_rate'])

        analytics = AnalyticsService._get_or_create_analytics(lesson)
        analytics.avg_watch_seconds = lesson.avg_watch_seconds
        analytics.completion_rate = lesson.completion_rate
        analytics.save(update_fields=['avg_watch_seconds', 'completion_rate'])

    @staticmethod
    def _bump_daily_metric(metric_name: str, school_id=None, dimension: str = ''):
        today = date.today()
        models.DailyAnalytics.objects.update_or_create(
            date=today,
            school_id=school_id,
            metric_name=metric_name,
            dimension=dimension,
            defaults={'metric_value': 0},
        )
        models.DailyAnalytics.objects.filter(
            date=today, school_id=school_id, metric_name=metric_name, dimension=dimension
        ).update(metric_value=F('metric_value') + 1)

    @staticmethod
    def track_search(query: str, user=None, school_id=None):
        models.FeedSearchQuery.objects.create(
            user=user,
            query=query,
        )
        AnalyticsService._bump_daily_metric('searches', school_id, dimension=query[:100])
