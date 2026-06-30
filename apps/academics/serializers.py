from rest_framework import serializers
from apps.academics.models import (
    Faculty, Department, Level, Subject, Class,
    ClassSubject, Enrollment, Timetable, AcademicCalendarEvent,
    Exam, ExamResult, SchoolFees, SchoolEvent, Document, DocumentFolder, Notice, UserProfilePicture,
    ClassTeacher, StudentClass, ClassSubjectTeacher, AcademicSession, TerminalReport, SubjectScore, GradingPolicy,
    TerminalReportTemplate, GradingScale, GradingScaleEntry, Assessment
)
from django.contrib.auth import get_user_model

User = get_user_model()


class FacultySerializer(serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = '__all__'


class DepartmentSerializer(serializers.ModelSerializer):
    faculty_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Department
        fields = '__all__'
    
    def get_faculty_name(self, obj):
        return obj.faculty.name if obj.faculty else None


class LevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = '__all__'


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'school', 'code', 'name', 'description', 'credit_hours', 'created_at', 'updated_at']
        extra_kwargs = {
            'school': {'required': False},
            'code': {'required': False},
        }
    
    def validate(self, data):
        # Skip validation if school is not provided
        # It will be set in perform_create
        return data


class ClassSerializer(serializers.ModelSerializer):
    level_name = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()
    level = serializers.PrimaryKeyRelatedField(queryset=Level.objects.all(), required=False, allow_null=True)
    teachers = serializers.SerializerMethodField()
    form_tutor = serializers.SerializerMethodField()
    
    class Meta:
        model = Class
        fields = '__all__'
    
    def get_level_name(self, obj):
        return obj.level.name if obj.level else None
    
    def get_student_count(self, obj):
        return obj.enrollments.filter(is_active=True).values('student').distinct().count()
    
    def get_teachers(self, obj):
        """Get all teachers assigned to this class with their details"""
        class_teachers = ClassTeacher.objects.filter(class_obj=obj).select_related('teacher')
        teachers_data = []
        for ct in class_teachers:
            teacher = ct.teacher
            # Get profile picture URL
            profile_pic_url = None
            try:
                profile_pic = UserProfilePicture.objects.filter(user=teacher).first()
                if profile_pic and profile_pic.display_url:
                    profile_pic_url = profile_pic.display_url
            except Exception:
                pass
            teachers_data.append({
                'id': teacher.id,
                'name': teacher.get_full_name() or teacher.username,
                'email': teacher.email,
                'phone': teacher.phone or 'N/A',
                'is_form_tutor': ct.is_form_tutor,
                'gender': getattr(teacher, 'gender', 'N/A'),
                'profile_picture': profile_pic_url,
            })
        return teachers_data
    
    def get_form_tutor(self, obj):
        """Get the form tutor (main class teacher)"""
        form_tutor = ClassTeacher.objects.filter(class_obj=obj, is_form_tutor=True).select_related('teacher').first()
        if form_tutor and form_tutor.teacher:
            teacher = form_tutor.teacher
            # Get profile picture URL
            profile_pic_url = None
            try:
                profile_pic = UserProfilePicture.objects.filter(user=teacher).first()
                if profile_pic and profile_pic.display_url:
                    profile_pic_url = profile_pic.display_url
            except Exception:
                pass
            return {
                'id': teacher.id,
                'name': teacher.get_full_name() or teacher.username,
                'email': teacher.email,
                'phone': teacher.phone or 'N/A',
                'gender': getattr(teacher, 'gender', 'N/A'),
                'profile_picture': profile_pic_url,
            }
        return None


class ClassSubjectSerializer(serializers.ModelSerializer):
    class_obj = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    
    subject_name = serializers.SerializerMethodField()
    subject_code = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ClassSubject
        fields = ['id', 'class_obj', 'subject', 'teacher', 'subject_name', 'subject_code', 'class_name', 'teacher_name', 'created_at']
    
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None
    
    def get_subject_code(self, obj):
        return obj.subject.code if obj.subject else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None
    
    def get_teacher_name(self, obj):
        if obj.teacher:
            return obj.teacher.get_full_name() or obj.teacher.username
        return None


class EnrollmentSerializer(serializers.ModelSerializer):
    class_obj = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all())
    student = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    
    student_name = serializers.SerializerMethodField()
    student_email = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = ['id', 'class_obj', 'student', 'subject', 'enrollment_date', 'is_active', 'student_name', 'student_email', 'class_name', 'subject_name']
    
    def get_student_name(self, obj):
        if obj.student:
            return obj.student.get_full_name() or obj.student.username
        return None
    
    def get_student_email(self, obj):
        return obj.student.email if obj.student else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None
    
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None


class TimetableSerializer(serializers.ModelSerializer):
    class_obj = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    teacher = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    
    subject_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Timetable
        fields = ['id', 'class_obj', 'subject', 'teacher', 'day', 'start_time', 'end_time', 'venue', 'subject_name', 'class_name', 'teacher_name', 'created_at', 'updated_at']
    
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None
    
    def get_teacher_name(self, obj):
        if obj.teacher:
            return obj.teacher.get_full_name() or obj.teacher.username
        return None


class AcademicCalendarEventSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AcademicCalendarEvent
        fields = '__all__'
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


class ExamSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    
    # Explicitly define fields with proper serializers for date/time handling
    exam_date = serializers.DateField()
    exam_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M", "%I:%M %p"])
    # School is handled by the view's perform_create, so make it read-only
    school = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Exam
        fields = ['id', 'school', 'subject', 'subject_name', 'class_obj', 'class_name', 'title', 'description', 'exam_date', 'exam_time', 'duration_minutes', 'venue', 'total_marks', 'created_by', 'teacher_name', 'created_at', 'updated_at']
    
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None
    
    def get_teacher_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None
    
    def validate_exam_time(self, value):
        """Ensure exam_time is a valid time object"""
        if value is None:
            raise serializers.ValidationError("Exam time is required")
        return value
    
    def validate_exam_date(self, value):
        """Ensure exam_date is a valid date object"""
        if value is None:
            raise serializers.ValidationError("Exam date is required")
        return value
    
    def to_internal_value(self, data):
        """Override to ensure proper conversion of string IDs to integers"""
        ret = super().to_internal_value(data)
        
        # Convert string IDs to integers
        for field_name in ['subject', 'class_obj']:
            if field_name in ret and ret[field_name]:
                if isinstance(ret[field_name], str):
                    try:
                        ret[field_name] = int(ret[field_name])
                    except (ValueError, TypeError):
                        pass
        
        return ret


class ExamResultSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    exam_title = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamResult
        fields = ['id', 'school', 'exam', 'exam_title', 'student', 'student_name', 'subject_name', 'marks_obtained', 'percentage', 'grade', 'remarks', 'recorded_by', 'recorded_date', 'updated_at']
    
    def get_student_name(self, obj):
        try:
            if obj.student:
                return obj.student.get_full_name() or obj.student.username
        except:
            pass
        return None
    
    def get_subject_name(self, obj):
        try:
            return obj.exam.subject.name if obj.exam and obj.exam.subject else None
        except:
            return None
    
    def get_exam_title(self, obj):
        try:
            return obj.exam.title if obj.exam else None
        except:
            return None


class SchoolFeesSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    amount_remaining = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    
    class Meta:
        model = SchoolFees
        fields = ['id', 'school', 'student', 'student_name', 'class_obj', 'class_name', 'title', 'amount_due', 'amount_paid', 'amount_remaining', 'due_date', 'status', 'description', 'created_at', 'updated_at']
    
    def get_student_name(self, obj):
        try:
            if obj.student:
                return obj.student.get_full_name() or obj.student.username
        except:
            pass
        return None
    
    def get_class_name(self, obj):
        try:
            return obj.class_obj.name if obj.class_obj else None
        except:
            return None
    
    def get_amount_remaining(self, obj):
        try:
            return float(obj.amount_due) - float(obj.amount_paid)
        except:
            return 0


class SchoolEventSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = SchoolEvent
        fields = ['id', 'school', 'title', 'description', 'event_date', 'event_time', 'location', 'image', 'created_by', 'created_by_name', 'created_at', 'updated_at']
    
    def get_created_by_name(self, obj):
        try:
            if obj.created_by:
                return obj.created_by.get_full_name() or obj.created_by.username
        except:
            pass
        return None


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Document
        fields = ['id', 'school', 'title', 'document_type', 'description', 'file', 'related_class', 'class_name', 'related_subject', 'subject_name', 'uploaded_by', 'uploaded_by_name', 'created_at', 'updated_at']
    
    def get_uploaded_by_name(self, obj):
        try:
            if obj.uploaded_by:
                return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        except:
            pass
        return None
    
    def get_subject_name(self, obj):
        try:
            return obj.related_subject.name if obj.related_subject else None
        except:
            return None
    
    def get_class_name(self, obj):
        try:
            return obj.related_class.name if obj.related_class else None
        except:
            return None


class DocumentFolderSerializer(serializers.ModelSerializer):
    """Serializer for document folders"""
    class Meta:
        model = DocumentFolder
        fields = ['id', 'school', 'teacher', 'name', 'description', 'parent_folder', 'created_at', 'updated_at']
        read_only_fields = ['school', 'teacher', 'created_at', 'updated_at']


class NoticeSerializer(serializers.ModelSerializer):
    posted_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Notice
        fields = ['id', 'school', 'title', 'content', 'priority', 'posted_by', 'posted_by_name', 'is_active', 'created_at', 'updated_at']
    
    def get_posted_by_name(self, obj):
        try:
            if obj.posted_by:
                return obj.posted_by.get_full_name() or obj.posted_by.username
        except:
            pass
        return None


class UserProfilePictureSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    display_url = serializers.SerializerMethodField()

    class Meta:
        model = UserProfilePicture
        fields = [
            'id', 'user', 'user_name', 
            'picture', 'storage_path', 'storage_url', 'display_url',
            'file_size', 'content_type', 'width', 'height',
            'uploaded_at', 'updated_at'
        ]
        read_only_fields = ['user', 'uploaded_at', 'updated_at']

    def get_user_name(self, obj):
        try:
            if obj.user:
                return obj.user.get_full_name() or obj.user.username
        except Exception:
            pass
        return None
    
    def get_display_url(self, obj):
        return obj.display_url


class ClassTeacherSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ClassTeacher
        fields = ['id', 'class_obj', 'class_name', 'teacher', 'teacher_name', 'teacher_email', 'is_form_tutor', 'created_at', 'updated_at']
    
    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.username if obj.teacher else None
    
    def get_teacher_email(self, obj):
        return obj.teacher.email if obj.teacher else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None


class StudentClassSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_email = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    
    class Meta:
        model = StudentClass
        fields = ['id', 'class_obj', 'class_name', 'student', 'student_name', 'student_email', 'assigned_date', 'is_active', 'created_at', 'updated_at']
    
    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username if obj.student else None
    
    def get_student_email(self, obj):
        return obj.student.email if obj.student else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None


class ClassSubjectTeacherSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    subject_code = serializers.SerializerMethodField()
    
    class Meta:
        model = ClassSubjectTeacher
        fields = ['id', 'class_obj', 'class_name', 'subject', 'subject_name', 'subject_code', 'teacher', 'teacher_name', 'teacher_email', 'assigned_date', 'is_active', 'created_at', 'updated_at']
    
    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.username if obj.teacher else None
    
    def get_teacher_email(self, obj):
        return obj.teacher.email if obj.teacher else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None
    
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None
    
    def get_subject_code(self, obj):
        return obj.subject.code if obj.subject else None


# ==================== GRADING SYSTEM - TERMINAL REPORTS SERIALIZERS ====================

class GradingPolicySerializer(serializers.ModelSerializer):
    assessment_type_display = serializers.CharField(source='get_assessment_type_display', read_only=True)
    session_name = serializers.CharField(source='academic_session.name', read_only=True)
    
    class Meta:
        model = GradingPolicy
        fields = ['id', 'school', 'academic_session', 'session_name', 'name', 'assessment_type', 'assessment_type_display', 'weightage', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['school', 'created_at', 'updated_at']


class AcademicSessionSerializer(serializers.ModelSerializer):
    school = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = AcademicSession
        fields = '__all__'


class SubjectScoreSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()
    subject_code = serializers.SerializerMethodField()
    
    class Meta:
        model = SubjectScore
        fields = ['id', 'subject', 'subject_name', 'subject_code', 'ca1_score', 'ca2_score', 'ca3_score', 'exam_score', 'total_score', 'percentage', 'grade', 'remarks', 'subject_position', 'subject_total_students']
    
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None
    
    def get_subject_code(self, obj):
        return obj.subject.code if obj.subject else None


class TerminalReportSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    session_name = serializers.SerializerMethodField()
    subject_scores = SubjectScoreSerializer(many=True, read_only=True)
    generated_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = TerminalReport
        fields = ['id', 'school', 'student', 'student_name', 'class_obj', 'class_name', 'academic_session', 'session_name', 'total_marks', 'average_marks', 'position', 'total_students', 'grade', 'total_days', 'days_present', 'attendance_percentage', 'form_teacher_remarks', 'principal_remarks', 'status', 'generated_by', 'generated_by_name', 'generated_at', 'subject_scores']
    
    def get_student_name(self, obj):
        return obj.student.get_full_name() if obj.student else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None
    
    def get_session_name(self, obj):
        return obj.academic_session.name if obj.academic_session else None
    
    def get_generated_by_name(self, obj):
        return obj.generated_by.get_full_name() if obj.generated_by else None


class TerminalReportListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing terminal reports"""
    student_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    session_name = serializers.SerializerMethodField()
    
    class Meta:
        model = TerminalReport
        fields = ['id', 'student', 'student_name', 'class_obj', 'class_name', 'academic_session', 'session_name', 'total_marks', 'average_marks', 'position', 'total_students', 'grade', 'status', 'generated_at']
    
    def get_student_name(self, obj):
        return obj.student.get_full_name() if obj.student else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None
    
    def get_session_name(self, obj):
        return obj.academic_session.name if obj.academic_session else None


class TerminalReportTemplateSerializer(serializers.ModelSerializer):
    """Serializer for terminal report templates"""
    school_name = serializers.SerializerMethodField()
    session_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = TerminalReportTemplate
        fields = [
            'id', 'school', 'school_name', 'academic_session', 'session_name', 'name', 'description',
'structure', 'html_template', 'is_active', 'is_default', 'preview_data', 'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['school', 'created_at', 'updated_at']
    
    def get_school_name(self, obj):
        return obj.school.name if obj.school else None
    
    def get_session_name(self, obj):
        return obj.academic_session.name if obj.academic_session else 'All Sessions'
    
    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


# ==================== GRADING SCALE SERIALIZERS ====================

class GradingScaleEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = GradingScaleEntry
        fields = ['id', 'grade_letter', 'min_percentage', 'max_percentage', 'points', 'is_passing', 'remark', 'promotion_eligible', 'order']


class GradingScaleSerializer(serializers.ModelSerializer):
    entries = GradingScaleEntrySerializer(many=True, read_only=True)
    school_name = serializers.SerializerMethodField()
    session_name = serializers.SerializerMethodField()
    
    class Meta:
        model = GradingScale
        fields = ['id', 'school', 'school_name', 'academic_session', 'session_name', 'name', 'entries', 'is_active', 'is_default', 'created_at', 'updated_at']
        read_only_fields = ['school', 'created_at', 'updated_at']

    def get_school_name(self, obj):
        return obj.school.name if obj.school else None
    
    def get_session_name(self, obj):
        return obj.academic_session.name if obj.academic_session else None


class GradingScaleWithEntriesSerializer(serializers.ModelSerializer):
    """Write serializer that handles nested entries"""
    entries = GradingScaleEntrySerializer(many=True)
    
    class Meta:
        model = GradingScale
        fields = ['id', 'school', 'academic_session', 'name', 'entries', 'is_active', 'is_default']
        read_only_fields = ['school']
    
    def create(self, validated_data):
        entries_data = validated_data.pop('entries', [])
        scale = GradingScale.objects.create(**validated_data)
        for i, entry_data in enumerate(entries_data):
            entry_data['order'] = entry_data.get('order', i)
            GradingScaleEntry.objects.create(grading_scale=scale, **entry_data)
        return scale
    
    def update(self, instance, validated_data):
        entries_data = validated_data.pop('entries', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if entries_data is not None:
            instance.entries.all().delete()
            for i, entry_data in enumerate(entries_data):
                entry_data['order'] = entry_data.get('order', i)
                GradingScaleEntry.objects.create(grading_scale=instance, **entry_data)
        
        return instance


# ==================== ASSESSMENT SERIALIZERS ====================

class AssessmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    session_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()
    term_label = serializers.SerializerMethodField()
    
    class Meta:
        model = Assessment
        fields = ['id', 'school', 'academic_session', 'session_name', 'subject', 'subject_name', 'class_obj', 'class_name', 'term', 'term_label', 'category', 'category_label', 'title', 'total_marks', 'assessment_date', 'weight_percentage', 'is_active', 'created_by', 'created_by_name', 'created_at', 'updated_at']
        read_only_fields = ['school', 'created_by', 'created_at', 'updated_at']
    
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None
    
    def get_class_name(self, obj):
        return obj.class_obj.name if obj.class_obj else None
    
    def get_session_name(self, obj):
        return obj.academic_session.name if obj.academic_session else None
    
    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None
    
    def get_category_label(self, obj):
        return obj.get_category_display()
    
    def get_term_label(self, obj):
        return obj.get_term_display()
