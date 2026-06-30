from django.contrib import admin
from apps.students.models import Grade, StudentGPA, StudentSocialClub, StudentSocialClubMember


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'assessment_type', 'score', 'grade', 'recorded_date')
    list_filter = ('assessment_type', 'subject', 'student__school')
    search_fields = ('student__first_name', 'student__last_name', 'subject__name')

@admin.register(StudentGPA)
class StudentGPAAdmin(admin.ModelAdmin):
    list_display = ('student', 'cgpa', 'current_gpa', 'total_credits', 'last_updated')
    search_fields = ('student__first_name', 'student__last_name')

@admin.register(StudentSocialClub)
class StudentSocialClubAdmin(admin.ModelAdmin):
    list_display = ('name', 'faculty_advisor', 'created_at')
    search_fields = ('name',)

@admin.register(StudentSocialClubMember)
class StudentSocialClubMemberAdmin(admin.ModelAdmin):
    list_display = ('club', 'student', 'role', 'status', 'joined_at')
    list_filter = ('club', 'role', 'status')
    search_fields = ('student__first_name', 'student__last_name', 'club__name')
