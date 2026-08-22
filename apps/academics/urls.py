from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.academics.views import (
    FacultyViewSet, DepartmentViewSet, LevelViewSet, SubjectViewSet,
    ClassViewSet, ClassSubjectViewSet, EnrollmentViewSet, TimetableViewSet,
    AcademicCalendarEventViewSet, ExamViewSet, ExamResultViewSet, SchoolFeesViewSet,
    SchoolEventViewSet, NoticeViewSet, UserProfilePictureViewSet,
    ClassTeacherViewSet, StudentClassViewSet, ClassSubjectTeacherViewSet,
    AcademicSessionViewSet, TerminalReportViewSet, GradingPolicyViewSet,
    TerminalReportTemplateViewSet, AssessmentViewSet,
    GradingScaleViewSet, GradingAssessmentViewSet, AssessmentTypeViewSet
)
from apps.academics.promotion_views import (
    AcademicYearViewSet, PromotionRuleViewSet, PromotionPolicyViewSet,
    PromotionBatchViewSet, PromotionPreviewView, PromotionBulkView,
    StudentPromoteView, StudentAcademicHistoryView,
)
from apps.academics.views_documents import DocumentViewSet, DocumentFolderViewSet

router = DefaultRouter()
router.register(r'faculties', FacultyViewSet, basename='faculty')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'levels', LevelViewSet, basename='level')
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'classes', ClassViewSet, basename='class')
router.register(r'class-subjects', ClassSubjectViewSet, basename='class-subject')
router.register(r'class-teachers', ClassTeacherViewSet, basename='class-teacher')
router.register(r'student-classes', StudentClassViewSet, basename='student-class')
router.register(r'class-subject-teachers', ClassSubjectTeacherViewSet, basename='class-subject-teacher')
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'timetables', TimetableViewSet, basename='timetable')
router.register(r'calendar-events', AcademicCalendarEventViewSet, basename='calendar-event')
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'exam-results', ExamResultViewSet, basename='exam-result')
router.register(r'school-fees', SchoolFeesViewSet, basename='school-fees')
router.register(r'events', SchoolEventViewSet, basename='event')
router.register(r'documents', DocumentViewSet, basename='document')
router.register(r'document-folders', DocumentFolderViewSet, basename='document-folder')
router.register(r'notices', NoticeViewSet, basename='notice')
router.register(r'profile-pictures', UserProfilePictureViewSet, basename='profile-picture')
router.register(r'academic-sessions', AcademicSessionViewSet, basename='academic-session')
router.register(r'terminal-reports', TerminalReportViewSet, basename='terminal-report')
router.register(r'grading-policies', GradingPolicyViewSet, basename='grading-policy')
router.register(r'terminal-report-templates', TerminalReportTemplateViewSet, basename='terminal-report-template')
router.register(r'assessments', AssessmentViewSet, basename='assessment')
router.register(r'grading-scales', GradingScaleViewSet, basename='grading-scale')
router.register(r'grading-assessments', GradingAssessmentViewSet, basename='grading-assessment')
router.register(r'assessment-types', AssessmentTypeViewSet, basename='assessment-type')
router.register(r'academic-years', AcademicYearViewSet, basename='academic-year')
router.register(r'promotion-rules', PromotionRuleViewSet, basename='promotion-rule')
router.register(r'promotion-policy', PromotionPolicyViewSet, basename='promotion-policy')
router.register(r'promotion-batches', PromotionBatchViewSet, basename='promotion-batch')

urlpatterns = [
    path('', include(router.urls)),
    # Student promotion workflow
    path('promotion/preview/', PromotionPreviewView.as_view(), name='promotion-preview'),
    path('promotion/bulk/', PromotionBulkView.as_view(), name='promotion-bulk'),
    path('students/<int:student_id>/promote/', StudentPromoteView.as_view(), name='student-promote'),
    path('students/<int:student_id>/academic-history/', StudentAcademicHistoryView.as_view(), name='student-academic-history'),
]
