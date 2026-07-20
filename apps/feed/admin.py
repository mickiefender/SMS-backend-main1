from django.contrib import admin
from apps.feed import models


@admin.register(models.FeedAcademicLevel)
class FeedAcademicLevelAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'order', 'is_active']
    search_fields = ['name', 'slug']


@admin.register(models.FeedAcademicClass)
class FeedAcademicClassAdmin(admin.ModelAdmin):
    list_display = ['name', 'level', 'slug', 'order', 'is_active']
    list_filter = ['level']
    search_fields = ['name', 'slug']


@admin.register(models.FeedSubject)
class FeedSubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active']
    search_fields = ['name', 'slug']


@admin.register(models.FeedTag)
class FeedTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'usage_count']
    search_fields = ['name', 'slug']


@admin.register(models.LearningProfile)
class LearningProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'preferred_level', 'preferred_class', 'learning_streak_days']
    list_filter = ['preferred_level', 'preferred_class']


class LessonResourceInline(admin.TabularInline):
    model = models.LessonResource
    extra = 0


@admin.register(models.FeedLesson)
class FeedLessonAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'teacher', 'school', 'subject', 'visibility',
        'status', 'verification_status', 'view_count', 'like_count',
        'published_at'
    ]
    list_filter = ['visibility', 'status', 'verification_status', 'level', 'subject']
    search_fields = ['title', 'description', 'topic']
    inlines = [LessonResourceInline]
    readonly_fields = [
        'view_count', 'unique_view_count', 'like_count', 'save_count',
        'comment_count', 'share_count', 'download_count', 'completion_rate',
        'avg_watch_seconds', 'trending_score', 'search_vector'
    ]


@admin.register(models.FeedComment)
class FeedCommentAdmin(admin.ModelAdmin):
    list_display = ['lesson', 'user', 'is_pinned', 'is_deleted', 'like_count', 'created_at']
    list_filter = ['is_pinned', 'is_deleted', 'is_moderated']


@admin.register(models.FeedReport)
class FeedReportAdmin(admin.ModelAdmin):
    list_display = ['target_type', 'reason', 'status', 'reporter', 'created_at']
    list_filter = ['target_type', 'status']


@admin.register(models.FeedNotification)
class FeedNotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']


@admin.register(models.LessonAnalytics)
class LessonAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['lesson', 'views', 'unique_views', 'completion_rate', 'updated_at']
