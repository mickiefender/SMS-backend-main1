from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.schools.views import SchoolViewSet, PlanViewSet, SubscriptionViewSet, AnnouncementViewSet
from apps.schools.news_views import NewsViewSet

router = DefaultRouter()
router.register(r'schools', SchoolViewSet, basename='school')
router.register(r'plans', PlanViewSet, basename='plan')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'announcements', AnnouncementViewSet, basename='announcement')
router.register(r'news', NewsViewSet, basename='news')

urlpatterns = [
    path('', include(router.urls)),
]
