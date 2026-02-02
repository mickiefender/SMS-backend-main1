from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.assignments.views import AssignmentViewSet, AssignmentSubmissionViewSet

router = DefaultRouter()
router.register(r'submissions', AssignmentSubmissionViewSet, basename='submission')
router.register(r'', AssignmentViewSet, basename='assignment')

urlpatterns = [
    path('', include(router.urls)),
]
