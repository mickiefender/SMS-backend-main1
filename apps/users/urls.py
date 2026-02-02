from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.users.views import AuthViewSet, UserViewSet, TeacherViewSet, StudentViewSet, CurrentUserView, AdminStaffViewSet

router = DefaultRouter()
router.register(r'teachers', TeacherViewSet, basename='teacher')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'admin-staff', AdminStaffViewSet, basename='admin-staff')
router.register(r'users', UserViewSet, basename='user')  # Changed from r'' to r'users' to avoid path conflicts

urlpatterns = [
    path('auth/register/', AuthViewSet.as_view({'post': 'register'}), name='register'),
    path('auth/login/', AuthViewSet.as_view({'post': 'login'}), name='login'),
    path('me/', CurrentUserView.as_view(), name='current-user'),
    path('', include(router.urls)),
]
