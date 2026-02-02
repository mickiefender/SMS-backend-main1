from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.students.views import GradeViewSet, StudentPortalViewSet, StudentBillingViewSet, StudentSocialClubViewSet

router = DefaultRouter()
router.register(r'grades', GradeViewSet, basename='grade')
router.register(r'student-portal', StudentPortalViewSet, basename='student-portal')
router.register(r'student-billing', StudentBillingViewSet, basename='student-billing')
router.register(r'social-clubs', StudentSocialClubViewSet, basename='social-club')

urlpatterns = [
    path('', include(router.urls)),
]
