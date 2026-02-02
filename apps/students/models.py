from django.db import models
from django.contrib.auth import get_user_model
from apps.academics.models import Subject

User = get_user_model()


class Grade(models.Model):
    ASSESSMENT_TYPE_CHOICES = (
        ('exam', 'Exam'),
        ('test', 'Test'),
        ('quiz', 'Quiz'),
        ('continuous', 'Continuous Assessment'),
        ('assignment', 'Assignment'),
    )
    
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='grades')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    assessment_type = models.CharField(max_length=20, choices=ASSESSMENT_TYPE_CHOICES)
    score = models.FloatField()
    max_score = models.FloatField(default=100)
    percentage = models.FloatField(editable=False)
    grade = models.CharField(max_length=5, blank=True)
    recorded_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-recorded_date']
    
    def save(self, *args, **kwargs):
        self.percentage = (self.score / self.max_score * 100) if self.max_score > 0 else 0
        self.grade = self.calculate_grade()
        super().save(*args, **kwargs)
    
    def calculate_grade(self):
        if self.percentage >= 90:
            return 'A'
        elif self.percentage >= 80:
            return 'B'
        elif self.percentage >= 70:
            return 'C'
        elif self.percentage >= 60:
            return 'D'
        else:
            return 'F'
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.subject.name} - {self.grade}"


class StudentGPA(models.Model):
    student = models.OneToOneField(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='gpa')
    cgpa = models.FloatField(default=0.0)
    current_gpa = models.FloatField(default=0.0)
    total_credits = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Student GPAs"
    
    def __str__(self):
        return f"{self.student.get_full_name()} - GPA: {self.cgpa}"
    
    def calculate_gpa(self):
        """Calculate GPA based on grades"""
        from apps.academics.models import Enrollment
        
        enrollments = Enrollment.objects.filter(student=self.student, is_active=True)
        total_points = 0
        total_credits = 0
        
        for enrollment in enrollments:
            grades = Grade.objects.filter(student=self.student, subject=enrollment.subject).aggregate(avg=models.Avg('percentage'))
            avg_percentage = grades['avg'] or 0
            
            # Convert percentage to GPA (4.0 scale)
            gpa_point = (avg_percentage / 100) * 4.0
            total_points += gpa_point * enrollment.subject.credit_hours
            total_credits += enrollment.subject.credit_hours
        
        if total_credits > 0:
            self.current_gpa = total_points / total_credits
            if self.cgpa == 0:
                self.cgpa = self.current_gpa
            else:
                self.cgpa = (self.cgpa + self.current_gpa) / 2
        
        self.total_credits = total_credits
        self.save()


class StudentSocialClub(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    faculty_advisor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role__in': ['teacher', 'school_admin']})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class StudentSocialClubMember(models.Model):
    ROLE_CHOICES = (
        ('member', 'Member'),
        ('president', 'President'),
        ('vice_president', 'Vice President'),
        ('secretary', 'Secretary'),
        ('treasurer', 'Treasurer'),
    )

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('pending', 'Pending'),
    )

    club = models.ForeignKey(StudentSocialClub, on_delete=models.CASCADE, related_name='members')
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('club', 'student')

    def __str__(self):
        return f"{self.student.get_full_name()} - {self.club.name} ({self.get_role_display()})"
