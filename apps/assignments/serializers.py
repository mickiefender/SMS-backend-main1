from rest_framework import serializers
from apps.assignments.models import Assignment, AssignmentSubmission
from apps.users.models import User
from apps.academics.models import Class, Subject


class AssignmentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    class_name = serializers.CharField(source='class_obj.name', read_only=True)
    submission = serializers.SerializerMethodField(read_only=True)
    submission_count = serializers.SerializerMethodField(read_only=True)
    graded_count = serializers.SerializerMethodField(read_only=True)
    
    class_obj = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    teacher = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='teacher'), required=False)
    file = serializers.FileField(required=False)
    
    class Meta:
        model = Assignment
        fields = ['id', 'class_obj', 'subject', 'teacher', 'teacher_name', 'subject_name', 'class_name', 'title', 'description', 'file', 'due_date', 'created_at', 'updated_at', 'submission', 'submission_count', 'graded_count']
        read_only_fields = ['teacher_name', 'subject_name', 'class_name', 'created_at', 'updated_at', 'submission', 'submission_count', 'graded_count']
    
    def get_submission_count(self, obj):
        return obj.submissions.count()
    
    def get_graded_count(self, obj):
        return obj.submissions.filter(status='graded').count()
    
    def get_submission(self, obj):
        user = self.context.get('user')
        if not user or user.role != 'student':
            return None
        try:
            submission = AssignmentSubmission.objects.get(
                assignment=obj,
                student=user
            )
            # Lightweight dict for frontend compatibility (matches expected shape)
            return {
                'status': submission.status,
                'score': submission.score,
                'feedback': submission.feedback,
                'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at else None
            }
        except AssignmentSubmission.DoesNotExist:
            return None


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    
    class Meta:
        model = AssignmentSubmission
        fields = '__all__'
        read_only_fields = ['student']
    
    def to_internal_value(self, data):
        print(f"[DEBUG] AssignmentSubmissionSerializer - Raw data keys: {list(data.keys())}")
        print(f"[DEBUG] AssignmentSubmissionSerializer - Data types: { {k: type(v).__name__ if v is not None else None for k,v in data.items()} }")
        internal_data = super().to_internal_value(data)
        print(f"[DEBUG] After validation internal_data: {internal_data}")
        return internal_data
        
    def validate(self, data):
        print(f"[DEBUG] validate() called with data: {data}")
        if not data.get('file') and not data.get('text_submission'):
            raise serializers.ValidationError({"detail": "Must have either a file or text submission."})
        
        if data.get('file') and data.get('text_submission'):
            raise serializers.ValidationError({"detail": "Cannot have both file and text submission."})
        return data
