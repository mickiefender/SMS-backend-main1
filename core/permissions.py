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


# ─────────────────────────────────────────────────────────────────────────────
# Admin-staff (granular) permissions
#
# "Admin staff" are school-level staff accounts (academic_admin, exam_officer,
# finance_officer, ct_admin_support) created by the school admin. Each account
# carries a set of granular permission codes (RolePermission.permission), e.g.
# 'manage_subjects', 'manage_fees'. These mirror the codes the frontend uses
# to gate sidebar pages (frontend/lib/permissions.ts).
# ─────────────────────────────────────────────────────────────────────────────

STAFF_ROLES = {'academic_admin', 'exam_officer', 'finance_officer', 'ct_admin_support'}
ADMIN_ROLES = {'super_admin', 'school_admin'}


def user_has_permission(user, *codes):
    """
    True when the user may perform an action guarded by any of ``codes``.

    - super_admin / school_admin: always allowed.
    - Admin-staff roles: allowed when their RolePermission record contains at
      least one of the codes.
    - Everyone else (teacher, student, parent): not allowed.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    role = getattr(user, 'role', None)
    if role in ADMIN_ROLES:
        return True
    if role not in STAFF_ROLES:
        return False
    try:
        role_permission = user.role_permission
    except Exception:
        return False
    return any(role_permission.has_permission(code) for code in codes)


def make_permission_class(*codes):
    """Build a DRF permission class guarding an action behind permission codes."""
    class HasAnyPermission(permissions.BasePermission):
        message = "You do not have permission to perform this action."

        def has_permission(self, request, view):
            return user_has_permission(request.user, *codes)

    HasAnyPermission.__name__ = f"HasAnyPermission_{'_or_'.join(codes)}"
    HasAnyPermission.__qualname__ = HasAnyPermission.__name__
    return HasAnyPermission


def make_staff_or_teacher_permission(*codes):
    """
    Permission class allowing admins, teachers, or admin-staff holding any of
    ``codes``. Used for endpoints teachers already had access to (exams,
    grades, attendance) that staff admins with the matching permission
    should also be able to use.
    """
    class StaffOrTeacherPermission(permissions.BasePermission):
        message = "You do not have permission to perform this action."

        def has_permission(self, request, view):
            user = request.user
            if not user or not getattr(user, 'is_authenticated', False):
                return False
            if getattr(user, 'role', None) == 'teacher':
                return True
            return user_has_permission(user, *codes)

    StaffOrTeacherPermission.__name__ = f"StaffOrTeacher_{'_or_'.join(codes)}"
    StaffOrTeacherPermission.__qualname__ = StaffOrTeacherPermission.__name__
    return StaffOrTeacherPermission


# Named permission singletons — one per feature area, matching the frontend
# permission codes in frontend/lib/permissions.ts.
CanManageSubjects = make_permission_class('manage_subjects')
CanManageClasses = make_permission_class('manage_classes')
CanManageStudents = make_permission_class('manage_students')
CanManageTeachers = make_permission_class('manage_teachers')
CanManageStudentAssignment = make_permission_class('manage_student_assignment', 'manage_students')
CanManageTeacherAssignment = make_permission_class('manage_teacher_assignment', 'manage_teachers')
CanManageTimetable = make_permission_class('manage_timetable')
CanManageFees = make_permission_class('manage_fees')
CanCollectFees = make_permission_class('collect_fees', 'manage_fees')
CanManageExpenses = make_permission_class('manage_expenses')
CanManageNotices = make_permission_class('manage_notices')
CanSendMessages = make_permission_class('send_messages')
CanManageEvents = make_permission_class('manage_events')
CanManageNews = make_permission_class('manage_news')
CanManageSchoolProfile = make_permission_class('manage_school_profile')
CanManageGradingPolicy = make_permission_class('manage_grading_policy')
CanManageReportTemplates = make_permission_class('manage_report_templates')
CanManageAdminStaff = make_permission_class('manage_admins')
CanViewPerformance = make_permission_class('view_performance', 'export_results')
CanViewRecipients = make_permission_class('send_messages', 'manage_notices')
CanManageAcademicSessions = make_permission_class('manage_grading_policy', 'manage_school_profile')
CanManageAssessmentTypes = make_permission_class('manage_grading_policy', 'manage_exams')

# Teacher-inclusive variants: admins + teachers + permitted admin staff.
CanManageExamsOrTeach = make_staff_or_teacher_permission('manage_exams')
CanManageGradesOrTeach = make_staff_or_teacher_permission('manage_grades')
CanManageAssessmentsOrTeach = make_staff_or_teacher_permission('manage_grades', 'manage_exams')
CanManageAttendanceOrTeach = make_staff_or_teacher_permission('manage_attendance')


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
