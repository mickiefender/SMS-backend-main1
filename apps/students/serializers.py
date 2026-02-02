from rest_framework import serializers
from apps.students.models import Grade, StudentGPA, StudentSocialClub, StudentSocialClubMember
from apps.users.models import StudentProfile


class GradeSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    
    class Meta:
        model = Grade
        fields = '__all__'


class StudentGPASerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    
    class Meta:
        model = StudentGPA
        fields = '__all__'


class StudentPortalSerializer(serializers.Serializer):
    profile = serializers.SerializerMethodField()
    enrollments = serializers.SerializerMethodField()
    grades = serializers.SerializerMethodField()
    gpa = serializers.SerializerMethodField()
    
    def get_profile(self, obj):
        if hasattr(obj, 'student_profile'):
            return {
                'student_id': obj.student_profile.student_id,
                'level': obj.student_profile.level.name if obj.student_profile.level else None,
                'department': obj.student_profile.department.name if obj.student_profile.department else None,
                'enrollment_date': obj.student_profile.enrollment_date,
            }
        return None
    
    def get_enrollments(self, obj):
        from apps.academics.models import Enrollment
        enrollments = Enrollment.objects.filter(student=obj, is_active=True)
        return [{
            'class': e.class_obj.name,
            'subject': e.subject.name,
            'subject_code': e.subject.code,
        } for e in enrollments]
    
    def get_grades(self, obj):
        grades = Grade.objects.filter(student=obj)
        return GradeSerializer(grades, many=True).data
    
    def get_gpa(self, obj):
        if hasattr(obj, 'gpa'):
            return StudentGPASerializer(obj.gpa).data
        return None


class StudentSocialClubSerializer(serializers.ModelSerializer):
    members_count = serializers.SerializerMethodField()

    class Meta:
        model = StudentSocialClub
        fields = '__all__'

    def get_members_count(self, obj):
        return obj.members.count()


class StudentSocialClubMemberSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    club_name = serializers.CharField(source='club.name', read_only=True)

    class Meta:
        model = StudentSocialClubMember
        fields = '__all__'
