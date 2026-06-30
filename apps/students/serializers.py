from rest_framework import serializers
from apps.students.models import Grade, StudentGPA, StudentSocialClub, StudentSocialClubMember
from apps.users.models import StudentProfile
from apps.academics.models import Subject


class GradeSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    subject_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = Grade
        fields = '__all__'
        extra_kwargs = {
            'subject': {'required': False}
        }

    def to_internal_value(self, data):
        """
        Normalize subject payloads before field validation.
        Supports:
        - subject_id: 12
        - subject: 12
        - subject: {"id": 12}
        """
        if isinstance(data, dict):
            mutable = data.copy()

            subject_value = mutable.get('subject', None)
            subject_id_value = mutable.get('subject_id', None)

            normalized_subject_id = None

            if subject_id_value not in (None, ''):
                normalized_subject_id = subject_id_value
            elif isinstance(subject_value, dict):
                normalized_subject_id = subject_value.get('id')
            elif subject_value not in (None, ''):
                normalized_subject_id = subject_value

            if normalized_subject_id is not None:
                mutable['subject_id'] = normalized_subject_id
                if 'subject' in mutable:
                    del mutable['subject']

            data = mutable

        return super().to_internal_value(data)

    def validate_subject_id(self, value):
        """
        Validate subject existence within the user's school boundary.
        Teacher-class assignment is enforced centrally in validate().
        """
        if value in (None, ''):
            return value

        request = self.context.get('request')
        user = getattr(request, 'user', None)

        subject_qs = Subject.objects.filter(pk=value)
        if user and hasattr(user, 'school'):
            subject_qs = subject_qs.filter(school=user.school)

        subject_obj = subject_qs.first()
        if not subject_obj:
            raise serializers.ValidationError(
                f'Invalid pk "{value}" - object does not exist.'
            )

        self.context['validated_subject'] = subject_obj
        return value

    def create(self, validated_data):
        subject_id = validated_data.pop('subject_id', None)

        if subject_id is not None:
            validated_data['subject_id'] = subject_id

        return super().create(validated_data)

    def validate(self, attrs):
        """
        Cross-check teacher assignment for the specific student's class and selected subject.
        """
        if not self.instance and 'subject_id' not in attrs:
            raise serializers.ValidationError({'subject_id': 'This field is required.'})

        request = self.context.get('request')
        if not request or not request.user or request.user.is_anonymous:
            return attrs

        user = request.user
        if user.role != 'teacher':
            return attrs

        student = attrs.get('student') or getattr(self.instance, 'student', None)
        subject = attrs.get('subject') or self.context.get('validated_subject') or getattr(self.instance, 'subject', None)

        if not student or not subject:
            return attrs

        from apps.academics.models import StudentClass, ClassSubjectTeacher, ClassTeacher, ClassSubject
        import logging
        logger = logging.getLogger(__name__)

        student_class_ids = list(StudentClass.objects.filter(
            student=student,
            is_active=True
        ).values_list('class_obj_id', flat=True))
        
        logger.info(f"Validating grade for teacher={user.id} ({user.get_full_name()}), "
                   f"student={student.id} ({student.get_full_name()}), "
                   f"subject={subject.id} ({subject.name}), "
                   f"student_classes={[cid for cid in student_class_ids]}")

        # Check direct subject assignment
        teacher_assigned = ClassSubjectTeacher.objects.filter(
            teacher=user,
            subject=subject,
            class_obj_id__in=student_class_ids,
            is_active=True
        ).exists()

        if teacher_assigned:
            logger.info("✓ Teacher directly assigned to subject in student's class")
            return attrs

        # Fallback: Check if teacher is form tutor AND subject exists in class
        form_tutor = ClassTeacher.objects.filter(
            teacher=user,
            class_obj_id__in=student_class_ids,
            is_form_tutor=True
        ).exists()
        
        subject_in_class = False
        if form_tutor:
            # Verify subject is assigned to one of student's classes
            subject_in_class = ClassSubject.objects.filter(
                class_obj_id__in=student_class_ids,
                subject=subject
            ).exists()
            
            if subject_in_class:
                logger.info("✓ Teacher is form tutor + subject assigned to class ✓")
                return attrs
            else:
                logger.info(f"✗ Form tutor OK but subject '{subject.name}' not assigned to any student class")

        # Detailed error
        logger.warning(f"✗ Teacher NOT assigned: No ClassSubjectTeacher or ClassTeacher match")
        
        active_classes = StudentClass.objects.filter(
            student=student, is_active=True
        ).select_related('class_obj').values_list('class_obj__name', flat=True)
        
        teacher_assignments = ClassSubjectTeacher.objects.filter(
            teacher=user, is_active=True
        ).select_related('class_obj', 'subject').values_list(
            'class_obj__name', 'subject__name'
        )
        
        error_detail = (
            f"You are not assigned to '{subject.name}' for student '{student.get_full_name()}' "
            f"(active classes: {list(active_classes)}). "
            f"Your assignments: {list(teacher_assignments)}. "
            f"Contact admin to add ClassSubjectTeacher record."
        )
        raise serializers.ValidationError({'subject_id': error_detail})

        return attrs


class StudentGPASerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    
    class Meta:
        model = StudentGPA
        fields = '__all__'


class StudentPortalSerializer(serializers.Serializer):
    profile = serializers.SerializerMethodField()
    profile_picture_url = serializers.SerializerMethodField()
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
    
    def get_profile_picture_url(self, obj):
        """Get profile picture URL from UserProfilePicture"""
        try:
            if hasattr(obj, 'profile_picture') and obj.profile_picture:
                return obj.profile_picture.display_url
        except Exception:
            pass
        # Also check in student_profile
        if hasattr(obj, 'student_profile') and obj.student_profile:
            return getattr(obj.student_profile, 'profile_picture_url', None)
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
