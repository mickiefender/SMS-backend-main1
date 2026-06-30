from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from core.permissions import IsSchoolAdminOrHigher, IsSchoolAdminOrTeacher, IsSchoolAdminOrSelf
from apps.academics.models import (
    Faculty, Department, Level, Subject, Class,
    ClassSubject, Enrollment, Timetable, AcademicCalendarEvent,
    Exam, ExamResult, SchoolFees, SchoolEvent, Document, DocumentFolder, Notice, UserProfilePicture,
    ClassTeacher, StudentClass, ClassSubjectTeacher, AcademicSession, TerminalReport, SubjectScore, GradingPolicy,
    TerminalReportTemplate, GradingScale, GradingScaleEntry, Assessment
)
from apps.academics.serializers import (
    FacultySerializer, DepartmentSerializer, LevelSerializer,
    SubjectSerializer, ClassSerializer, ClassSubjectSerializer,
    EnrollmentSerializer, TimetableSerializer, AcademicCalendarEventSerializer,
    ExamSerializer, ExamResultSerializer, SchoolFeesSerializer,
    SchoolEventSerializer, DocumentSerializer, DocumentFolderSerializer, NoticeSerializer, UserProfilePictureSerializer,
    ClassTeacherSerializer, StudentClassSerializer, ClassSubjectTeacherSerializer,
    AcademicSessionSerializer,
    TerminalReportListSerializer, GradingPolicySerializer,
    TerminalReportTemplateSerializer, GradingScaleSerializer, GradingScaleWithEntriesSerializer,
    AssessmentSerializer, GradingScaleEntrySerializer
)

class GenerateTerminalReportSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    class_id = serializers.IntegerField()
    session_id = serializers.IntegerField()
    template_id = serializers.IntegerField(required=False, allow_null=True)
    
    def validate_student_id(self, value):
        from apps.users.models import User
        if not User.objects.filter(id=value, role='student').exists():
            raise serializers.ValidationError("Student not found")
        return value
    
    def validate_class_id(self, value):
        from apps.academics.models import Class
        if not Class.objects.filter(id=value).exists():
            raise serializers.ValidationError("Class not found")
        return value
    
    def validate_session_id(self, value):
        from apps.academics.models import AcademicSession
        if not AcademicSession.objects.filter(id=value).exists():
            raise serializers.ValidationError("Session not found")
        return value


import os
import fitz  # PyMuPDF for PDF extraction
try:
    from docx import Document
except ImportError:
    Document = None

from .utils import calculate_student_report_data, render_template_html




def get_school_filter(user):
    """Get school for filtering, returns None for super_admin or if no school assigned"""
    try:
        if user.role == 'super_admin':
            return None
        # Check if school_id exists and is not None
        if hasattr(user, 'school_id') and user.school_id:
            return user.school_id
        return None
    except Exception as e:
        print(f"[v0] Error in get_school_filter: {e}")
        return None


class FacultyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing faculties"""
    serializer_class = FacultySerializer
    queryset = Faculty.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()


class DepartmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing departments"""
    serializer_class = DepartmentSerializer
    queryset = Department.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(faculty__school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            # Departments need faculty first, set in serializer or validate
            serializer.save()
        else:
            serializer.save()


class LevelViewSet(viewsets.ModelViewSet):
    """ViewSet for managing levels"""
    serializer_class = LevelSerializer
    queryset = Level.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()


class SubjectViewSet(viewsets.ModelViewSet):
    """ViewSet for managing subjects"""
    serializer_class = SubjectSerializer
    queryset = Subject.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()


class ClassViewSet(viewsets.ModelViewSet):
    """ViewSet for managing classes"""
    serializer_class = ClassSerializer
    queryset = Class.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()

    @action(detail=False, methods=['get'])
    def performance(self, request):
        """Get class performance analytics with grades and attendance"""
        from django.db.models import Avg, Count
        from datetime import timedelta
        from apps.attendance.models import Attendance
        from apps.academics.models import ExamResult, StudentClass

        school_id = get_school_filter(request.user)
        if not school_id:
            return Response({"error": "No school access"}, status=403)

        three_months_ago = timezone.now().date() - timedelta(days=90)

        classes = Class.objects.filter(school_id=school_id).annotate(
            student_count=Count('student_enrollments', filter=models.Q(student_enrollments__is_active=True))
        ).select_related('level')

        performance_data = []
        for cls in classes:
            # Student count
            student_count = cls.student_count or StudentClass.objects.filter(class_obj=cls, is_active=True).count()

            # Average grade score (percentage from all exams)
            avg_score = 0
            exam_results = ExamResult.objects.filter(exam__class_obj=cls)
            if exam_results.exists():
                avg_score = exam_results.aggregate(average=Avg('percentage'))['average'] or 0

            # Attendance percentage (last 90 days)
            total_attendance_days = Attendance.objects.filter(
                class_obj=cls, 
                date__gte=three_months_ago
            ).values('date').distinct().count()
            
            present_days = Attendance.objects.filter(
                class_obj=cls,
                date__gte=three_months_ago,
                status='present'
            ).count()
            
            attendance_pct = 0
            if total_attendance_days > 0 and student_count > 0:
                attendance_pct = (present_days / (total_attendance_days * student_count)) * 100

            # Combined performance score (50% grades + 50% attendance)
            performance_score = ((avg_score * 0.5) + (attendance_pct * 0.5))

            performance_data.append({
                'classId': cls.id,
                'className': cls.name,
                'averageScore': round(avg_score, 2),
                'attendancePercentage': round(attendance_pct, 2),
                'performanceScore': round(performance_score, 2),
                'studentCount': student_count,
            })

        # Sort by performance score descending, top 10
        performance_data.sort(key=lambda x: x['performanceScore'], reverse=True)
        performance_data = performance_data[:10]

        return Response({'results': performance_data})

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsSchoolAdminOrTeacher])
    def my_class_subjects(self, request):
        """Get subjects assigned to teacher in specific class (with form tutor fallback)"""
        class_id = request.query_params.get('class_obj')
        if not class_id:
            return Response({'error': 'class_obj required'}, status=status.HTTP_400_BAD_REQUEST)
        
        from apps.academics.models import ClassSubjectTeacher, ClassTeacher, ClassSubject
        
        # Primary: teacher's specific subjects
        queryset = ClassSubjectTeacher.objects.filter(
            teacher=request.user,
            class_obj_id=class_id,
            is_active=True
        ).select_related('subject')
        
        is_form_tutor = False
        if not queryset.exists():
            # Fallback: form tutor gets all class subjects
            form_tutor_qs = ClassTeacher.objects.filter(
                teacher=request.user,
                class_obj_id=class_id,
                is_form_tutor=True
            )
            is_form_tutor = form_tutor_qs.exists()
            
            if is_form_tutor:
                queryset = ClassSubject.objects.filter(
                    class_obj_id=class_id
                ).select_related('subject')
        
        class_subjects = queryset.values('subject_id', subject_name=F('subject__name'), subject_code=F('subject__code'))
        
        print(f"[my_class_subjects] Teacher {request.user.id}, class {class_id}: {queryset.count()} subjects, form_tutor={is_form_tutor}")
        
        return Response({
            'results': list(class_subjects),
            'is_form_tutor': is_form_tutor
        })

    @action(detail=False, methods=['get'], url_path='teacher-dashboard', permission_classes=[IsAuthenticated, IsSchoolAdminOrTeacher])
    def teacher_dashboard(self, request):
        """Teacher dashboard data: assigned classes, subject assignments, summary, attendance and student gender distribution."""
        from apps.academics.models import ClassTeacher, ClassSubjectTeacher, StudentClass
        from apps.attendance.models import Attendance

        school_id = get_school_filter(request.user)
        if school_id is None:
            return Response({"error": "No school access"}, status=status.HTTP_403_FORBIDDEN)

        class_teacher_qs = ClassTeacher.objects.filter(
            teacher=request.user,
            class_obj__school_id=school_id
        ).select_related('class_obj', 'class_obj__level')

        class_subject_teacher_qs = ClassSubjectTeacher.objects.filter(
            teacher=request.user,
            class_obj__school_id=school_id,
            is_active=True
        ).select_related('class_obj', 'class_obj__level', 'subject')

        assigned_class_map = {}

        for ct in class_teacher_qs:
            cls = ct.class_obj
            assigned_class_map[cls.id] = {
                'class_id': cls.id,
                'class_name': cls.name,
                'level_name': getattr(cls.level, 'name', None),
                'is_form_tutor': bool(ct.is_form_tutor),
            }

        for cst in class_subject_teacher_qs:
            cls = cst.class_obj
            if cls.id not in assigned_class_map:
                assigned_class_map[cls.id] = {
                    'class_id': cls.id,
                    'class_name': cls.name,
                    'level_name': getattr(cls.level, 'name', None),
                    'is_form_tutor': False,
                }

        class_ids = list(assigned_class_map.keys())
        student_counts = {}
        if class_ids:
            student_counts_qs = StudentClass.objects.filter(
                class_obj_id__in=class_ids,
                is_active=True
            ).values('class_obj_id').annotate(total=models.Count('id'))
            student_counts = {row['class_obj_id']: row['total'] for row in student_counts_qs}

        assigned_classes = []
        for class_id, class_data in assigned_class_map.items():
            class_data['student_count'] = student_counts.get(class_id, 0)
            assigned_classes.append(class_data)

        assigned_classes.sort(key=lambda x: (x.get('class_name') or '').lower())

        subject_assignment_map = {}
        for cst in class_subject_teacher_qs:
            key = cst.class_obj_id
            if key not in subject_assignment_map:
                subject_assignment_map[key] = {
                    'class_id': cst.class_obj_id,
                    'class_name': cst.class_obj.name,
                    'subjects': []
                }
            subject_assignment_map[key]['subjects'].append({
                'subject_id': cst.subject_id,
                'subject_name': cst.subject.name,
                'subject_code': cst.subject.code
            })

        subject_assignments = list(subject_assignment_map.values())
        subject_assignments.sort(key=lambda x: (x.get('class_name') or '').lower())

        total_students = sum(item.get('student_count', 0) for item in assigned_classes)
        total_subject_assignments = class_subject_teacher_qs.count()

        attendance_overview = {'present': 0, 'late': 0, 'absent': 0}
        gender_distribution = {'male': 0, 'female': 0}

        if class_ids:
            attendance_counts = Attendance.objects.filter(
                class_obj_id__in=class_ids
            ).values('status').annotate(total=models.Count('id'))

            for row in attendance_counts:
                status_key = row.get('status')
                if status_key in attendance_overview:
                    attendance_overview[status_key] = row.get('total', 0)

            student_gender_counts = StudentClass.objects.filter(
                class_obj_id__in=class_ids,
                is_active=True
            ).values('student__student_profile__gender').annotate(total=models.Count('id'))

            for row in student_gender_counts:
                gender = (row.get('student__student_profile__gender') or '').strip().lower()
                total = row.get('total', 0)
                if gender in ['m', 'male', 'boy', 'boys']:
                    gender_distribution['male'] += total
                elif gender in ['f', 'female', 'girl', 'girls']:
                    gender_distribution['female'] += total

        return Response({
            'assigned_classes': assigned_classes,
            'subject_assignments': subject_assignments,
            'summary': {
                'total_classes': len(assigned_classes),
                'total_subject_assignments': total_subject_assignments,
                'total_students': total_students,
            },
            'attendance_overview': attendance_overview,
            'gender_distribution': gender_distribution,
        })



class ClassSubjectViewSet(viewsets.ModelViewSet):
    """ViewSet for managing class subjects"""
    serializer_class = ClassSubjectSerializer
    queryset = ClassSubject.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(class_obj__school_id=school_id)

    def perform_create(self, serializer):
        serializer.save()


class EnrollmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing enrollments"""
    serializer_class = EnrollmentSerializer
    queryset = Enrollment.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(class_obj__school_id=school_id)

    def perform_create(self, serializer):
        serializer.save()


class TimetableViewSet(viewsets.ModelViewSet):
    """ViewSet for managing timetables"""
    serializer_class = TimetableSerializer
    queryset = Timetable.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(class_obj__school_id=school_id)

    def perform_create(self, serializer):
        serializer.save()


class AcademicCalendarEventViewSet(viewsets.ModelViewSet):
    """ViewSet for academic calendar events"""
    serializer_class = AcademicCalendarEventSerializer
    queryset = AcademicCalendarEvent.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id, created_by=self.request.user)
        else:
            serializer.save(created_by=self.request.user)

class ExamViewSet(viewsets.ModelViewSet):
    """ViewSet for managing exams"""
    serializer_class = ExamSerializer
    queryset = Exam.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id, created_by=self.request.user)
        else:
            serializer.save(created_by=self.request.user)


class ExamResultViewSet(viewsets.ModelViewSet):
    """ViewSet for exam results"""
    serializer_class = ExamResultSerializer
    queryset = ExamResult.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id, recorded_by=self.request.user)
        else:
            serializer.save(recorded_by=self.request.user)


class SchoolFeesViewSet(viewsets.ModelViewSet):
    """ViewSet for school fees"""
    serializer_class = SchoolFeesSerializer
    queryset = SchoolFees.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)


class SchoolEventViewSet(viewsets.ModelViewSet):
    """ViewSet for school events"""
    serializer_class = SchoolEventSerializer
    queryset = SchoolEvent.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id, created_by=self.request.user)
        else:
            serializer.save(created_by=self.request.user)


class NoticeViewSet(viewsets.ModelViewSet):
    """ViewSet for notices"""
    serializer_class = NoticeSerializer
    queryset = Notice.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id, posted_by=self.request.user)
        else:
            serializer.save(posted_by=self.request.user)


class UserProfilePictureViewSet(viewsets.ModelViewSet):
    """ViewSet for user profile pictures"""
    serializer_class = UserProfilePictureSerializer
    queryset = UserProfilePicture.objects.all()
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrSelf()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        queryset = self.queryset.all()
        
        if school_id is not None:
            queryset = queryset.filter(user__school_id=school_id)
            
        # Filter by user if provided in query params
        user_id = self.request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
            
        return queryset

    def create(self, request, *args, **kwargs):
        from apps.storage.supabase_service import SupabaseStorageService
        from apps.users.models import User

        picture_file = request.FILES.get('picture') or request.FILES.get('profile_picture')
        if not picture_file:
            return Response({'error': 'No profile picture file provided'}, status=status.HTTP_400_BAD_REQUEST)

        user_id = request.data.get('user')
        if request.user.role not in ['super_admin', 'school_admin']:
            target_user = request.user
        else:
            if not user_id:
                return Response({'error': 'user is required'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if target_user.role not in ['student', 'teacher', 'school_admin', 'super_admin']:
            return Response({'error': 'Invalid user role for profile picture'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            service = SupabaseStorageService()
            storage_path, storage_url = service.upload_profile_picture(
                file_obj=picture_file,
                user_id=target_user.id,
                user_name=target_user.get_full_name() or target_user.username
            )

            obj, _ = UserProfilePicture.objects.update_or_create(
                user=target_user,
                defaults={
                    'storage_path': storage_path,
                    'storage_url': storage_url,
                    'file_size': getattr(picture_file, 'size', None),
                    'content_type': getattr(picture_file, 'content_type', None),
                }
            )

            serializer = self.get_serializer(obj)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': f'Failed to upload profile picture: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClassTeacherViewSet(viewsets.ModelViewSet):
    """ViewSet for class teachers"""
    serializer_class = ClassTeacherSerializer
    queryset = ClassTeacher.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(class_obj__school_id=school_id)


class StudentClassViewSet(viewsets.ModelViewSet):
    """ViewSet for student classes"""
    serializer_class = StudentClassSerializer
    queryset = StudentClass.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(class_obj__school_id=school_id)


class ClassSubjectTeacherViewSet(viewsets.ModelViewSet):
    """ViewSet for class subject teachers"""
    serializer_class = ClassSubjectTeacherSerializer
    queryset = ClassSubjectTeacher.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(class_obj__school_id=school_id)


class AcademicSessionViewSet(viewsets.ModelViewSet):
    """ViewSet for academic sessions"""
    serializer_class = AcademicSessionSerializer
    queryset = AcademicSession.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()


class TerminalReportViewSet(viewsets.ModelViewSet):
    """ViewSet for terminal reports"""
    serializer_class = TerminalReportListSerializer
    queryset = TerminalReport.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    @action(detail=False, methods=['post'], url_path='generate_report')
    def generate_report(self, request):
        serializer = GenerateTerminalReportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        school_id = get_school_filter(request.user)
        if not school_id:
            return Response({"error": "No school access"}, status=status.HTTP_403_FORBIDDEN)

        # Verify class belongs to school
        try:
            class_obj = Class.objects.get(id=data['class_id'])
        except Class.DoesNotExist:
            return Response({"error": "Class not found"}, status=status.HTTP_404_NOT_FOUND)

        if class_obj.school_id != school_id:
            return Response({"error": "Unauthorized access to class"}, status=status.HTTP_403_FORBIDDEN)

        # Calculate report data
        report_data = calculate_student_report_data(
            data['student_id'], data['class_id'], data['session_id']
        )
        if not report_data['success']:
            return Response({"error": report_data['error']}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            report, created = TerminalReport.objects.update_or_create(
                student_id=data['student_id'],
                class_obj_id=data['class_id'],
                academic_session_id=data['session_id'],
                defaults={
                    'school_id': school_id,
                    **report_data['aggregates'],
                    'generated_by': request.user
                }
            )

            # Deterministic regeneration of subject scores
            report.subject_scores.all().delete()
            SubjectScore.objects.bulk_create([
                SubjectScore(
                    terminal_report=report,
                    subject_id=ss_data['subject_id'],
                    total_score=ss_data['total_score'],
                    percentage=ss_data['percentage'],
                    grade=ss_data['grade'],
                    remarks=ss_data['remarks'],
                    subject_position=ss_data['subject_position'],
                    subject_total_students=ss_data['subject_total_students']
                )
                for ss_data in report_data['subject_scores']
            ])

        response_serializer = self.get_serializer(report)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], url_path='compute_class_reports')
    def compute_class_reports(self, request):
        """Generate terminal reports for ALL students in a class at once"""
        class_id = request.data.get('class_id')
        session_id = request.data.get('session_id')

        if not class_id or not session_id:
            return Response({"error": "class_id and session_id required"}, status=status.HTTP_400_BAD_REQUEST)

        school_id = get_school_filter(request.user)
        if not school_id:
            return Response({"error": "No school access"}, status=status.HTTP_403_FORBIDDEN)

        try:
            class_obj = Class.objects.get(id=class_id, school_id=school_id)
        except Class.DoesNotExist:
            return Response({"error": "Class not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            session = AcademicSession.objects.get(id=session_id, school_id=school_id)
        except AcademicSession.DoesNotExist:
            return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get all active students in class
        student_ids = StudentClass.objects.filter(
            class_obj=class_obj, is_active=True
        ).values_list('student_id', flat=True)

        if not student_ids:
            return Response({"error": "No students in this class"}, status=status.HTTP_400_BAD_REQUEST)

        reports_generated = 0
        errors = []

        for student_id in student_ids:
            report_data = calculate_student_report_data(
                student_id, class_id, session_id
            )
            if not report_data['success']:
                errors.append({'student_id': student_id, 'error': report_data['error']})
                continue

            with transaction.atomic():
                report, created = TerminalReport.objects.update_or_create(
                    student_id=student_id,
                    class_obj_id=class_id,
                    academic_session_id=session_id,
                    defaults={
                        'school_id': school_id,
                        **report_data['aggregates'],
                        'generated_by': request.user
                    }
                )

                report.subject_scores.all().delete()
                SubjectScore.objects.bulk_create([
                    SubjectScore(
                        terminal_report=report,
                        subject_id=ss_data['subject_id'],
                        total_score=ss_data['total_score'],
                        percentage=ss_data['percentage'],
                        grade=ss_data['grade'],
                        remarks=ss_data['remarks'],
                        subject_position=ss_data['subject_position'],
                        subject_total_students=ss_data['subject_total_students']
                    )
                    for ss_data in report_data['subject_scores']
                ])

            if created:
                reports_generated += 1

        return Response({
            'success': True,
            'class_id': int(class_id),
            'session_id': int(session_id),
            'reports_generated': reports_generated,
            'total_students': len(student_ids),
            'errors': errors
        })

    @action(detail=False, methods=['get'], url_path='class_reports')
    def class_reports(self, request):
        """Get all terminal reports for a class/session"""
        class_id = request.query_params.get('class_id')
        session_id = request.query_params.get('session_id')

        if not class_id:
            return Response({"error": "class_id required"}, status=status.HTTP_400_BAD_REQUEST)

        school_id = get_school_filter(request.user)
        reports = self.get_queryset().filter(
            class_obj_id=class_id,
            academic_session_id=session_id if session_id else None
        ).select_related('student', 'academic_session').prefetch_related('subject_scores__subject')

        # Build rich response with all computed fields
        results = []
        for report in reports:
            subject_scores = []
            for ss in report.subject_scores.all().select_related('subject'):
                subject_scores.append({
                    'subject_id': ss.subject_id,
                    'subject_name': ss.subject.name,
                    'total_score': ss.total_score,
                    'percentage': ss.percentage,
                    'grade': ss.grade,
                    'subject_position': ss.subject_position,
                    'subject_total_students': ss.subject_total_students,
                })

            results.append({
                'id': report.id,
                'student_id': report.student_id,
                'student_name': report.student.get_full_name() or report.student.username,
                'class_id': report.class_obj_id,
                'class_name': report.class_obj.name if report.class_obj_id else None,
                'session_id': report.academic_session_id,
                'session_name': report.academic_session.name if report.academic_session else None,
                'total_marks': report.total_marks,
                'average_marks': report.average_marks,
                'position': report.position,
                'total_students': report.total_students,
                'grade': report.grade,
                'total_days': report.total_days,
                'days_present': report.days_present,
                'attendance_percentage': report.attendance_percentage,
                'promotion_status': report.promotion_status,
                'best_subject_name': report.best_subject_name,
                'best_subject_score': report.best_subject_score,
                'form_teacher_remarks': report.form_teacher_remarks,
                'principal_remarks': report.principal_remarks,
                'status': report.status,
                'subject_scores': subject_scores,
            })

        # Calculate class-level stats
        if results:
            results.sort(key=lambda r: (r['position'] or 999))
            best_student = results[0] if results else None
            best_subject = max(
                (ss for r in results for ss in r['subject_scores']),
                key=lambda ss: ss['percentage'],
                default=None
            )

            class_summary = {
                'total_students': len(results),
                'average_score': sum(r['average_marks'] for r in results) / len(results) if results else 0,
                'best_student_name': best_student['student_name'] if best_student else None,
                'best_student_score': best_student['average_marks'] if best_student else 0,
                'best_subject_name': best_subject['subject_name'] if best_subject else None,
                'best_subject_score': best_subject['percentage'] if best_subject else 0,
                'students_promoted': sum(1 for r in results if r['promotion_status'] == 'promoted'),
                'students_repeated': sum(1 for r in results if r['promotion_status'] == 'repeated'),
            }
        else:
            class_summary = {}

        # Include active grading scale (grading system) and assessment titles (exam types)
        grading_system = None
        assessments_payload = {
            'continuous_assessments': [],
            'examinations': [],
        }

        try:
            target_session_id = int(session_id) if session_id else None
        except (TypeError, ValueError):
            target_session_id = None

        # Grading system
        grading_scale_qs = GradingScale.objects.filter(
            school_id=school_id,
            is_active=True
        ).prefetch_related('entries')

        if target_session_id:
            grading_scale_qs = grading_scale_qs.filter(academic_session_id=target_session_id)

        grading_scale = grading_scale_qs.order_by('-is_default', '-updated_at').first()
        if grading_scale:
            grading_system = {
                'id': grading_scale.id,
                'name': grading_scale.name,
                'is_default': grading_scale.is_default,
                'entries': [
                    {
                        'grade_letter': e.grade_letter,
                        'min_percentage': e.min_percentage,
                        'max_percentage': e.max_percentage,
                        'remark': e.remark,
                        'promotion_eligible': e.promotion_eligible,
                        'is_passing': e.is_passing,
                        'order': e.order,
                    }
                    for e in grading_scale.entries.all().order_by('order', '-max_percentage')
                ]
            }

        # Exam types / assessments created by school admin/teachers
        assessments_qs = Assessment.objects.filter(
            school_id=school_id,
            class_obj_id=class_id,
            is_active=True
        ).select_related('subject', 'academic_session')

        if target_session_id:
            assessments_qs = assessments_qs.filter(academic_session_id=target_session_id)

        assessments_payload['continuous_assessments'] = [
            {
                'id': a.id,
                'title': a.title,
                'category': a.category,
                'subject_id': a.subject_id,
                'subject_name': a.subject.name if a.subject_id else None,
                'term': a.term,
                'total_marks': a.total_marks,
                'weight_percentage': a.weight_percentage,
                'assessment_date': a.assessment_date,
            }
            for a in assessments_qs.filter(category='continuous_assessment').order_by('assessment_date', 'title')
        ]
        assessments_payload['examinations'] = [
            {
                'id': a.id,
                'title': a.title,
                'category': a.category,
                'subject_id': a.subject_id,
                'subject_name': a.subject.name if a.subject_id else None,
                'term': a.term,
                'total_marks': a.total_marks,
                'weight_percentage': a.weight_percentage,
                'assessment_date': a.assessment_date,
            }
            for a in assessments_qs.filter(category='examination').order_by('assessment_date', 'title')
        ]

        return Response({
            'results': results,
            'summary': class_summary,
            'grading_system': grading_system,
            'assessments': assessments_payload,
        })


class GradingPolicyViewSet(viewsets.ModelViewSet):

    """ViewSet for grading policies"""
    serializer_class = GradingPolicySerializer
    queryset = GradingPolicy.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'bulk_create']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.filter(school__isnull=False)  # Prevent None school policies
        return self.queryset.filter(school_id=school_id)

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id)

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()

    @action(detail=False, methods=['get'])
    def by_session(self, request):
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({"error": "session_id required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            session_id = int(session_id)
        except ValueError:
            return Response({"error": "session_id must be integer"}, status=status.HTTP_400_BAD_REQUEST)
        
        school_id = get_school_filter(request.user)
        queryset = self.get_queryset().filter(academic_session_id=session_id)
        if school_id:
            queryset = queryset.filter(school_id=school_id)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Bulk create/replace grading policies for a session"""
        import logging
        logger = logging.getLogger(__name__)
        
        session_id = request.data.get('session_id')
        policies_data = request.data.get('policies', [])
        
        if not session_id:
            return Response({"error": "session_id required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            session_id = int(session_id)
        except ValueError:
            return Response({"error": "session_id must be integer"}, status=status.HTTP_400_BAD_REQUEST)
        
        school_id = get_school_filter(request.user)
        if not school_id:
            return Response({"error": "No school access - user must be assigned to a school"}, status=status.HTTP_403_FORBIDDEN)
        
        from apps.academics.models import AcademicSession
        try:
            session_obj = AcademicSession.objects.get(id=session_id, school_id=school_id)
        except AcademicSession.DoesNotExist:
            return Response({"error": "Academic session not found or access denied"}, status=status.HTTP_404_NOT_FOUND)
        
        logger.info(f"Bulk creating grading policies for school_id={school_id}, session_id={session_id}, user={request.user.id}")
        
        # Validate total weightage
        total_weight = sum(float(p.get('weightage', 0)) for p in policies_data)
        if not (95 <= total_weight <= 105):  # Allow small rounding errors
            return Response({
                "error": "Total weightage must be approximately 100%",
                "total_weight": total_weight
            }, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Delete existing policies for this session/school
            deleted_count, _ = self.queryset.filter(
                academic_session_id=session_id, 
                school_id=school_id
            ).delete()
            logger.info(f"Deleted {deleted_count} existing policies")
            
            # Bulk create new policies
            created_policies = []
            for policy_data in policies_data:
                # Clean frontend data, set backend IDs explicitly
                policy_data = policy_data.copy()
                policy_data['school_id'] = school_id
                policy_data['academic_session_id'] = session_id
                policy_data.pop('school', None)  # Remove if frontend sends conflicting
                
                serializer = self.get_serializer(data=policy_data)
                if serializer.is_valid():
                    # Explicitly pass school_id to save
                    instance = serializer.save(school_id=school_id)
                    created_policies.append(serializer.data)
                else:
                    logger.error(f"Validation failed: {serializer.errors}")
                    raise serializers.ValidationError(serializer.errors)
            
            logger.info(f"Successfully created {len(created_policies)} grading policies")
        
        return Response({
            "message": f"Successfully created {len(created_policies)} grading policies",
            "policies": created_policies,
            "total_weight": total_weight,
            "deleted_count": deleted_count
        }, status=status.HTTP_201_CREATED)


from apps.students.models import Grade


class AssessmentViewSet(viewsets.ViewSet):
    """Assessment helper endpoints used by grade entry workflow."""
    permission_classes = [IsAuthenticated, IsSchoolAdminOrTeacher]

    @action(detail=False, methods=['get'], url_path='by_class_subject_term')
    def by_class_subject_term(self, request):
        class_id = request.query_params.get('class_id')
        subject_id = request.query_params.get('subject_id')
        term = request.query_params.get('term')
        academic_session_id = request.query_params.get('academic_session_id')

        if not class_id or not subject_id:
            return Response(
                {'error': 'class_id and subject_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            class_id = int(class_id)
            subject_id = int(subject_id)
            if academic_session_id is not None:
                academic_session_id = int(academic_session_id)
            if term is not None:
                term = int(term)
        except ValueError:
            return Response(
                {'error': 'class_id, subject_id, term and academic_session_id must be integers when provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        school_id = get_school_filter(request.user)

        # Base grade queryset
        grades_qs = Grade.objects.filter(
            student__class_assignments__class_obj_id=class_id,
            student__class_assignments__is_active=True,
            subject_id=subject_id,
        ).select_related('student', 'subject', 'academic_session').distinct()

        if school_id is not None:
            grades_qs = grades_qs.filter(student__school_id=school_id)

        if academic_session_id is not None:
            grades_qs = grades_qs.filter(academic_session_id=academic_session_id)

        if term is not None:
            grades_qs = grades_qs.filter(
                Q(academic_session__term=term) |
                Q(academic_session__term__isnull=True)
            )

        # Teachers can only see grades they are allowed to manage
        if request.user.role == 'teacher':
            from apps.academics.models import ClassSubjectTeacher, ClassTeacher

            allowed_subject_assignment = ClassSubjectTeacher.objects.filter(
                teacher=request.user,
                class_obj_id=class_id,
                subject_id=subject_id,
                is_active=True
            ).exists()

            is_form_tutor = ClassTeacher.objects.filter(
                teacher=request.user,
                class_obj_id=class_id,
                is_form_tutor=True
            ).exists()

            if not (allowed_subject_assignment or is_form_tutor):
                return Response(
                    {'error': 'No access to assessments for this class/subject'},
                    status=status.HTTP_403_FORBIDDEN
                )

        results = []
        for g in grades_qs:
            max_score = float(g.max_score) if g.max_score else 100.0
            score = float(g.score) if g.score is not None else None

            results.append({
                'id': g.id,
                'student_id': g.student_id,
                'student_name': g.student.get_full_name() or g.student.username,
                'subject_id': g.subject_id,
                'subject_name': g.subject.name if g.subject else None,
                'assessment_type': g.assessment_type,
                'score': score,
                'max_score': max_score,
                'percentage': float(g.percentage) if g.percentage is not None else None,
                'grade': g.grade,
                'is_locked': bool(g.is_locked),
                'academic_session_id': g.academic_session_id,
                'term': g.academic_session.term if g.academic_session else None,
                'recorded_date': g.recorded_date,
                'created_at': g.created_at,
                'updated_at': g.updated_at,
            })

        return Response(results, status=status.HTTP_200_OK)


class TerminalReportTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing terminal report templates"""
    serializer_class = TerminalReportTemplateSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return TerminalReportTemplate.objects.all()
        return TerminalReportTemplate.objects.filter(school_id=school_id)
    
    from .utils import sanitize_html
    
    def perform_create(self, serializer):
        school_id = getattr(self.request.user, 'school_id', None)
        if school_id:
            instance = serializer.save(school_id=school_id, created_by=self.request.user)
            instance.html_template = sanitize_html(instance.html_template)
            instance.save()
        else:
            instance = serializer.save(created_by=self.request.user)
            instance.html_template = sanitize_html(instance.html_template)
            instance.save()

    from .utils import sanitize_html
    
    def perform_update(self, serializer):
        instance = serializer.save()
        instance.html_template = sanitize_html(instance.html_template)
        instance.save()
        return instance
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active templates for school/session"""
        session_id = request.query_params.get('session_id')
        school_id = get_school_filter(request.user)
        templates = TerminalReportTemplate.objects.filter(school_id=school_id, is_active=True)
        if session_id:
            templates = templates.filter(academic_session_id=session_id)
        templates = templates.order_by('-is_default')
        return Response(self.get_serializer(templates, many=True).data)
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set this template as default for school/session"""
        template = self.get_object()
        template.is_default = True
        template.save()
        return Response(self.get_serializer(template).data)
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate this template"""
        template = self.get_object()
        new_template = TerminalReportTemplate.objects.create(
            school=template.school,
            academic_session=template.academic_session,
            name=f"Copy of {template.name}",
            structure=template.structure,
            html_template=template.html_template,
            preview_data=template.preview_data,
            created_by=request.user
        )
        return Response(self.get_serializer(new_template).data)

    @action(detail=False, methods=['post'])
    def preview_render(self, request):
        """Preview rendered template with mock/student data"""
        template_id = request.data.get('template_id')
        student_data = request.data.get('student_data', {})
        try:
            rendered_html = render_template_html(template_id, student_data)
            return Response({'rendered_html': rendered_html})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['post'])
    def generate_pdf(self, request, pk=None):
        """Generate PDF from rendered template"""
        from weasyprint import HTML
        from django.http import HttpResponse
        
        template = self.get_object()
        student_data = request.data.get('student_data', {})
        rendered_html = render_template_html(template.id, student_data)
        
        html_doc = HTML(string=rendered_html)
        pdf_bytes = html_doc.write_pdf()
        
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="report-{student_data.get("student_name", "student")}.pdf"'
        return response


# ==================== GRADING SCALE VIEWSET ====================

class GradingScaleViewSet(viewsets.ModelViewSet):
    """ViewSet for managing grading scales (grade boundaries)"""
    queryset = GradingScale.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return GradingScaleWithEntriesSerializer
        return GradingScaleSerializer

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id).prefetch_related('entries')

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active/default grading scales for school/session"""
        session_id = request.query_params.get('session_id')
        school_id = get_school_filter(request.user)
        queryset = GradingScale.objects.filter(school_id=school_id, is_active=True)
        if session_id:
            queryset = queryset.filter(academic_session_id=session_id)
        queryset = queryset.prefetch_related('entries').order_by('-is_default')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = GradingScaleSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = GradingScaleSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set this grading scale as default"""
        scale = self.get_object()
        GradingScale.objects.filter(
            school=scale.school,
            academic_session=scale.academic_session
        ).exclude(id=scale.id).update(is_default=False)
        scale.is_default = True
        scale.save()
        serializer = GradingScaleSerializer(scale)
        return Response(serializer.data)


# ==================== ASSESSMENT VIEWSET (NEW) ====================

class GradingAssessmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing assessments (exam types created by school admin)"""
    serializer_class = AssessmentSerializer
    queryset = Assessment.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return self.queryset.all()
        return self.queryset.filter(school_id=school_id).select_related(
            'subject', 'class_obj', 'academic_session', 'created_by'
        )

    def perform_create(self, serializer):
        school_id = get_school_filter(self.request.user)
        if school_id:
            serializer.save(school_id=school_id, created_by=self.request.user)
        else:
            serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'], url_path='by_class_subject_term')
    def by_class_subject_term(self, request):
        """Get all assessments for a class/subject/term"""
        class_id = request.query_params.get('class_id')
        subject_id = request.query_params.get('subject_id')
        term = request.query_params.get('term')
        academic_session_id = request.query_params.get('academic_session_id')

        if not class_id or not subject_id:
            return Response({'error': 'class_id and subject_id are required'}, status=400)

        try:
            class_id = int(class_id)
            subject_id = int(subject_id)
            if academic_session_id: academic_session_id = int(academic_session_id)
            if term: term = int(term)
        except ValueError:
            return Response({'error': 'Invalid parameters'}, status=400)

        school_id = get_school_filter(request.user)
        queryset = Assessment.objects.filter(
            school_id=school_id,
            class_obj_id=class_id,
            subject_id=subject_id,
            is_active=True
        ).select_related('subject', 'class_obj', 'academic_session')

        if academic_session_id:
            queryset = queryset.filter(academic_session_id=academic_session_id)
        if term:
            queryset = queryset.filter(term=term)

        continuous = queryset.filter(category='continuous_assessment')
        examinations = queryset.filter(category='examination')

        return Response({
            'continuous_assessments': AssessmentSerializer(continuous, many=True).data,
            'examinations': AssessmentSerializer(examinations, many=True).data
        })

    @action(detail=False, methods=['get'])
    def assessment_scores(self, request):
        """Get students and their scores for a specific assessment"""
        assessment_id = request.query_params.get('assessment_id')
        if not assessment_id:
            return Response({'error': 'assessment_id required'}, status=400)

        try:
            assessment = Assessment.objects.get(id=assessment_id)
        except Assessment.DoesNotExist:
            return Response({'error': 'Assessment not found'}, status=404)

        # Get students in the class
        from apps.academics.models import StudentClass as StudentEnrollment
        student_enrollments = StudentEnrollment.objects.filter(
            class_obj=assessment.class_obj,
            is_active=True
        ).select_related('student').order_by('student__first_name', 'student__last_name')

        students = []
        graded_count = 0

        for se in student_enrollments:
            student = se.student
            # Check if grade exists for this assessment
            grade = Grade.objects.filter(
                student=student,
                subject=assessment.subject,
                academic_session=assessment.academic_session,
            ).filter(
                assessment_type='exam' if assessment.category == 'examination' else 'test'
            ).first()

            has_score = grade is not None
            if has_score:
                graded_count += 1

            students.append({
                'student_id': student.id,
                'student_name': student.get_full_name() or student.username,
                'first_name': student.first_name,
                'last_name': student.last_name,
                'score': grade.score if grade else None,
                'grade_id': grade.id if grade else None,
                'percentage': grade.percentage if grade else None,
                'grade_letter': grade.grade if grade else None,
                'has_score': has_score,
            })

        return Response({
            'assessment': AssessmentSerializer(assessment).data,
            'students': students,
            'total_students': len(students),
            'graded_count': graded_count,
        })

    @action(detail=True, methods=['post'], url_path='bulk_save_scores')
    def bulk_save_scores(self, request, pk=None):
        """Bulk save/update scores for all students in an assessment"""
        try:
            assessment = self.get_object()
        except Assessment.DoesNotExist:
            return Response({'error': 'Assessment not found'}, status=404)

        scores_data = request.data.get('scores', [])
        results = []
        errors = []

        for item in scores_data:
            student_id = item.get('student_id')
            score = item.get('score')

            if not student_id or score is None:
                errors.append({'student_id': student_id, 'error': 'student_id and score required'})
                continue

            try:
                student_id = int(student_id)
                score_val = float(score)
            except (ValueError, TypeError):
                errors.append({'student_id': student_id, 'error': 'Invalid student_id or score'})
                continue

            # Check student belongs to this class
            from apps.academics.models import StudentClass as StudentEnrollment
            enrolled = StudentEnrollment.objects.filter(
                student_id=student_id,
                class_obj=assessment.class_obj,
                is_active=True
            ).exists()

            if not enrolled:
                errors.append({'student_id': student_id, 'error': 'Student not in class'})
                continue

            # Create or update grade
            assessment_type = 'exam' if assessment.category == 'examination' else 'test'
            
            try:
                grade, created = Grade.objects.update_or_create(
                    student_id=student_id,
                    subject=assessment.subject,
                    academic_session=assessment.academic_session,
                    assessment_type=assessment_type,
                    defaults={
                        'score': score_val,
                        'max_score': assessment.total_marks,
                    }
                )
                results.append({
                    'student_id': student_id,
                    'grade_id': grade.id,
                    'score': score_val,
                    'percentage': grade.percentage,
                    'grade': grade.grade,
                    'was_created': created,
                })
            except Exception as e:
                errors.append({'student_id': student_id, 'error': str(e)})

        return Response({
            'assessment_id': assessment.id,
            'assessment_title': assessment.title,
            'results': results,
            'errors': errors,
            'success_count': len(results),
            'error_count': len(errors),
        })

    @action(detail=False, methods=['get'])
    def compute_results(self, request):
        """Compute final scores with grades, remarks, and positions for a class/subject"""
        class_id = request.query_params.get('class_id')
        subject_id = request.query_params.get('subject_id')
        academic_session_id = request.query_params.get('academic_session_id')
        term = request.query_params.get('term')

        if not class_id or not subject_id:
            return Response({'error': 'class_id and subject_id required'}, status=400)

        try:
            class_id = int(class_id)
            subject_id = int(subject_id)
        except ValueError:
            return Response({'error': 'Invalid parameters'}, status=400)

        school_id = get_school_filter(request.user)

        # Get students in class
        from apps.academics.models import StudentClass as StudentEnrollment
        enrollments = StudentEnrollment.objects.filter(
            class_obj_id=class_id,
            is_active=True
        ).select_related('student').order_by('student__first_name', 'student__last_name')

        # Get grading policies for this session
        grading_policies = GradingPolicy.objects.none()
        if academic_session_id:
            grading_policies = GradingPolicy.objects.filter(
                school_id=school_id,
                academic_session_id=academic_session_id,
                is_active=True
            )

        results = []
        for enrollment in enrollments:
            student = enrollment.student

            # Sum of all CA grade percentages
            ca_grades = Grade.objects.filter(
                student=student,
                subject_id=subject_id,
                assessment_type__in=['test', 'quiz', 'assignment', 'continuous'],
                is_locked=True,
            )
            if academic_session_id:
                ca_grades = ca_grades.filter(academic_session_id=academic_session_id)
            
            ca_total = ca_grades.aggregate(total=models.Sum('percentage'))['total'] or 0

            # Exam grade
            exam_grades = Grade.objects.filter(
                student=student,
                subject_id=subject_id,
                assessment_type='exam',
                is_locked=True,
            )
            if academic_session_id:
                exam_grades = exam_grades.filter(academic_session_id=academic_session_id)
            
            exam_total = exam_grades.aggregate(total=models.Sum('percentage'))['total'] or 0
            exam_count = exam_grades.count()
            exam_avg = exam_total / exam_count if exam_count > 0 else 0

            # Final = CA + Exam (simple sum)
            final_score = ca_total + exam_avg

            # Determine grade
            grade_letter = 'F'
            if final_score >= 90: grade_letter = 'A'
            elif final_score >= 80: grade_letter = 'B'
            elif final_score >= 70: grade_letter = 'C'
            elif final_score >= 60: grade_letter = 'D'

            remark = _get_remark_for_grade(grade_letter)

            results.append({
                'student_id': student.id,
                'student_name': student.get_full_name() or student.username,
                'ca_score': round(ca_total, 2),
                'exam_score': round(exam_avg, 2),
                'exam_max': 100,
                'exam_percentage': round(exam_avg, 2),
                'final_score': round(final_score, 2),
                'percentage': round(final_score, 2),
                'grade': grade_letter,
                'remark': remark,
                'position': 0,  # Will be assigned after sorting
            })

        # Sort and assign positions
        results.sort(key=lambda r: (-r['final_score'], r['student_name']))
        for idx, r in enumerate(results, start=1):
            r['position'] = idx

        summary = {
            'highest_score': max((r['final_score'] for r in results), default=0),
            'lowest_score': min((r['final_score'] for r in results), default=0),
            'average_score': sum(r['final_score'] for r in results) / len(results) if results else 0,
        }

        return Response({
            'class_id': class_id,
            'subject_id': subject_id,
            'academic_session_id': academic_session_id,
            'term': term,
            'results': results,
            'total_students': len(results),
            'summary': summary,
        })


def _get_remark_for_grade(grade):
    """Get remark text for a grade"""
    remarks = {
        'A': 'Excellent',
        'B': 'Very Good',
        'C': 'Good',
        'D': 'Fair',
        'E': 'Poor',
        'F': 'Fail',
    }
    return remarks.get(grade, '')
