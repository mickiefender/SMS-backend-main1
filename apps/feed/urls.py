from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.feed import views

router = DefaultRouter()
router.register(r'lesson', views.FeedLessonViewSet, basename='feed-lesson')
router.register(r'notifications', views.FeedNotificationViewSet, basename='feed-notification')
router.register(r'reports', views.FeedReportViewSet, basename='feed-report')
router.register(r'moderation', views.ModerationViewSet, basename='feed-moderation')

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
    path('', include(router.urls)),
]
