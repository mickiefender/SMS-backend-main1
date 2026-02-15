from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsSchoolAdminOrHigher, IsSchoolAdminOrTeacher
from apps.academics.models import (
    Faculty, Department, Level, Subject, Class,
    ClassSubject, Enrollment, Timetable, AcademicCalendarEvent,
    Exam, ExamResult, SchoolFees, SchoolEvent, Document, DocumentFolder, Notice, UserProfilePicture,
    ClassTeacher, StudentClass, ClassSubjectTeacher
)
from apps.academics.serializers import (
    FacultySerializer, DepartmentSerializer, LevelSerializer,
    SubjectSerializer, ClassSerializer, ClassSubjectSerializer,
    EnrollmentSerializer, TimetableSerializer, AcademicCalendarEventSerializer,
    ExamSerializer, ExamResultSerializer, SchoolFeesSerializer,
    SchoolEventSerializer, DocumentSerializer, DocumentFolderSerializer, NoticeSerializer, UserProfilePictureSerializer,
    ClassTeacherSerializer, StudentClassSerializer, ClassSubjectTeacherSerializer
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
        if school_id is None:
            return UserProfilePicture.objects.all()
        return UserProfilePicture.objects.filter(user__school_id=school_id)
    
    def perform_create(self, serializer):
        # Users can only upload their own profile pictures, admins can upload for others
        if self.request.user.role == 'school_admin':
            serializer.save()
        else:
            serializer.save(user=self.request.user)


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
        
        # Teachers can see their own subject assignments
        if self.request.user.role == 'teacher':
            if school_id:
                return ClassSubjectTeacher.objects.filter(teacher=self.request.user, class_obj__school_id=school_id)
            return ClassSubjectTeacher.objects.filter(teacher=self.request.user)
        
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
