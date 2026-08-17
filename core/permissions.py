"""
Custom permission classes for role-based access control
"""
from rest_framework import permissions


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'super_admin'


class IsSchoolAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'school_admin'


class IsTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'teacher'


class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'student'


class IsSchoolAdminOrTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['school_admin', 'teacher']


class IsSchoolAdminOrHigher(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['super_admin', 'school_admin']


class IsSchoolAdminOrSelf(permissions.BasePermission):
    """
    Allows school admins (higher) or users uploading for themselves.
    """
    def has_object_permission(self, request, view, obj):
        return (
            request.user.role in ['super_admin', 'school_admin'] or
            obj.user_id == request.user.id
        )

    def has_permission(self, request, view):
        if request.user.role in ['super_admin', 'school_admin']:
            return True
        # Read always allowed for authenticated users.
        if getattr(request, 'method', '') in permissions.SAFE_METHODS:
            return True
        # A non-admin may only upload/edit for themselves. When no 'user'
        # field is supplied the view targets request.user (self-upload), so
        # that is allowed too. If a 'user' field IS present it must match.
        if request.data is None:
            return True
        user_id = request.data.get('user')
        return user_id is None or str(user_id) == str(request.user.id)
