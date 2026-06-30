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
    Allows school admins (higher) or users uploading for themselves
    """
    def has_object_permission(self, request, view, obj):
        return (
            request.user.role in ['super_admin', 'school_admin'] or
            obj.user_id == request.user.id
        )

    def has_permission(self, request, view):
        if request.user.role in ['super_admin', 'school_admin']:
            return True
        # For self-upload, check if data targets self
        if getattr(request, 'method', '') in permissions.SAFE_METHODS:
            return True  # Read always allowed for authenticated
        user_id = request.data.get('user')
        return user_id == request.user.id

