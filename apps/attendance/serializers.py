from rest_framework import serializers
from apps.attendance.models import Attendance
from apps.academics.models import Class, Subject
from apps.users.models import User


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    class_name = serializers.CharField(source='class_obj.name', read_only=True)
    
    class_obj = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    student = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='student'))
    teacher = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='teacher'), required=False, allow_null=True)
    
    class Meta:
        model = Attendance
        fields = ['id', 'class_obj', 'class_name', 'subject', 'subject_name', 'student', 'student_name', 'teacher', 'teacher_name', 'status', 'date', 'remark', 'created_at', 'updated_at']
