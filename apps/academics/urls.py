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
    GradingScaleViewSet, GradingAssessmentViewSet
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

urlpatterns = [
    path('', include(router.urls)),
]
