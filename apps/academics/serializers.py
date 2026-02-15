from rest_framework import serializers
from apps.academics.models import (
    Faculty, Department, Level, Subject, Class,
    ClassSubject, Enrollment, Timetable, AcademicCalendarEvent,
    Exam, ExamResult, SchoolFees, SchoolEvent, Document, DocumentFolder, Notice, UserProfilePicture,
    ClassTeacher, StudentClass, ClassSubjectTeacher
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
        fields = '__all__'


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
            teachers_data.append({
                'id': teacher.id,
                'name': teacher.get_full_name() or teacher.username,
                'email': teacher.email,
                'phone': teacher.phone or 'N/A',
                'is_form_tutor': ct.is_form_tutor,
                'gender': getattr(teacher, 'gender', 'N/A'),
            })
        return teachers_data
    
    def get_form_tutor(self, obj):
        """Get the form tutor (main class teacher)"""
        form_tutor = ClassTeacher.objects.filter(class_obj=obj, is_form_tutor=True).select_related('teacher').first()
        if form_tutor and form_tutor.teacher:
            teacher = form_tutor.teacher
            return {
                'id': teacher.id,
                'name': teacher.get_full_name() or teacher.username,
                'email': teacher.email,
                'phone': teacher.phone or 'N/A',
                'gender': getattr(teacher, 'gender', 'N/A'),
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
    
    class Meta:
        model = UserProfilePicture
        fields = ['id', 'user', 'user_name', 'picture', 'uploaded_at', 'updated_at']
    
    def get_user_name(self, obj):
        try:
            if obj.user:
                return obj.user.get_full_name() or obj.user.username
        except:
            pass
        return None


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