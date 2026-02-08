from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MessageViewSet, AnnouncementViewSet, NoticeViewSet

router = DefaultRouter()
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'announcements', AnnouncementViewSet, basename='announcement')
router.register(r'notices', NoticeViewSet, basename='notice')

urlpatterns = [
    path('', include(router.urls)),
]
