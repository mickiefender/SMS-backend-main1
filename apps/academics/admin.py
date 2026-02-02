from django.contrib import admin
from apps.academics.models import (
    Faculty, Department, Level, Subject, Class,
    ClassSubject, Enrollment, Timetable, AcademicCalendarEvent,
    Exam, ExamResult, SchoolFees, SchoolEvent, Document, Notice, UserProfilePicture,
    ClassTeacher, StudentClass, ClassSubjectTeacher, Syllabus, SyllabusTopic
)

@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'created_at')
    search_fields = ('name', 'school__name')

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'faculty', 'created_at')
    search_fields = ('name', 'faculty__name')

@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'order', 'created_at')
    search_fields = ('name', 'school__name')

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'school', 'credit_hours', 'created_at')
    search_fields = ('name', 'code', 'school__name')

@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'school', 'level', 'capacity', 'created_at')
    search_fields = ('name', 'code', 'school__name', 'level__name')

@admin.register(ClassSubject)
class ClassSubjectAdmin(admin.ModelAdmin):
    list_display = ('class_obj', 'subject', 'teacher', 'created_at')
    search_fields = ('class_obj__name', 'subject__name', 'teacher__first_name', 'teacher__last_name')

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'class_obj', 'subject', 'is_active', 'enrollment_date')
    search_fields = ('student__first_name', 'student__last_name', 'class_obj__name', 'subject__name')

@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ('class_obj', 'subject', 'teacher', 'day', 'start_time', 'end_time')
    search_fields = ('class_obj__name', 'subject__name', 'teacher__first_name', 'teacher__last_name')

@admin.register(AcademicCalendarEvent)
class AcademicCalendarEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'school', 'event_type', 'start_date', 'end_date')
    search_fields = ('title', 'school__name')

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'class_obj', 'exam_date', 'total_marks')
    search_fields = ('title', 'subject__name', 'class_obj__name')

@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'marks_obtained', 'grade')
    search_fields = ('student__first_name', 'student__last_name', 'exam__title')

@admin.register(SchoolFees)
class SchoolFeesAdmin(admin.ModelAdmin):
    list_display = ('student', 'title', 'amount_due', 'amount_paid', 'status', 'due_date')
    search_fields = ('student__first_name', 'student__last_name', 'title')

@admin.register(SchoolEvent)
class SchoolEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'event_date', 'location')
    search_fields = ('title', 'location')

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'document_type', 'uploaded_by', 'created_at')
    search_fields = ('title', 'uploaded_by__first_name', 'uploaded_by__last_name')

@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ('title', 'priority', 'posted_by', 'is_active', 'created_at')
    search_fields = ('title', 'posted_by__first_name', 'posted_by__last_name')

@admin.register(UserProfilePicture)
class UserProfilePictureAdmin(admin.ModelAdmin):
    list_display = ('user', 'uploaded_at')
    search_fields = ('user__first_name', 'user__last_name')

@admin.register(ClassTeacher)
class ClassTeacherAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'class_obj', 'is_form_tutor')
    search_fields = ('teacher__first_name', 'teacher__last_name', 'class_obj__name')

@admin.register(StudentClass)
class StudentClassAdmin(admin.ModelAdmin):
    list_display = ('student', 'class_obj', 'is_active')
    search_fields = ('student__first_name', 'student__last_name', 'class_obj__name')

@admin.register(ClassSubjectTeacher)
class ClassSubjectTeacherAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'subject', 'class_obj', 'is_active')
    search_fields = ('teacher__first_name', 'teacher__last_name', 'subject__name', 'class_obj__name')

@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ('subject', 'title', 'created_at')
    search_fields = ('subject__name', 'title')

@admin.register(SyllabusTopic)
class SyllabusTopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'syllabus', 'order', 'created_at')
    search_fields = ('title', 'syllabus__title')
