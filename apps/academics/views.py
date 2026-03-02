from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import models
from core.permissions import IsSchoolAdminOrHigher, IsSchoolAdminOrTeacher
from apps.academics.models import (
    Faculty, Department, Level, Subject, Class,
    ClassSubject, Enrollment, Timetable, AcademicCalendarEvent,
    Exam, ExamResult, SchoolFees, SchoolEvent, Document, DocumentFolder, Notice, UserProfilePicture,
    ClassTeacher, StudentClass, ClassSubjectTeacher, AcademicSession, TerminalReport, SubjectScore, GradingPolicy
)
from apps.academics.serializers import (
    FacultySerializer, DepartmentSerializer, LevelSerializer,
    SubjectSerializer, ClassSerializer, ClassSubjectSerializer,
    EnrollmentSerializer, TimetableSerializer, AcademicCalendarEventSerializer,
    ExamSerializer, ExamResultSerializer, SchoolFeesSerializer,
    SchoolEventSerializer, DocumentSerializer, DocumentFolderSerializer, NoticeSerializer, UserProfilePictureSerializer,
    ClassTeacherSerializer, StudentClassSerializer, ClassSubjectTeacherSerializer,
    AcademicSessionSerializer, TerminalReportSerializer, TerminalReportListSerializer, GradingPolicySerializer
)


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
    serializer_class = FacultySerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return Faculty.objects.all()
        return Faculty.objects.filter(school_id=school_id)


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return Department.objects.all()
        return Department.objects.filter(faculty__school_id=school_id)


class LevelViewSet(viewsets.ModelViewSet):
    serializer_class = LevelSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return Level.objects.all()
        return Level.objects.filter(school_id=school_id)


class SubjectViewSet(viewsets.ModelViewSet):
    serializer_class = SubjectSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return Subject.objects.all()
        return Subject.objects.filter(school_id=school_id)


class ClassViewSet(viewsets.ModelViewSet):
    serializer_class = ClassSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        
        # Students see only classes they're enrolled in
        if self.request.user.role == 'student':
            student_class_ids = StudentClass.objects.filter(student=self.request.user, is_active=True).values_list('class_obj_id', flat=True)
            if school_id:
                return Class.objects.filter(id__in=student_class_ids, school_id=school_id)
            return Class.objects.filter(id__in=student_class_ids)
        
        # Teachers see classes they manage or teach
        if self.request.user.role == 'teacher':
            teacher_class_ids = ClassTeacher.objects.filter(teacher=self.request.user).values_list('class_obj_id', flat=True)
            if school_id:
                return Class.objects.filter(id__in=teacher_class_ids, school_id=school_id)
            return Class.objects.filter(id__in=teacher_class_ids)
        
        # Admins and super_admins see all classes in their school
        if school_id is None:
            return Class.objects.all()
        return Class.objects.filter(school_id=school_id)
    
    def create(self, request, *args, **kwargs):
        try:
            print(f"[v0] ClassViewSet.create - received data: {request.data}")
            return super().create(request, *args, **kwargs)
        except Exception as e:
            print(f"[v0] ClassViewSet.create - error: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def perform_create(self, serializer):
        try:
            if self.request.user.school_id:
                print(f"[v0] ClassViewSet.perform_create - saving class with school_id: {self.request.user.school_id}")
                print(f"[v0] ClassViewSet.perform_create - validated data: {serializer.validated_data}")
                serializer.save(school_id=self.request.user.school_id)
            else:
                print(f"[v0] ClassViewSet.perform_create - no school_id for user: {self.request.user}")
                serializer.save()
            print(f"[v0] ClassViewSet.perform_create - class saved successfully: {serializer.data}")
        except Exception as e:
            print(f"[v0] ClassViewSet.perform_create - error: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]


class ClassSubjectViewSet(viewsets.ModelViewSet):
    serializer_class = ClassSubjectSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return ClassSubject.objects.all()
        return ClassSubject.objects.filter(class_obj__school_id=school_id)


class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        
        # Students can only see their own enrollments
        if self.request.user.role == 'student':
            if school_id:
                return Enrollment.objects.filter(student=self.request.user, class_obj__school_id=school_id)
            return Enrollment.objects.filter(student=self.request.user)
        
        # Teachers can see enrollments for their classes
        if self.request.user.role == 'teacher':
            if school_id:
                return Enrollment.objects.filter(class_obj__teachers__teacher=self.request.user, class_obj__school_id=school_id).distinct()
            return Enrollment.objects.filter(class_obj__teachers__teacher=self.request.user).distinct()
        
        # Admins see all
        if school_id:
            return Enrollment.objects.filter(class_obj__school_id=school_id)
        return Enrollment.objects.all()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]


class TimetableViewSet(viewsets.ModelViewSet):
    serializer_class = TimetableSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        
        # Students see timetables for their assigned classes
        if self.request.user.role == 'student':
            student_classes = StudentClass.objects.filter(student=self.request.user, is_active=True).values_list('class_obj_id', flat=True)
            if school_id:
                return Timetable.objects.filter(class_obj_id__in=student_classes, class_obj__school_id=school_id)
            return Timetable.objects.filter(class_obj_id__in=student_classes)
        
        # Teachers see timetables for classes they teach
        if self.request.user.role == 'teacher':
            if school_id:
                return Timetable.objects.filter(teacher=self.request.user, class_obj__school_id=school_id)
            return Timetable.objects.filter(teacher=self.request.user)
        
        # Admins see all
        if school_id:
            return Timetable.objects.filter(class_obj__school_id=school_id)
        return Timetable.objects.all()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]


class AcademicCalendarEventViewSet(viewsets.ModelViewSet):
    serializer_class = AcademicCalendarEventSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return AcademicCalendarEvent.objects.all()
        return AcademicCalendarEvent.objects.filter(school_id=school_id)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, school_id=self.request.user.school_id)


class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        try:
            school_id = get_school_filter(self.request.user)
            if school_id:
                return Exam.objects.filter(school_id=school_id).order_by('exam_date')
            return Exam.objects.all().order_by('exam_date')
        except Exception as e:
            print(f"[v0] Error in ExamViewSet.get_queryset: {e}")
            return Exam.objects.all().order_by('exam_date')
    
    def perform_create(self, serializer):
        school_id = getattr(self.request.user, 'school_id', None)
        if school_id:
            serializer.save(created_by=self.request.user, school_id=school_id)
        else:
            serializer.save(created_by=self.request.user)


class ExamResultViewSet(viewsets.ModelViewSet):
    serializer_class = ExamResultSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        try:
            school_id = get_school_filter(self.request.user)
            if school_id:
                return ExamResult.objects.filter(school_id=school_id).order_by('-recorded_date')
            return ExamResult.objects.all().order_by('-recorded_date')
        except Exception as e:
            print(f"[v0] Error in ExamResultViewSet.get_queryset: {e}")
            return ExamResult.objects.all().order_by('-recorded_date')
    
    def perform_create(self, serializer):
        school_id = getattr(self.request.user, 'school_id', None)
        if school_id:
            serializer.save(recorded_by=self.request.user, school_id=school_id)
        else:
            serializer.save(recorded_by=self.request.user)


class SchoolFeesViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolFeesSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        try:
            school_id = get_school_filter(self.request.user)
            
            # Students can only see their own fees
            if self.request.user.role == 'student':
                if school_id:
                    return SchoolFees.objects.filter(student=self.request.user, school_id=school_id).order_by('-due_date')
                return SchoolFees.objects.filter(student=self.request.user).order_by('-due_date')
            
            if school_id:
                return SchoolFees.objects.filter(school_id=school_id).order_by('-due_date')
            return SchoolFees.objects.all().order_by('-due_date')
        except Exception as e:
            print(f"[v0] Error in SchoolFeesViewSet.get_queryset: {e}")
            if self.request.user.role == 'student':
                return SchoolFees.objects.filter(student=self.request.user).order_by('-due_date')
            return SchoolFees.objects.all().order_by('-due_date')
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]


class SchoolEventViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolEventSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        try:
            school_id = get_school_filter(self.request.user)
            if school_id:
                return SchoolEvent.objects.filter(school_id=school_id).order_by('-event_date')
            return SchoolEvent.objects.all().order_by('-event_date')
        except Exception as e:
            print(f"[v0] Error in SchoolEventViewSet.get_queryset: {e}")
            return SchoolEvent.objects.all().order_by('-event_date')
    
    def perform_create(self, serializer):
        school_id = getattr(self.request.user, 'school_id', None)
        if school_id:
            serializer.save(created_by=self.request.user, school_id=school_id)
        else:
            serializer.save(created_by=self.request.user)


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        try:
            school_id = get_school_filter(self.request.user)
            if school_id:
                return Document.objects.filter(school_id=school_id).order_by('-created_at')
            return Document.objects.all().order_by('-created_at')
        except Exception as e:
            print(f"[v0] Error in DocumentViewSet.get_queryset: {e}")
            return Document.objects.all().order_by('-created_at')
    
    def perform_create(self, serializer):
        user = self.request.user
        school_id = getattr(user, 'school_id', None)

        if user.role == 'teacher' and not school_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Your account is not associated with a school. Please contact an administrator to be assigned to a school before uploading materials.")

        if school_id:
            serializer.save(uploaded_by=user, school_id=school_id)
        elif user.role != 'teacher': # Allow super_admin to create without school_id
            serializer.save(uploaded_by=user)
        else:
            # This case should be blocked by the check above, but as a safeguard:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have permission to create a document without a school.")
    
    @action(detail=False, methods=['post'])
    def generate_questions_from_topic(self, request):
        """Generate exam questions from a topic without needing a document"""
        try:
            print(f"[v0] Starting generate_questions_from_topic")
            print(f"[v0] Request data: {request.data}")
            print(f"[v0] Request user: {request.user}")
            
            topic = request.data.get('topic', '').strip()
            subject = request.data.get('subject', '').strip()
            num_questions = int(request.data.get('num_questions', 5))
            question_type = request.data.get('question_type', 'multiple_choice')
            difficulty = request.data.get('difficulty', 'medium')
            
            print(f"[v0] Parsed parameters - topic: {topic}, subject: {subject}, num_questions: {num_questions}")
            
            # Validate parameters
            if not topic:
                return Response(
                    {'error': 'Topic is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if num_questions < 1 or num_questions > 20:
                return Response(
                    {'error': 'Number of questions must be between 1 and 20'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if question_type not in ['multiple_choice', 'short_answer', 'essay']:
                return Response(
                    {'error': 'Invalid question type'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get school name for AI naming
            school_name = getattr(request.user, 'school', None)
            school_name_str = school_name.name if school_name else "School"
            print(f"[v0] School name: {school_name_str}")
            
            # Import AI service
            from apps.academics.ai_service import generate_school_ai_questions
            
            # Generate questions from topic
            material_content = f"Topic: {topic}"
            if subject:
                material_content += f"\nSubject: {subject}"
            
            print(f"[v0] Calling AI service with content: {material_content}")
            
            result = generate_school_ai_questions(
                school_name=school_name_str,
                material_content=material_content,
                num_questions=num_questions,
                question_type=question_type,
                difficulty=difficulty,
                subject=subject
            )
            
            print(f"[v0] AI service result: {result}")
            
            if result and 'error' not in result:
                return Response(result, status=status.HTTP_200_OK)
            else:
                error_msg = result.get('error', 'Failed to generate questions') if result else 'Failed to generate questions'
                return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            import traceback
            print(f"[v0] Error generating questions from topic: {str(e)}")
            traceback.print_exc()
            return Response(
                {'error': f'Failed to generate questions: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def share_with_classes(self, request, pk=None):
        """Share a document with specific classes"""
        try:
            document = self.get_object()
            class_ids = request.data.get('class_ids', [])
            
            if not class_ids:
                return Response(
                    {'error': 'At least one class must be selected'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate that all classes belong to the same school
            from apps.academics.models import Class
            classes = Class.objects.filter(id__in=class_ids, school=document.school)
            
            if len(classes) != len(class_ids):
                return Response(
                    {'error': 'Invalid class selection'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Add classes to the shared_with_classes relationship
            document.shared_with_classes.set(classes)
            document.is_shared = True
            document.save()
            
            return Response({
                'success': True,
                'message': f'Document shared with {len(classes)} class(es)',
                'shared_with_classes': list(classes.values_list('id', 'name'))
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"[v0] Error sharing document: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed to share document: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def unshare_from_classes(self, request, pk=None):
        """Remove document from classes"""
        try:
            document = self.get_object()
            class_ids = request.data.get('class_ids', [])
            
            if not class_ids:
                # Clear all classes if none specified
                document.shared_with_classes.clear()
                document.is_shared = False
                document.save()
                return Response({
                    'success': True,
                    'message': 'Document unshared from all classes'
                }, status=status.HTTP_200_OK)
            
            # Remove specific classes
            document.shared_with_classes.remove(*class_ids)
            
            if document.shared_with_classes.count() == 0:
                document.is_shared = False
            
            document.save()
            
            return Response({
                'success': True,
                'message': f'Document unshared from {len(class_ids)} class(es)'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"[v0] Error unsharing document: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed to unshare document: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        """Generate exam questions from a learning material using AI"""
        try:
            document = self.get_object()
            
            # Get request parameters
            num_questions = int(request.data.get('num_questions', 5))
            question_type = request.data.get('question_type', 'multiple_choice')
            difficulty = request.data.get('difficulty', 'medium')
            
            # Validate parameters
            if num_questions < 1 or num_questions > 20:
                return Response(
                    {'error': 'Number of questions must be between 1 and 20'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if question_type not in ['multiple_choice', 'short_answer', 'essay']:
                return Response(
                    {'error': 'Invalid question type'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get school name for AI naming
            school_name = getattr(request.user, 'school', None)
            school_name_str = school_name.name if school_name else "School"
            
            # Import AI service
            from apps.academics.ai_service import generate_school_ai_questions
            
            # Generate questions from document title and description
            material_content = f"Title: {document.title}\n\nDescription: {document.description}"
            
            result = generate_school_ai_questions(
                school_name=school_name_str,
                material_content=material_content,
                num_questions=num_questions,
                question_type=question_type,
                difficulty=difficulty,
                subject=document.subject.name if document.subject else ""
            )
            
            if result and 'error' not in result:
                return Response(result, status=status.HTTP_200_OK)
            else:
                error_msg = result.get('error', 'Failed to generate questions') if result else 'Failed to generate questions'
                return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            import traceback
            print(f"[v0] Error generating questions: {str(e)}")
            traceback.print_exc()
            return Response(
                {'error': f'Failed to generate questions: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DocumentFolderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing document folders"""
    serializer_class = DocumentFolderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Only show folders for the current teacher"""
        return DocumentFolder.objects.filter(teacher=self.request.user)
    
    def perform_create(self, serializer):
        """Create folder for the current teacher"""
        serializer.save(teacher=self.request.user, school=self.request.user.school)


class NoticeViewSet(viewsets.ModelViewSet):
    serializer_class = NoticeSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        try:
            school_id = get_school_filter(self.request.user)
            if school_id:
                return Notice.objects.filter(school_id=school_id, is_active=True).order_by('-created_at')
            return Notice.objects.filter(is_active=True).order_by('-created_at')
        except Exception as e:
            print(f"[v0] Error in NoticeViewSet.get_queryset: {e}")
            return Notice.objects.filter(is_active=True).order_by('-created_at')
    
    def perform_create(self, serializer):
        school_id = getattr(self.request.user, 'school_id', None)
        if school_id:
            serializer.save(posted_by=self.request.user, school_id=school_id)
        else:
            serializer.save(posted_by=self.request.user)


class UserProfilePictureViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfilePictureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        school_id = get_school_filter(self.request.user)

        # Base queryset scoped to the school
        if school_id is None:
            qs = UserProfilePicture.objects.all()
        else:
            qs = UserProfilePicture.objects.filter(user__school_id=school_id)

        # Allow filtering by a specific user via ?user=<id>
        user_id = self.request.query_params.get('user')
        if user_id:
            try:
                qs = qs.filter(user_id=int(user_id))
            except (ValueError, TypeError):
                pass

        return qs

    def _resolve_target_user(self):
        """
        Return the User instance the picture belongs to.
        School/super admins may pass a 'user' id in the request body to
        upload on behalf of another user; everyone else gets their own account.
        """
        if self.request.user.role in ('school_admin', 'super_admin'):
            user_id = self.request.data.get('user')
            if user_id:
                from apps.users.models import User as UserModel
                try:
                    return UserModel.objects.get(id=user_id)
                except UserModel.DoesNotExist:
                    pass
        return self.request.user

    def _upload_to_supabase(self, file_obj, user):
        """
        Upload profile picture to Supabase Storage.
        Returns (storage_path, storage_url, file_size, content_type)
        """
        try:
            from apps.storage.supabase_service import SupabaseStorageService
            
            # Determine folder based on user role
            role_folder = user.role if user.role in ('student', 'teacher', 'school_admin') else 'other'
            
            # Create unique filename
            import uuid
            from datetime import datetime
            file_ext = '.jpg'
            if file_obj.name:
                import os
                file_ext = os.path.splitext(file_obj.name)[1] or '.jpg'
            
            filename = f"{role_folder}/{user.id}/avatar_{datetime.now().timestamp()}{file_ext}"
            
            # Initialize Supabase service
            supabase_service = SupabaseStorageService()
            
            # Upload to Supabase
            storage_path, storage_url = supabase_service.upload_profile_picture(
                file_obj=file_obj,
                user_id=user.id,
                user_name=user.get_full_name() or user.username
            )
            
            # Get file size and content type
            file_obj.seek(0, 2)  # Seek to end
            file_size = file_obj.tell()
            file_obj.seek(0)  # Reset to beginning
            
            content_type = file_obj.content_type if hasattr(file_obj, 'content_type') else 'image/jpeg'
            
            return storage_path, storage_url, file_size, content_type
            
        except Exception as e:
            print(f"[ProfilePicture] Supabase upload error: {str(e)}")
            raise Exception(f"Failed to upload to Supabase: {str(e)}")

    def create(self, request, *args, **kwargs):
        """
        Upsert behaviour: if the target user already has a profile picture
        record, update it in-place instead of trying to INSERT a duplicate
        (which would hit the OneToOneField unique constraint and return 400).
        
        Now also uploads to Supabase Storage.
        """
        target_user = self._resolve_target_user()
        
        # Check if picture file was uploaded
        picture_file = request.FILES.get('picture')
        
        storage_path = None
        storage_url = None
        file_size = None
        content_type = None
        
        # Upload to Supabase if file provided
        if picture_file:
            try:
                storage_path, storage_url, file_size, content_type = self._upload_to_supabase(picture_file, target_user)
            except Exception as e:
                return Response(
                    {'error': f'Failed to upload picture: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        try:
            existing = UserProfilePicture.objects.get(user=target_user)
            
            # --- UPDATE path ---
            update_data = {}
            if picture_file:
                update_data['storage_path'] = storage_path
                update_data['storage_url'] = storage_url
                update_data['file_size'] = file_size
                update_data['content_type'] = content_type
            
            serializer = self.get_serializer(existing, data=update_data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except UserProfilePicture.DoesNotExist:
            # --- CREATE path ---
            if not picture_file:
                return Response(
                    {'error': 'No picture file provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            create_data = {
                'storage_path': storage_path,
                'storage_url': storage_url,
                'file_size': file_size,
                'content_type': content_type,
            }
            serializer = self.get_serializer(data=create_data)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=target_user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        # Fallback used only when create() is not overridden (e.g. tests).
        serializer.save(user=self._resolve_target_user())


class ClassTeacherViewSet(viewsets.ModelViewSet):
    serializer_class = ClassTeacherSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return ClassTeacher.objects.all()
        return ClassTeacher.objects.filter(class_obj__school_id=school_id)
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def create(self, request, *args, **kwargs):
        try:
            print(f"[v0] ClassTeacherViewSet.create - data: {request.data}")
            return super().create(request, *args, **kwargs)
        except Exception as e:
            print(f"[v0] ClassTeacherViewSet.create - error: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def perform_create(self, serializer):
        try:
            serializer.save()
        except Exception as e:
            print(f"[v0] ClassTeacherViewSet.perform_create - error: {str(e)}")
            raise


class StudentClassViewSet(viewsets.ModelViewSet):
    serializer_class = StudentClassSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        
        # Students can only see their own class assignments
        if self.request.user.role == 'student':
            if school_id:
                return StudentClass.objects.filter(student=self.request.user, class_obj__school_id=school_id)
            return StudentClass.objects.filter(student=self.request.user)
        
        # Teachers can see classes they manage
        if self.request.user.role == 'teacher':
            if school_id:
                return StudentClass.objects.filter(class_obj__teachers__teacher=self.request.user, class_obj__school_id=school_id)
            return StudentClass.objects.filter(class_obj__teachers__teacher=self.request.user)
        
        # Admins see all
        if school_id:
            return StudentClass.objects.filter(class_obj__school_id=school_id)
        return StudentClass.objects.all()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def create(self, request, *args, **kwargs):
        try:
            print(f"[v0] StudentClassViewSet.create - data: {request.data}")
            return super().create(request, *args, **kwargs)
        except Exception as e:
            print(f"[v0] StudentClassViewSet.create - error: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def perform_create(self, serializer):
        try:
            serializer.save()
        except Exception as e:
            print(f"[v0] StudentClassViewSet.perform_create - error: {str(e)}")
            raise


class ClassSubjectTeacherViewSet(viewsets.ModelViewSet):
    serializer_class = ClassSubjectTeacherSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        
        print(f"[TeacherGrading] User: {self.request.user}, role: {self.request.user.role}, school_id: {school_id}")

        # Teachers can see their own subject assignments
        if self.request.user.role == 'teacher':
            if school_id:
                # Get ClassSubjectTeacher assignments
                subject_teacher_qs = ClassSubjectTeacher.objects.filter(
                    teacher=self.request.user, 
                    class_obj__school_id=school_id
                )
                # Also get classes where teacher is a ClassTeacher (form tutor)
                class_teacher_qs = ClassTeacher.objects.filter(
                    teacher=self.request.user,
                    class_obj__school_id=school_id
                )
            else:
                subject_teacher_qs = ClassSubjectTeacher.objects.filter(
                    teacher=self.request.user
                )
                class_teacher_qs = ClassTeacher.objects.filter(
                    teacher=self.request.user
                )
            
            # Combine both querysets - get unique class_obj IDs
            class_ids = set()
            for st in subject_teacher_qs:
                class_ids.add(st.class_obj_id)
            for ct in class_teacher_qs:
                class_ids.add(ct.class_obj_id)
            
            # Return ClassSubjectTeacher records for all these classes
            queryset = ClassSubjectTeacher.objects.filter(
                class_obj_id__in=class_ids
            )
            
            print(f"[TeacherGrading] Teacher subject assignments: {subject_teacher_qs.count()}, class teacher assignments: {class_teacher_qs.count()}, combined class_ids: {class_ids}")
            return queryset

        if school_id:
            return ClassSubjectTeacher.objects.filter(class_obj__school_id=school_id)
        return ClassSubjectTeacher.objects.all()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def create(self, request, *args, **kwargs):
        try:
            print(f"[v0] ClassSubjectTeacherViewSet.create - data: {request.data}")
            return super().create(request, *args, **kwargs)
        except Exception as e:
            print(f"[v0] ClassSubjectTeacherViewSet.create - error: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def perform_create(self, serializer):
        try:
            serializer.save()
        except Exception as e:
            print(f"[v0] ClassSubjectTeacherViewSet.perform_create - error: {str(e)}")
            raise


# ==================== GRADING SYSTEM - TERMINAL REPORTS VIEWSETS ====================

class GradingPolicyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing grading policies (weightage for assessment types)"""
    serializer_class = GradingPolicySerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return GradingPolicy.objects.all()
        return GradingPolicy.objects.filter(school_id=school_id)
    
    def perform_create(self, serializer):
        school_id = getattr(self.request.user, 'school_id', None)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()
    
    @action(detail=False, methods=['get'])
    def by_session(self, request):
        """Get grading policies for a specific session"""
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({'error': 'session_id is required'}, status=400)
        
        school_id = get_school_filter(request.user)
        policies = GradingPolicy.objects.filter(academic_session_id=session_id)
        if school_id:
            policies = policies.filter(school_id=school_id)
        
        return Response(GradingPolicySerializer(policies, many=True).data)
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Bulk create grading policies for a session"""
        try:
            policies_data = request.data.get('policies', [])
            session_id = request.data.get('session_id')
            
            if not session_id:
                return Response({'error': 'session_id is required'}, status=400)
            
            if not policies_data:
                return Response({'error': 'No policies provided'}, status=400)
            
            school_id = getattr(request.user, 'school_id', None)
            if not school_id:
                return Response({'error': 'School not found'}, status=400)
            
            created_policies = []
            for policy_data in policies_data:
                policy, created = GradingPolicy.objects.update_or_create(
                    school_id=school_id,
                    academic_session_id=session_id,
                    assessment_type=policy_data.get('assessment_type'),
                    defaults={
                        'name': policy_data.get('name', 'Default Grading Policy'),
                        'weightage': policy_data.get('weightage', 0),
                        'is_active': policy_data.get('is_active', True),
                    }
                )
                created_policies.append({
                    'id': policy.id,
                    'assessment_type': policy.assessment_type,
                    'weightage': policy.weightage,
                    'created': created,
                })
            
            return Response({
                'success': True,
                'message': f'{len(created_policies)} policies saved',
                'policies': created_policies,
            })
            
        except Exception as e:
            import traceback
            print(f"[v0] Error bulk creating grading policies: {str(e)}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=500)


class AcademicSessionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing academic sessions/terms"""
    serializer_class = AcademicSessionSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        if school_id is None:
            return AcademicSession.objects.all()
        return AcademicSession.objects.filter(school_id=school_id)
    
    def perform_create(self, serializer):
        school_id = getattr(self.request.user, 'school_id', None)
        if school_id:
            serializer.save(school_id=school_id)
        else:
            serializer.save()
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get the current academic session"""
        school_id = get_school_filter(request.user)
        if school_id:
            session = AcademicSession.objects.filter(school_id=school_id, is_current=True).first()
        else:
            session = AcademicSession.objects.filter(is_current=True).first()
        
        if session:
            return Response(AcademicSessionSerializer(session).data)
        return Response({'error': 'No current session found'}, status=404)


class TerminalReportViewSet(viewsets.ModelViewSet):
    """ViewSet for managing terminal reports"""
    serializer_class = TerminalReportSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrTeacher()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        school_id = get_school_filter(self.request.user)
        
        # Students can see their own terminal reports
        if self.request.user.role == 'student':
            if school_id:
                return TerminalReport.objects.filter(student=self.request.user, school_id=school_id)
            return TerminalReport.objects.filter(student=self.request.user)
        
        # Teachers can see reports for their classes
        if self.request.user.role == 'teacher':
            if school_id:
                return TerminalReport.objects.filter(class_obj__teachers__teacher=self.request.user, school_id=school_id).distinct()
            return TerminalReport.objects.filter(class_obj__teachers__teacher=self.request.user).distinct()
        
        # Admins see all
        if school_id:
            return TerminalReport.objects.filter(school_id=school_id)
        return TerminalReport.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return TerminalReportListSerializer
        return TerminalReportSerializer
    
    def perform_create(self, serializer):
        school_id = getattr(self.request.user, 'school_id', None)
        if school_id:
            serializer.save(school_id=school_id, generated_by=self.request.user)
        else:
            serializer.save(generated_by=self.request.user)
    
    @action(detail=False, methods=['post'])
    def generate_report(self, request):
        """Generate a terminal report for a student using grading policy weightage"""
        try:
            student_id = request.data.get('student_id')
            class_id = request.data.get('class_id')
            session_id = request.data.get('session_id')
            use_weighted = request.data.get('use_weighted', True)  # Use grading policy by default
            
            if not all([student_id, class_id, session_id]):
                return Response({'error': 'student_id, class_id, and session_id are required'}, status=400)
            
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            student = User.objects.get(id=student_id)
            class_obj = Class.objects.get(id=class_id)
            session = AcademicSession.objects.get(id=session_id)
            
            # Get all subjects for the class
            subjects = Subject.objects.filter(
                classsubject__class_obj=class_obj
            ).distinct()
            
            # Get grading policies for this session
            grading_policies = GradingPolicy.objects.filter(
                academic_session=session,
                is_active=True
            )
            
            # Get locked grades for this student in this class/session
            from apps.students.models import Grade
            grades = Grade.objects.filter(
                student=student,
                subject__in=subjects,
                academic_session=session,
                is_locked=True
            )
            
            # Calculate total and average
            total_marks = 0
            subject_count = 0
            subject_scores = []
            
            for subject in subjects:
                subject_grades = grades.filter(subject=subject)
                
                if subject_grades.exists():
                    if use_weighted and grading_policies.exists():
                        # Calculate weighted percentage
                        weighted_percentage = 0
                        total_weight = 0
                        
                        for policy in grading_policies:
                            weight = policy.weightage
                            type_grades = subject_grades.filter(assessment_type=policy.assessment_type)
                            
                            if type_grades.exists():
                                avg_percentage = type_grades.aggregate(avg=models.Avg('percentage'))['avg'] or 0
                                weighted_percentage += avg_percentage * (weight / 100)
                                total_weight += weight
                        
                        if total_weight > 0:
                            # Normalize to 100
                            display_percentage = (weighted_percentage / total_weight) * 100
                        else:
                            display_percentage = subject_grades.aggregate(avg=models.Avg('percentage'))['avg'] or 0
                    else:
                        # Simple average (old behavior)
                        display_percentage = subject_grades.aggregate(avg=models.Avg('percentage'))['avg'] or 0
                    
                    total_marks += display_percentage
                    subject_count += 1
                    
                    # Calculate grade
                    if display_percentage >= 90:
                        grade = 'A'
                    elif display_percentage >= 80:
                        grade = 'B'
                    elif display_percentage >= 70:
                        grade = 'C'
                    elif display_percentage >= 60:
                        grade = 'D'
                    else:
                        grade = 'F'
                    
                    subject_scores.append({
                        'subject': subject,
                        'percentage': display_percentage,
                        'grade': grade,
                        'use_weighted': use_weighted and grading_policies.exists(),
                    })
            
            average_marks = total_marks / subject_count if subject_count > 0 else 0
            
            # Get attendance data
            from apps.attendance.models import Attendance
            total_days = Attendance.objects.filter(
                student=student,
                date__gte=session.start_date,
                date__lte=session.end_date
            ).count()
            days_present = Attendance.objects.filter(
                student=student,
                date__gte=session.start_date,
                date__lte=session.end_date,
                status='present'
            ).count()
            attendance_percentage = (days_present / total_days * 100) if total_days > 0 else 0
            
            # Calculate overall grade
            if average_marks >= 90:
                overall_grade = 'A'
            elif average_marks >= 80:
                overall_grade = 'B'
            elif average_marks >= 70:
                overall_grade = 'C'
            elif average_marks >= 60:
                overall_grade = 'D'
            else:
                overall_grade = 'F'
            
            # Create or update terminal report
            terminal_report, created = TerminalReport.objects.update_or_create(
                student=student,
                class_obj=class_obj,
                academic_session=session,
                defaults={
                    'school_id': getattr(request.user, 'school_id', None),
                    'total_marks': total_marks,
                    'average_marks': average_marks,
                    'total_days': total_days,
                    'days_present': days_present,
                    'attendance_percentage': attendance_percentage,
                    'grade': overall_grade,
                    'status': 'draft',
                    'generated_by': request.user,
                }
            )
            
            # Create subject scores
            for score_data in subject_scores:
                SubjectScore.objects.update_or_create(
                    terminal_report=terminal_report,
                    subject=score_data['subject'],
                    defaults={
                        'percentage': score_data['percentage'],
                        'total_score': score_data['percentage'],
                        'grade': score_data['grade'],
                        'use_grading_policy': score_data['use_weighted'],
                    }
                )
            
            return Response(TerminalReportSerializer(terminal_report).data, status=201 if created else 200)
            
        except Exception as e:
            import traceback
            print(f"[v0] Error generating terminal report: {str(e)}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=500)
    
    @action(detail=False, methods=['post'])
    def calculate_positions(self, request):
        """Calculate positions for all students in a class for a given session"""
        try:
            class_id = request.data.get('class_id')
            session_id = request.data.get('session_id')
            
            if not all([class_id, session_id]):
                return Response({'error': 'class_id and session_id are required'}, status=400)
            
            # Get all terminal reports for this class and session
            reports = TerminalReport.objects.filter(
                class_obj_id=class_id,
                academic_session_id=session_id
            ).order_by('-average_marks')
            
            total_students = reports.count()
            position = 1
            
            for report in reports:
                report.position = position
                report.total_students = total_students
                report.save()
                position += 1
            
            return Response({
                'success': True,
                'message': f'Positions calculated for {total_students} students'
            })
            
        except Exception as e:
            import traceback
            print(f"[v0] Error calculating positions: {str(e)}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=500)
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish a terminal report"""
        report = self.get_object()
        report.status = 'published'
        report.save()
        return Response(TerminalReportSerializer(report).data)
    
    @action(detail=True, methods=['post'])
    def add_remarks(self, request, pk=None):
        """Add remarks to a terminal report"""
        report = self.get_object()
        report.form_teacher_remarks = request.data.get('form_teacher_remarks', '')
        report.principal_remarks = request.data.get('principal_remarks', '')
        report.save()
        return Response(TerminalReportSerializer(report).data)
