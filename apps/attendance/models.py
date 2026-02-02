from django.db import models
from django.contrib.auth import get_user_model
from apps.academics.models import Class, Subject

User = get_user_model()


class Attendance(models.Model):
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    )
    
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='attendances')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='attendances')
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'teacher'})
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    date = models.DateField()
    remark = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['class_obj', 'student', 'subject', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.status} - {self.date}"
