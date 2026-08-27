from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from apps.users.views import AuthViewSet, UserViewSet, TeacherViewSet, StudentViewSet, CurrentUserView, AdminStaffViewSet

router = DefaultRouter()
router.register(r'teachers', TeacherViewSet, basename='teacher')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'admin-staff', AdminStaffViewSet, basename='admin-staff')
router.register(r'users', UserViewSet, basename='user')  # Changed from r'' to r'users' to avoid path conflicts

urlpatterns = [
    path('auth/register/', AuthViewSet.as_view({'post': 'register'}), name='register'),
    path('auth/login/', AuthViewSet.as_view({'post': 'login'}), name='login'),
    # JWT refresh endpoint under the /api/users/ namespace — this is the URL
    # the mobile client uses to silently renew an expired access token using
    # the stored refresh token. Without it the client's refresh call 404s,
    # which previously forced users to manually log out/in after expiry.
    # SimpleJWT's standard view: POST {"refresh": "<token>"} -> {"access": "..."}
    # Returns 401 for expired/invalid refresh tokens (terminal session end).
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', CurrentUserView.as_view(), name='current-user'),
    path('', include(router.urls)),
]
