from rest_framework import serializers
from apps.assignments.models import Assignment, AssignmentSubmission
from apps.users.models import User
from apps.academics.models import Class, Subject


class AssignmentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    class_name = serializers.CharField(source='class_obj.name', read_only=True)
    
    class_obj = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    teacher = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='teacher'), required=False)
    file = serializers.FileField(required=False)
    
    class Meta:
        model = Assignment
        fields = ['id', 'class_obj', 'subject', 'teacher', 'teacher_name', 'subject_name', 'class_name', 'title', 'description', 'file', 'due_date', 'created_at', 'updated_at']
        read_only_fields = ['teacher_name', 'subject_name', 'class_name', 'created_at', 'updated_at']


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    
    class Meta:
        model = AssignmentSubmission
        fields = '__all__'
        read_only_fields = ['student']
        
    def validate(self, data):
        if not data.get('file') and not data.get('text_submission'):
            raise serializers.ValidationError("Must have either a file or text submission.")
        
        if data.get('file') and data.get('text_submission'):
            raise serializers.ValidationError("Cannot have both file and text submission.")
            
        return data
