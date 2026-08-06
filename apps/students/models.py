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
        ('class_exercise', 'Class Exercise'),
        ('project', 'Project'),
    )
    
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='grades')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    assessment_type = models.CharField(max_length=20, choices=ASSESSMENT_TYPE_CHOICES)
    # Link to the specific Assessment this grade belongs to (school-configured type + date + total marks)
    assessment = models.ForeignKey(
        'academics.Assessment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grades',
        help_text='The specific assessment (type + date + total marks) this score belongs to.',
    )
    academic_session = models.ForeignKey('academics.AcademicSession', on_delete=models.CASCADE, related_name='grades', null=True, blank=True)
    score = models.FloatField()
    max_score = models.FloatField(default=100)
    percentage = models.FloatField(editable=False)
    grade = models.CharField(max_length=5, blank=True)
    is_locked = models.BooleanField(default=False)  # When true, grade cannot be edited
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_grades')
    locked_at = models.DateTimeField(null=True, blank=True)
    recorded_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-recorded_date']
        indexes = [
            models.Index(fields=['assessment', 'student']),
        ]
    
    def save(self, *args, **kwargs):
        # Calculate raw percentage from score
        raw_percentage = (self.score / self.max_score * 100) if self.max_score > 0 else 0
        self.percentage = raw_percentage
        
        # Apply the assessment's configured weight contribution (e.g. Assignment = 10%)
        if self.assessment_id:
            from apps.academics.models import Assessment
            assessment = Assessment.objects.filter(pk=self.assessment_id).first()
            if assessment is not None and assessment.weight_percentage > 0:
                # Contribution = % score * weight. E.g. 80% on a 10% assignment = 8 points.
                self.percentage = raw_percentage * (assessment.weight_percentage / 100)
            elif assessment is not None and assessment.assessment_type_id:
                atype = assessment.assessment_type
                if atype and atype.weight_percentage > 0:
                    self.percentage = raw_percentage * (atype.weight_percentage / 100)
        else:
            # Fallback: legacy grading policy weighting
            if self.academic_session_id:
                from apps.academics.models import GradingPolicy
                policy = GradingPolicy.objects.filter(
                    academic_session=self.academic_session,
                    assessment_type=self.assessment_type,
                    is_active=True
                ).first()
                
                if policy and policy.weightage > 0:
                    self.percentage = raw_percentage * (policy.weightage / 100)
        
        # Calculate the grade letter based on percentage
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
