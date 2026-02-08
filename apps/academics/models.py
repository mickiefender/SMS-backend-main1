from django.db import models
from apps.schools.models import School


class Faculty(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='faculties')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['school', 'name']
        verbose_name_plural = "Faculties"
    
    def __str__(self):
        return f"{self.school.name} - {self.name}"


class Department(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['faculty', 'name']
    
    def __str__(self):
        return f"{self.faculty.name} - {self.name}"


class Level(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='levels')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['school', 'name']
        ordering = ['order']
    
    def __str__(self):
        return f"{self.school.name} - {self.name}"


class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='subjects')
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    credit_hours = models.IntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['school', 'code']
    
    def save(self, *args, **kwargs):
        if not self.code:
            # Get school initials
            school_name = self.school.name if self.school else "SUB"
            words = school_name.split()
            school_initials = ''.join([word[0].upper() for word in words if word])[:3]
            
            # Get first 3 letters of subject name in uppercase
            subject_abbr = self.name[:3].upper() if self.name else "UNK"
            
            # Get the count of subjects in this school
            count = Subject.objects.filter(school=self.school).count() + 1
            
            self.code = f"{school_initials}{subject_abbr}{count:03d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Class(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='classes')
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    name = models.CharField(max_length=100)
    level = models.ForeignKey(Level, on_delete=models.SET_NULL, null=True)
    capacity = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['school', 'name', 'level']
        verbose_name_plural = "Classes"
    
    def save(self, *args, **kwargs):
        if not self.code:
            # Get school initials
            school_name = self.school.name if self.school else "CLS"
            words = school_name.split()
            school_initials = ''.join([word[0].upper() for word in words if word])[:3]
            
            # Get the count of classes in this school
            count = Class.objects.filter(school=self.school).count() + 1
            
            self.code = f"{school_initials}-{count:03d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.school.name} - {self.name}"


class ClassSubject(models.Model):
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'teacher'})
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['class_obj', 'subject']
    
    def __str__(self):
        return f"{self.class_obj.name} - {self.subject.code}"


class Enrollment(models.Model):
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='enrollments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    enrollment_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_current = models.BooleanField(default=True)
    status = models.CharField(max_length=20, default='active', choices=[('active', 'Active'), ('inactive', 'Inactive'), ('completed', 'Completed')])
    remarks = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['class_obj', 'student', 'subject']
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.class_obj.name}"


class ClassTeacher(models.Model):
    """Track which teacher(s) manage which class"""
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='teachers')
    teacher = models.ForeignKey('users.User', on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'}, related_name='managed_classes')
    is_form_tutor = models.BooleanField(default=False)  # Main class teacher
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['class_obj', 'teacher']
    
    def __str__(self):
        return f"{self.teacher.get_full_name()} - {self.class_obj.name} {'(Form Tutor)' if self.is_form_tutor else ''}"


class StudentClass(models.Model):
    """Direct tracking of student-class assignments"""
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='student_enrollments')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='class_assignments')
    assigned_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['class_obj', 'student']
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.class_obj.name}"


class ClassSubjectTeacher(models.Model):
    """Track which teacher teaches which subject in which class"""
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='subject_teachers')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='class_assignments')
    teacher = models.ForeignKey('users.User', on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'}, related_name='subject_assignments')
    assigned_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['class_obj', 'subject', 'teacher']
    
    def __str__(self):
        return f"{self.teacher.get_full_name()} - {self.subject.code} in {self.class_obj.name}"


class Timetable(models.Model):
    DAY_CHOICES = (
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    )
    
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='timetables')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'teacher'})
    day = models.CharField(max_length=10, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    venue = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['class_obj', 'subject', 'day', 'start_time']
        verbose_name_plural = "Timetables"
    
    def __str__(self):
        return f"{self.class_obj.name} - {self.subject.code} - {self.day}"

class AcademicCalendarEvent(models.Model):
    EVENT_TYPE_CHOICES = (
        ('holiday', 'Holiday'),
        ('exam', 'Exam'),
        ('event', 'Event'),
        ('break', 'Break'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='calendar_events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['school', 'title', 'start_date']
        ordering = ['start_date']
    
    def __str__(self):
        return f"{self.school.name} - {self.title}"


class Exam(models.Model):
    """Upcoming exams for students"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='exams')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exams')
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='exams')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    exam_date = models.DateField()
    exam_time = models.TimeField()
    duration_minutes = models.IntegerField(default=60)
    venue = models.CharField(max_length=255, blank=True)
    total_marks = models.IntegerField(default=100)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'teacher'})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['school', 'subject', 'class_obj', 'exam_date']
        ordering = ['exam_date']
    
    def __str__(self):
        return f"{self.subject.name} - {self.exam_date}"


class ExamResult(models.Model):
    """Student exam results"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='exam_results')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='results')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='exam_results')
    marks_obtained = models.FloatField()
    percentage = models.FloatField(default=0, editable=False)
    grade = models.CharField(max_length=5, blank=True)
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='recorded_exam_results', limit_choices_to={'role': 'teacher'})
    recorded_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['exam', 'student']
        ordering = ['-recorded_date']
    
    def save(self, *args, **kwargs):
        if self.exam.total_marks > 0:
            self.percentage = (self.marks_obtained / self.exam.total_marks) * 100
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
        return f"{self.student.get_full_name()} - {self.exam.subject.name}"


class SchoolFees(models.Model):
    """Student school fees - linked to fee types"""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='fees')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='school_fees')
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='fees')
    title = models.CharField(max_length=255)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.title}"


class SchoolEvent(models.Model):
    """School events/activities"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='school_events')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_date = models.DateField()
    event_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to='events/', null=True, blank=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-event_date']
    
    def __str__(self):
        return f"{self.title} - {self.event_date}"


class DocumentFolder(models.Model):
    """Folders for organizing learning materials"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='document_folders')
    teacher = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='document_folders')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    parent_folder = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subfolders')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['teacher', 'name', 'parent_folder']
    
    def __str__(self):
        return f"{self.name} ({self.teacher.get_full_name()})"


class Document(models.Model):
    """School documents for students/teachers"""
    DOCUMENT_TYPE_CHOICES = (
        ('certificate', 'Certificate'),
        ('transcript', 'Transcript'),
        ('syllabus', 'Syllabus'),
        ('assignment', 'Assignment'),
        ('notes', 'Notes'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='documents')
    folder = models.ForeignKey(DocumentFolder, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='documents/')
    related_class = models.ForeignKey(Class, on_delete=models.SET_NULL, null=True, blank=True)
    related_subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    shared_with_classes = models.ManyToManyField(Class, blank=True, related_name='shared_documents')
    is_shared = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title}"


class Notice(models.Model):
    """Notice board for school announcements"""
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='+')
    title = models.CharField(max_length=255)
    content = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    posted_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.school.name} - {self.title}"


class UserProfilePicture(models.Model):
    """Profile pictures for students and teachers"""
    user = models.OneToOneField('users.User', on_delete=models.CASCADE, related_name='profile_picture')
    picture = models.ImageField(upload_to='profile_pictures/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "User Profile Pictures"
    
    def __str__(self):
        return f"{self.user.get_full_name()} - Profile Picture"


class Syllabus(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='syllabi')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='syllabi')
    class_obj = models.ForeignKey(Class, on_delete=models.SET_NULL, null=True, blank=True, related_name='syllabi')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='syllabi/', null=True, blank=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Syllabi"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.subject.name} - {self.title}"


class SyllabusTopic(models.Model):
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name='topics')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.syllabus.subject.name} - {self.title}"


# ==================== NEW FEE MANAGEMENT SYSTEM ====================

class FeeType(models.Model):
    """Define types of fees (School Fees, PTA, Transport, etc.)"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='+')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['school', 'name']
        ordering = ['name']
        indexes = [
            models.Index(fields=['school', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.school.name} - {self.name}"


class StudentFeeAssignment(models.Model):
    """Bulk assignment of fees to entire classes"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='fee_assignments')
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name='class_assignments')
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='fee_assignments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    description = models.TextField(blank=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'admin'})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['fee_type', 'class_obj']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['class_obj', 'due_date']),
        ]
    
    def __str__(self):
        return f"{self.fee_type.name} - {self.class_obj.name}"


class StudentIndividualFee(models.Model):
    """Individual fee assignment to specific students"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='individual_fees')
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name='individual_assignments')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='individual_fees')
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='individual_student_fees')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('partial', 'Partial'), ('paid', 'Paid'), ('overdue', 'Overdue')], default='pending')
    description = models.TextField(blank=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='assigned_individual_fees', limit_choices_to={'role': 'admin'})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['fee_type', 'student', 'class_obj']
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.fee_type.name}"


class FeePayment(models.Model):
    """Track fee payments from students"""
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('credit_card', 'Credit Card'),
        ('check', 'Check'),
        ('mobile_money', 'Mobile Money'),
        ('other', 'Other'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='fee_payments')
    individual_fee = models.ForeignKey(StudentIndividualFee, on_delete=models.CASCADE, related_name='payments')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    transaction_id = models.CharField(max_length=100, blank=True)
    receipt_number = models.CharField(max_length=100, unique=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'admin'})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['individual_fee', 'payment_date']),
        ]
    
    def __str__(self):
        return f"Payment: {self.individual_fee.student.get_full_name()} - {self.amount_paid}"


class FeeWaiver(models.Model):
    """Manage fee waivers for students"""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='fee_waivers')
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='fee_waivers')
    individual_fee = models.ForeignKey(StudentIndividualFee, on_delete=models.CASCADE, related_name='waivers')
    reason = models.TextField()
    waiver_percentage = models.IntegerField(default=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_waivers', limit_choices_to={'role': 'admin'})
    approval_date = models.DateField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'status']),
        ]
    
    def __str__(self):
        return f"Waiver: {self.student.get_full_name()} - {self.waiver_percentage}%"
