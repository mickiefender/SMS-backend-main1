"""
Feed-specific permissions.

Guest access:
- List/retrieve public lessons, teachers, comments, analytics aggregates.
- Cannot perform any mutating / personalized action.

Authenticated access:
- Students/parents can like, save, comment, follow, report, create learning profile.
- Teachers can upload and manage their own lessons.
- School admins / super admins can moderate content and reports.
"""
from rest_framework import permissions


class ReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


class IsGuestReadOnly(permissions.BasePermission):
    """
    Allow read-only access to unauthenticated users for public resources.
    Authenticated users are passed through to other permission classes.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated


class IsTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user and request.user.is_authenticated
            and request.user.role == 'teacher'
        )


class IsTeacherOwner(permissions.BasePermission):
    """
    Object-level permission: the object's teacher must be the current user,
    or the user is a school admin / super admin.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role in ['super_admin', 'school_admin']:
            return True
        if request.user.role == 'teacher':
            return getattr(obj, 'teacher_id', None) == request.user.id
        return False


class IsAuthenticatedStudentOrParent(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user and request.user.is_authenticated
            and request.user.role in ['student', 'parent']
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role in ['super_admin', 'school_admin']:
            return True
        return getattr(obj, 'user_id', None) == request.user.id


class IsCommentOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role in ['super_admin', 'school_admin']:
            return True
        return getattr(obj, 'user_id', None) == request.user.id


class IsModerator(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user and request.user.is_authenticated
            and request.user.role in ['super_admin', 'school_admin', 'academic_admin']
        )
