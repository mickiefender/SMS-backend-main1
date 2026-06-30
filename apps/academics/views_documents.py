"""
ViewSets for Document and DocumentFolder management
Allows teachers to create folders and upload learning materials
"""
from datetime import timedelta
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
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
                from apps.academics.models import StudentClass
                student_class_ids = StudentClass.objects.filter(
                    student=user
                ).values_list('class_obj', flat=True)
                return Document.objects.filter(
                    Q(school=user.school) & (
                        Q(related_class__in=student_class_ids) |
                        Q(shared_with_classes__in=student_class_ids)
                    )
                ).distinct()
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
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get document statistics for the current user"""
        documents = self.get_queryset()
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)
        
        return Response({
            'total': documents.count(),
            'recent_uploads': documents.filter(created_at__gte=seven_days_ago).count(),
        })
    
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
        
        # Send email notifications
        if class_ids:
            try:
                from apps.academics.tasks import send_document_shared_email
                send_document_shared_email.delay(document.id, class_ids)
            except Exception:
                pass
        
            # Create in-app notifications for affected students
            try:
                from apps.academics.models import StudentClass
                students = StudentClass.objects.select_related('student').filter(
                    class_obj_id__in=class_ids,
                    is_active=True
                )
                from apps.messaging.models import PersonalNotice
                for sc in students:
                    PersonalNotice.objects.create(
                        school=request.user.school,
                        student=sc.student,
                        created_by=request.user,
                        title=f"New Material: {document.title}",
                        content=f"A new learning material \"{document.title}\" has been shared with your class by {document.uploaded_by.get_full_name() if document.uploaded_by else 'Teacher'}."
                    )
            except Exception as notify_err:
                print(f"Failed to create in-app notifications: {notify_err}")
        
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
        Downloads the file from Supabase storage, extracts text, and calls the AI service.
        URL: /documents/{id}/generate_questions/
        """
        document = self.get_object()

        num_questions = int(request.data.get('num_questions', 5))
        question_type = request.data.get('question_type', 'multiple_choice')
        difficulty = request.data.get('difficulty', 'medium')

        # Verify permission by role
        user_role = getattr(request.user, 'role', None)
        print(f"[DEBUG] User {request.user.email} (role: {user_role}) trying to generate questions from doc {document.id} (uploaded by {document.uploaded_by.email if document.uploaded_by else 'None'})")
        
        if user_role in ['super_admin', 'school_admin', 'teacher']:
            # Teachers/admins have full access
            pass
        elif user_role == 'student':
            # Students can access documents visible to them (already filtered by get_queryset)
            # Additional safety check for school match
            if not hasattr(request.user, 'school') or document.school != request.user.school:
                return Response(
                    {'error': 'You do not have permission to generate questions from this document'},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            return Response(
                {'error': 'You do not have permission to generate questions from this document'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            import io
            import requests as http_requests

            # ── 1. Resolve the file URL ──────────────────────────────────────
            file_url = None
            if document.file:
                # document.file may be a FieldFile or a plain string URL
                raw = str(document.file)
                if raw.startswith('http'):
                    file_url = raw
                else:
                    # Build absolute URL from the request
                    file_url = request.build_absolute_uri(document.file.url)

            if not file_url:
                return Response(
                    {'error': 'Document has no associated file.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Also add more logging for debugging
            print(f"[generate_questions] Raw file URL: {file_url}")
            print(f"[generate_questions] Document file field: {document.file}")
            print(f"[generate_questions] Document file type: {type(document.file)}")
            
            # Try to get filename from document.file.name if available
            if hasattr(document.file, 'name'):
                print(f"[generate_questions] document.file.name: {document.file.name}")
            
            # Also try to get filename from document title or file field
            # Sometimes the file URL doesn't have proper extension
            # Check if document.file.name has the extension
            db_filename = getattr(document.file, 'name', '') or ''
            print(f"[generate_questions] DB filename: {db_filename}")

            # ── 2. Download the file ─────────────────────────────────────────
            try:
                file_response = http_requests.get(file_url, timeout=30)
                file_response.raise_for_status()
                file_bytes = file_response.content
            except Exception as dl_err:
                print(f"[generate_questions] Download failed: {dl_err}")
                return Response(
                    {'error': f'Could not download document file: {str(dl_err)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ── 3. Extract text based on file type ───────────────────────────
            filename = file_url.split('?')[0].lower()   # strip query params
            
            # Also try to get filename from database if URL doesn't have extension
            db_filename = getattr(document.file, 'name', '') or ''
            
            # If filename from URL doesn't have proper extension, use database filename
            if db_filename and not any(filename.endswith(ext) for ext in ['.pdf', '.docx', '.doc', '.txt']):
                filename = db_filename.lower()
                print(f"[generate_questions] Using DB filename: {filename}")
            
            print(f"[generate_questions] Filename after processing: {filename}")
            
            # Try to detect MIME type from content if extension detection fails
            import mimetypes
            detected_mime = None
            try:
                # Read first bytes to detect MIME type
                import magic
                detected_mime = magic.from_buffer(file_bytes[:1024], mime=True)
                print(f"[generate_questions] Detected MIME type: {detected_mime}")
            except Exception as mime_err:
                print(f"[generate_questions] MIME detection error: {mime_err}")
            
            extracted_text = ""
            extraction_method = "none"

            # Check file extension - also check MIME type as fallback
            is_pdf = filename.endswith('.pdf') or detected_mime == 'application/pdf'
            is_docx = filename.endswith('.docx') or filename.endswith('.doc') or detected_mime in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']
            is_txt = filename.endswith('.txt') or detected_mime == 'text/plain' or detected_mime == 'application/text'
            
            print(f"[generate_questions] File detection - is_pdf: {is_pdf}, is_docx: {is_docx}, is_txt: {is_txt}, mime: {detected_mime}")

            if is_pdf:
                try:
                    # Try pymupdf first (better for both text and image-based PDFs)
                    try:
                        import fitz  # pymupdf
                        doc = fitz.open(stream=file_bytes, filetype="pdf")
                        pages_text = []
                        for page_num, page in enumerate(doc):
                            text = page.get_text()
                            if text and text.strip():
                                pages_text.append(text)
                            else:
                                # Page has no text, try to extract images for OCR
                                print(f"[generate_questions] Page {page_num + 1} has no extractable text, checking for images...")
                                try:
                                    import pytesseract
                                    from PIL import Image
                                    pix = page.get_pixmap(dpi=200)
                                    img_data = pix.tobytes("png")
                                    img = Image.open(io.BytesIO(img_data))
                                    ocr_text = pytesseract.image_to_string(img)
                                    if ocr_text and ocr_text.strip():
                                        pages_text.append(ocr_text)
                                        print(f"[generate_questions] OCR extracted {len(ocr_text)} chars from page {page_num + 1}")
                                except Exception as ocr_err:
                                    print(f"[generate_questions] OCR failed for page {page_num + 1}: {ocr_err}")
                        doc.close()
                        extracted_text = "\n".join(pages_text)
                        extraction_method = "pymupdf"
                        print(f"[generate_questions] pymupdf extracted {len(extracted_text)} chars from PDF")
                    except ImportError:
                        # Fallback to PyPDF2 if pymupdf not available
                        import PyPDF2
                        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                        pages_text = []
                        for page in pdf_reader.pages:
                            page_text = page.extract_text()
                            if page_text:
                                pages_text.append(page_text)
                        extracted_text = "\n".join(pages_text)
                        extraction_method = "pypdf2"
                        print(f"[generate_questions] PyPDF2 extracted {len(extracted_text)} chars from {len(pdf_reader.pages)} pages")
                except Exception as pdf_err:
                    print(f"[generate_questions] PDF extraction error: {pdf_err}")
                    extracted_text = ""

            elif filename.endswith('.docx'):
                try:
                    import docx
                    doc_obj = docx.Document(io.BytesIO(file_bytes))
                    extracted_text = "\n".join(
                        para.text for para in doc_obj.paragraphs if para.text.strip()
                    )
                    extraction_method = "python-docx"
                    print(f"[generate_questions] DOCX extracted {len(extracted_text)} chars")
                except Exception as docx_err:
                    print(f"[generate_questions] DOCX extraction error: {docx_err}")
                    extracted_text = ""

            elif filename.endswith('.txt'):
                try:
                    extracted_text = file_bytes.decode('utf-8', errors='ignore')
                    extraction_method = "plain-text"
                    print(f"[generate_questions] TXT extracted {len(extracted_text)} chars")
                except Exception as txt_err:
                    print(f"[generate_questions] TXT extraction error: {txt_err}")
                    extracted_text = ""

            else:
                # Attempt a plain UTF-8 decode as a last resort
                try:
                    extracted_text = file_bytes.decode('utf-8', errors='ignore')
                    extraction_method = "fallback-utf8"
                    print(f"[generate_questions] Unknown type — decoded {len(extracted_text)} chars")
                except Exception:
                    extracted_text = ""

            # ── 4. Validate extracted text ───────────────────────────────────
            print(f"[generate_questions] Extraction method: {extraction_method}, extracted length: {len(extracted_text)} chars")
            
            if not extracted_text or len(extracted_text.strip()) < 50:
                return Response(
                    {
                        'error': (
                            'Could not extract enough text from this document. '
                            'Please ensure the file is a readable PDF, DOCX, or TXT file '
                            'and is not password-protected or image-only. '
                            f'(Extraction method: {extraction_method})'
                        ),
                        'extraction_details': {
                            'method': extraction_method,
                            'chars_extracted': len(extracted_text),
                            'file_type': filename.split('.')[-1] if '.' in filename else 'unknown'
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Truncate to avoid exceeding token limits (~12 000 chars ≈ 3 000 tokens)
            material_content = extracted_text[:12000]

            # ── 5. Call the AI service ───────────────────────────────────────
            school_name = getattr(request.user, 'school', None)
            school_name_str = school_name.name if school_name else "School"

            from apps.academics.ai_service import generate_school_ai_questions

            subject = getattr(document, 'related_subject', None)
            subject_str = subject.name if subject and hasattr(subject, 'name') else ""

            print(f"[generate_questions] Calling AI for doc '{document.title}' — {num_questions} {question_type} questions")

            result = generate_school_ai_questions(
                school_name=school_name_str,
                material_content=material_content,
                num_questions=num_questions,
                question_type=question_type,
                difficulty=difficulty,
                subject=subject_str,
                is_topic=False
            )

            print(f"[generate_questions] AI result: {result}")

            if result and 'error' not in result:
                return Response(result, status=status.HTTP_200_OK)
            else:
                error_msg = result.get('error', 'Failed to generate questions') if result else 'Failed to generate questions'
                return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            import traceback
            print(f"[generate_questions] Unexpected error: {str(e)}")
            traceback.print_exc()
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
