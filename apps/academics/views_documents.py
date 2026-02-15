"""
ViewSets for Document and DocumentFolder management
Allows teachers to create folders and upload learning materials
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth import get_user_model
from apps.academics.models import Document, DocumentFolder
from apps.academics.serializers_documents import DocumentSerializer, DocumentFolderSerializer
from core.permissions import IsTeacher, IsSchoolAdminOrTeacher

User = get_user_model()


class DocumentFolderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing document folders.
    Teachers can create folders to organize their learning materials.
    """
    serializer_class = DocumentFolderSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    
    def get_queryset(self):
        """
        Filter folders by school and teacher.
        Teachers see only their own folders and school admin sees all.
        """
        user = self.request.user
        
        if not user.is_authenticated:
            return DocumentFolder.objects.none()
        
        # Check user role
        user_role = getattr(user, 'role', None)
        
        # Admin can see all folders in their school
        if user_role in ['school_admin', 'super_admin']:
            if hasattr(user, 'school') and user.school:
                return DocumentFolder.objects.filter(school=user.school)
            return DocumentFolder.objects.all()
        
        # Teachers see only their own folders
        if user_role == 'teacher':
            if hasattr(user, 'school') and user.school:
                return DocumentFolder.objects.filter(school=user.school, teacher=user)
            return DocumentFolder.objects.filter(teacher=user)
        
        return DocumentFolder.objects.none()
    
    def get_permissions(self):
        """
        Create, update, delete: requires IsTeacher or IsSchoolAdminOrTeacher
        List, retrieve: requires IsAuthenticated
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsTeacher | IsSchoolAdminOrTeacher]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """
        Create a folder for the current teacher.
        Sets school and teacher automatically.
        """
        serializer.save(
            school=self.request.user.school,
            teacher=self.request.user
        )
    
    @action(detail=True, methods=['get'])
    def children(self, request, pk=None):
        """Get all subfolders and documents in this folder"""
        folder = self.get_object()
        
        # Get child folders
        child_folders = DocumentFolder.objects.filter(parent_folder=folder)
        folder_serializer = DocumentFolderSerializer(child_folders, many=True)
        
        # Get documents in this folder
        documents = Document.objects.filter(folder=folder)
        document_serializer = DocumentSerializer(documents, many=True)
        
        return Response({
            'folders': folder_serializer.data,
            'documents': document_serializer.data,
            'total_items': len(child_folders) + len(documents)
        })
    
    @action(detail=True, methods=['get'])
    def breadcrumb(self, request, pk=None):
        """Get breadcrumb path from root to this folder"""
        folder = self.get_object()
        breadcrumb = []
        current = folder
        
        while current:
            breadcrumb.insert(0, {
                'id': current.id,
                'name': current.name
            })
            current = current.parent_folder
        
        return Response({'breadcrumb': breadcrumb})


class DocumentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing documents (learning materials).
    Teachers can upload files and organize them in folders.
    """
    serializer_class = DocumentSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    
    def get_queryset(self):
        """
        Filter documents by school and user.
        Teachers see only documents they uploaded or that are shared with their class.
        Students see documents related to their classes.
        """
        user = self.request.user
        
        if not user.is_authenticated:
            return Document.objects.none()
        
        # Check user role
        user_role = getattr(user, 'role', None)
        
        # Admin can see all documents in their school
        if user_role in ['school_admin', 'super_admin']:
            if hasattr(user, 'school') and user.school:
                return Document.objects.filter(school=user.school)
            return Document.objects.all()
        
        # Teachers see their own documents
        if user_role == 'teacher':
            if hasattr(user, 'school') and user.school:
                return Document.objects.filter(
                    Q(school=user.school) & Q(uploaded_by=user)
                )
            return Document.objects.filter(uploaded_by=user)
        
        # Students see documents for their classes
        if user_role == 'student':
            if hasattr(user, 'school') and user.school:
                return Document.objects.filter(
                    Q(school=user.school) & Q(related_class__in=user.classes.all())
                )
            return Document.objects.none()
        
        return Document.objects.none()
    
    def get_permissions(self):
        """
        Create, update, delete: requires IsTeacher or IsSchoolAdminOrTeacher
        List, retrieve: requires IsAuthenticated
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsTeacher | IsSchoolAdminOrTeacher]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """
        Create a document for the current teacher.
        Sets school and uploaded_by automatically.
        """
        serializer.save(
            school=self.request.user.school,
            uploaded_by=self.request.user
        )
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Download a document file.
        Returns file URL or file content depending on configuration.
        """
        document = self.get_object()
        
        # Check permissions
        if request.user.is_authenticated:
            if hasattr(request.user, 'is_teacher') and request.user.is_teacher:
                if document.uploaded_by != request.user and not hasattr(request.user, 'is_admin'):
                    return Response(
                        {'error': 'You do not have permission to download this file'},
                        status=status.HTTP_403_FORBIDDEN
                    )
        else:
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        return Response({
            'file_url': request.build_absolute_uri(document.file.url),
            'filename': document.file.name,
            'title': document.title,
            'file_size': document.file.size if document.file else 0
        })
    
    @action(detail=False, methods=['get'])
    def by_folder(self, request):
        """Get documents filtered by folder"""
        folder_id = request.query_params.get('folder_id')
        
        if not folder_id:
            return Response(
                {'error': 'folder_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        folder = get_object_or_404(DocumentFolder, id=folder_id)
        
        # Check permission
        if folder.teacher != request.user and not hasattr(request.user, 'is_admin'):
            return Response(
                {'error': 'You do not have permission to view this folder'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        documents = Document.objects.filter(folder=folder)
        serializer = DocumentSerializer(documents, many=True)
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """Delete multiple documents at once"""
        document_ids = request.data.get('document_ids', [])
        
        if not document_ids:
            return Response(
                {'error': 'document_ids list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        documents = Document.objects.filter(id__in=document_ids, uploaded_by=request.user)
        count = documents.count()
        documents.delete()
        
        return Response({
            'message': f'Successfully deleted {count} documents',
            'deleted_count': count
        })
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search documents by title or description"""
        query = request.query_params.get('q', '')
        
        if len(query) < 2:
            return Response(
                {'error': 'Search query must be at least 2 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        documents = self.get_queryset().filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
        
        serializer = DocumentSerializer(documents, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['patch'])
    def move_to_folder(self, request, pk=None):
        """Move a document to a different folder"""
        document = self.get_object()
        folder_id = request.data.get('folder_id')
        
        if not folder_id:
            return Response(
                {'error': 'folder_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        folder = get_object_or_404(DocumentFolder, id=folder_id)
        
        # Verify folder belongs to the same teacher
        if folder.teacher != request.user:
            return Response(
                {'error': 'You can only move documents to your own folders'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        document.folder = folder
        document.save()
        
        return Response({
            'message': 'Document moved successfully',
            'document': DocumentSerializer(document).data
        })
    
    @action(detail=True, methods=['post'])
    def share_with_classes(self, request, pk=None):
        """Share a document with specific classes"""
        document = self.get_object()
        class_ids = request.data.get('class_ids', [])
        
        if not class_ids:
            return Response(
                {'error': 'class_ids list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify document belongs to the teacher
        if document.uploaded_by != request.user and not hasattr(request.user, 'is_admin'):
            return Response(
                {'error': 'You can only share your own documents'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Import Class model
        from apps.academics.models import Class
        
        # Clear existing shared classes and add new ones
        document.shared_with_classes.clear()
        for class_id in class_ids:
            try:
                class_obj = Class.objects.get(id=class_id, school=request.user.school)
                document.shared_with_classes.add(class_obj)
            except Class.DoesNotExist:
                pass
        
        document.is_shared = len(class_ids) > 0
        document.save()
        
        return Response({
            'message': f'Document shared with {len(class_ids)} class(es)',
            'document': DocumentSerializer(document, context={'request': request}).data,
            'shared_classes': [{'id': c.id, 'name': c.name} for c in document.shared_with_classes.all()]
        })
    
    @action(detail=True, methods=['get'])
    def shared_classes(self, request, pk=None):
        """Get list of classes this document is shared with"""
        document = self.get_object()
        
        classes = document.shared_with_classes.all()
        return Response({
            'document_id': document.id,
            'document_title': document.title,
            'is_shared': document.is_shared,
            'shared_classes': [{'id': c.id, 'name': c.name} for c in classes]
        })
    
    @action(detail=True, methods=['post'])
    def generate_questions(self, request, pk=None):
        """
        Generate AI questions from a document.
        This endpoint extracts text from the document and generates questions.
        URL: /documents/{id}/generate_questions/
        """
        document = self.get_object()
        
        num_questions = request.data.get('num_questions', 5)
        question_type = request.data.get('question_type', 'multiple_choice')
        difficulty = request.data.get('difficulty', 'medium')
        
        # Verify permission
        if document.uploaded_by != request.user and not hasattr(request.user, 'is_admin'):
            return Response(
                {'error': 'You do not have permission to generate questions from this document'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Extract text from document (simplified - in production, use proper text extraction)
        try:
            # For now, return a placeholder response
            # In production, you would:
            # 1. Download the file from storage
            # 2. Extract text using libraries like PyPDF2, python-docx, etc.
            # 3. Send text to AI service (OpenAI, etc.)
            # 4. Return generated questions
            
            # Placeholder response
            questions = []
            for i in range(int(num_questions)):
                if question_type == 'multiple_choice':
                    questions.append({
                        'question': f'Sample question {i+1} from {document.title}',
                        'options': ['Option A', 'Option B', 'Option C', 'Option D'],
                        'correct_answer': 'A',
                        'explanation': 'This is a sample explanation.'
                    })
                elif question_type == 'true_false':
                    questions.append({
                        'question': f'Sample true/false question {i+1} from {document.title}',
                        'correct_answer': 'True',
                        'explanation': 'This is a sample explanation.'
                    })
                else:  # short_answer
                    questions.append({
                        'question': f'Sample short answer question {i+1} from {document.title}',
                        'model_answer': 'This is a sample model answer.',
                        'explanation': 'This is a sample explanation.'
                    })
            
            return Response({
                'document_id': document.id,
                'document_title': document.title,
                'questions': questions,
                'metadata': {
                    'num_questions': len(questions),
                    'question_type': question_type,
                    'difficulty': difficulty,
                    'generated_at': 'now'
                }
            })
            
        except Exception as e:
            return Response(
                {'error': f'Failed to generate questions: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def generate_questions_from_topic(self, request):
        """
        Generate exam questions from a topic without needing a document.
        URL: /documents/generate_questions_from_topic/
        """
        try:
            print(f"[v0] Starting generate_questions_from_topic")
            print(f"[v0] Request data: {request.data}")
            
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
                subject=subject,
                is_topic=True
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
