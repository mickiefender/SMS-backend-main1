from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.feed import admin_views, views, guest_views, recommendation_views, views_direct_upload

router = DefaultRouter()
router.register(r'lesson', views.FeedLessonViewSet, basename='feed-lesson')
router.register(r'notifications', views.FeedNotificationViewSet, basename='feed-notification')
router.register(r'reports', views.FeedReportViewSet, basename='feed-report')
router.register(r'moderation', views.ModerationViewSet, basename='feed-moderation')

# Super Admin lesson-metadata management (CRUD)
admin_router = DefaultRouter()
admin_router.register(r'academic-levels', admin_views.AdminAcademicLevelViewSet, basename='admin-academic-level')
admin_router.register(r'academic-classes', admin_views.AdminAcademicClassViewSet, basename='admin-academic-class')
admin_router.register(r'subjects', admin_views.AdminSubjectViewSet, basename='admin-subject')
admin_router.register(r'content-types', admin_views.AdminContentTypeViewSet, basename='admin-content-type')
admin_router.register(r'difficulty-levels', admin_views.AdminDifficultyLevelViewSet, basename='admin-difficulty-level')
admin_router.register(r'curricula', admin_views.AdminCurriculumViewSet, basename='admin-curriculum')
admin_router.register(r'learning-objectives', admin_views.AdminLearningObjectiveViewSet, basename='admin-learning-objective')
admin_router.register(r'tags', admin_views.AdminTagViewSet, basename='admin-tag')
admin_router.register(r'visibility-scopes', admin_views.AdminVisibilityScopeViewSet, basename='admin-visibility-scope')

# Comments nested under lessons
comment_list = views.FeedCommentViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
comment_detail = views.FeedCommentViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})
comment_like = views.FeedCommentViewSet.as_view({'post': 'like'})

urlpatterns = [
    path('', views.FeedView.as_view(), name='feed'),
    path('recommended/', views.RecommendedFeedView.as_view(), name='feed-recommended'),
    path('trending/', views.TrendingFeedView.as_view(), name='feed-trending'),
    path('latest/', views.LatestFeedView.as_view(), name='feed-latest'),
    path('search/', views.SearchFeedView.as_view(), name='feed-search'),
    path('continue-watching/', views.ContinueWatchingView.as_view(), name='feed-continue-watching'),
    path('watch-history/', views.WatchHistoryView.as_view(), name='feed-watch-history'),
    path('learning-profile/', views.LearningProfileView.as_view(), name='feed-learning-profile'),
    path('teacher/<int:pk>/', views.TeacherFeedView.as_view(), name='feed-teacher'),
    path('teacher/<int:pk>/follow/', views.TeacherFollowView.as_view(), name='feed-teacher-follow'),
    path('lesson/<int:lesson_id>/comments/', comment_list, name='feed-comment-list'),
    path('lesson/<int:lesson_id>/comments/<int:pk>/', comment_detail, name='feed-comment-detail'),
    path('lesson/<int:lesson_id>/comments/<int:pk>/like/', comment_like, name='feed-comment-like'),
    path('reference/levels/', views.ReferenceLevelsView.as_view(), name='feed-levels'),
    path('reference/classes/', views.ReferenceClassesView.as_view(), name='feed-classes'),
    path('reference/subjects/', views.ReferenceSubjectsView.as_view(), name='feed-subjects'),
    path('reference/tags/', views.ReferenceTagsView.as_view(), name='feed-tags'),
    path('reference/content-types/', views.ReferenceContentTypesView.as_view(), name='feed-content-types'),
    path('reference/difficulty-levels/', views.ReferenceDifficultyLevelsView.as_view(), name='feed-difficulty-levels'),
    path('reference/curricula/', views.ReferenceCurriculaView.as_view(), name='feed-curricula'),
    path('reference/learning-objectives/', views.ReferenceLearningObjectivesView.as_view(), name='feed-learning-objectives'),
    path('reference/visibility-scopes/', views.ReferenceVisibilityScopesView.as_view(), name='feed-visibility-scopes'),
    path('admin/', include(admin_router.urls)),

    # Guest (unauthenticated learner) endpoints
    path('guest/onboard/', guest_views.GuestOnboardView.as_view(), name='guest-onboard'),
    path('guest/profile/', guest_views.GuestProfileView.as_view(), name='guest-profile'),
    path('guest/feed/', guest_views.GuestFeedView.as_view(), name='guest-feed'),
    path('guest/like/', guest_views.GuestLikeView.as_view(), name='guest-like'),

    # Direct upload URL for Cloudflare Stream (bypasses nginx)
    path('direct-upload-url/', views_direct_upload.DirectUploadUrlView.as_view(), name='feed-direct-upload-url'),

    # =================================================================
    # Recommendation & Interaction Tracking endpoints (new)
    # =================================================================
    path('blended/', recommendation_views.BlendedFeedView.as_view(), name='feed-blended'),
    path('interactions/', recommendation_views.record_interaction, name='feed-interaction'),
    path('interactions/batch/', recommendation_views.record_batch_interactions, name='feed-interactions-batch'),
    path('interactions/impressions/', recommendation_views.record_impressions, name='feed-interactions-impressions'),
    path('interactions/watch/', recommendation_views.record_watch_progress, name='feed-interactions-watch'),
    path('interactions/summary/', recommendation_views.InteractionSummaryView.as_view(), name='feed-interactions-summary'),
    path('interests/', recommendation_views.InterestScoresView.as_view(), name='feed-interests'),

    path('', include(router.urls)),
]
