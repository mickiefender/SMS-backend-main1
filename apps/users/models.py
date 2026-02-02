from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from apps.schools.models import School


class User(AbstractUser):
    ROLE_CHOICES = (
        ('super_admin', 'Super Admin'),
        ('school_admin', 'School Admin'),
        ('academic_admin', 'Academic Admin'),
        ('exam_officer', 'Exam Officer'),
        ('finance_officer', 'Finance Officer'),
        ('ct_admin_support', 'CT/Admin Support'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
        ('parent', 'Parent'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True, related_name='users')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    phone = models.CharField(max_length=20, blank=True)
    is_active_user = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'role']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} - {self.role}"


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    employee_id = models.CharField(max_length=50, unique=True)
    qualification = models.CharField(max_length=255, blank=True)
    experience_years = models.IntegerField(default=0)
    department = models.ForeignKey('academics.Department', on_delete=models.SET_NULL, null=True, blank=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Teacher Profiles"
    
    def __str__(self):
        return f"{self.user.get_full_name()} - Teacher"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    student_id = models.CharField(max_length=50, unique=True, blank=True)
    level = models.ForeignKey('academics.Level', on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey('academics.Department', on_delete=models.SET_NULL, null=True, blank=True)
    enrollment_date = models.DateField(auto_now_add=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Student Profiles"
    
    def save(self, *args, **kwargs):
        if not self.student_id and self.user.school:
            with transaction.atomic():
                # Lock the school to prevent race conditions
                try:
                    school = School.objects.select_for_update().get(pk=self.user.school.pk)
                except School.DoesNotExist:
                    # Handle case where school is not found, though this is unlikely
                    super().save(*args, **kwargs)
                    return

                from datetime import datetime
                
                # Get school initials
                school_name = self.user.school.name
                words = school_name.split()
                school_initials = ''.join([word[0].upper() for word in words if word])[:3]
                
                year = datetime.now().year
                
                # Get the latest student to determine the next ID
                last_student = StudentProfile.objects.filter(
                    user__school=self.user.school,
                    student_id__startswith=f"{school_initials}{year}"
                ).order_by('student_id').last()

                if last_student and last_student.student_id:
                    # Extract the numeric part and increment
                    try:
                        last_count = int(last_student.student_id[-5:])
                        new_count = last_count + 1
                    except (ValueError, IndexError):
                        # Fallback if the ID format is unexpected
                        new_count = StudentProfile.objects.filter(user__school=self.user.school, created_at__year=year).count() + 1
                else:
                    # No student found for this year, start from 1
                    new_count = 1
                
                self.student_id = f"{school_initials}{year}{new_count:05d}"
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - Student ({self.student_id})"


class RolePermission(models.Model):
    """
    Define permissions for each admin role.
    School admin can grant/revoke these permissions to staff members.
    """
    PERMISSION_CHOICES = (
        ('manage_students', 'Manage Students'),
        ('manage_teachers', 'Manage Teachers'),
        ('manage_classes', 'Manage Classes'),
        ('manage_subjects', 'Manage Subjects'),
        ('manage_attendance', 'Manage Attendance'),
        ('manage_grades', 'Manage Grades'),
        ('manage_exams', 'Manage Exams'),
        ('view_exams', 'View Exams'),
        ('manage_fees', 'Manage Fees'),
        ('view_fees', 'View Fees'),
        ('manage_assignments', 'Manage Assignments'),
        ('view_reports', 'View Reports'),
        ('manage_timetable', 'Manage Timetable'),
        ('manage_materials', 'Manage Materials'),
        ('send_messages', 'Send Messages'),
        ('manage_notices', 'Manage Notices'),
        ('manage_events', 'Manage Events'),
        ('manage_admins', 'Manage Admin Accounts'),
        ('view_analytics', 'View Analytics'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='role_permission')
    permission = models.JSONField(default=list, help_text="List of permissions granted to this user")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Role Permissions"
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.user.role}"
    
    def has_permission(self, permission_code):
        """Check if user has a specific permission"""
        return permission_code in self.permission
    
    def add_permission(self, permission_code):
        """Add a permission to the user"""
        if permission_code not in self.permission:
            self.permission.append(permission_code)
            self.save()
    
    def remove_permission(self, permission_code):
        """Remove a permission from the user"""
        if permission_code in self.permission:
            self.permission.remove(permission_code)
            self.save()
