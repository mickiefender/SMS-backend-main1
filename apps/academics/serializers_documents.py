"""
Enhanced serializers for Document and DocumentFolder with file upload support
"""
from rest_framework import serializers
from apps.academics.models import Document, DocumentFolder
from django.core.files.uploadedfile import UploadedFile


class DocumentFolderSerializer(serializers.ModelSerializer):
    """
    Serializer for document folders with nested folder support.
    Includes item count for UI display.
    """
    item_count = serializers.SerializerMethodField()
    subfolder_count = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()
    parent_folder_name = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    school = serializers.PrimaryKeyRelatedField(read_only=True)
    teacher = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = DocumentFolder
        fields = [
            'id', 'school', 'teacher', 'teacher_name', 'name', 'description',
            'parent_folder', 'parent_folder_name', 'item_count', 'subfolder_count',
            'document_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_item_count(self, obj):
        """Get count of subfolders and documents in this folder"""
        subfolders = DocumentFolder.objects.filter(parent_folder=obj).count()
        documents = Document.objects.filter(folder=obj).count()
        return subfolders + documents
    
    def get_subfolder_count(self, obj):
        """Get count of subfolders in this folder"""
        return DocumentFolder.objects.filter(parent_folder=obj).count()
    
    def get_document_count(self, obj):
        """Get count of documents in this folder"""
        return Document.objects.filter(folder=obj).count()
    
    def get_parent_folder_name(self, obj):
        """Get parent folder name if exists"""
        if obj.parent_folder:
            return obj.parent_folder.name
        return None
    
    def get_teacher_name(self, obj):
        """Get teacher's full name"""
        if obj.teacher:
            return obj.teacher.get_full_name() or obj.teacher.username
        return None


class DocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for documents (learning materials) with file upload support.
    Handles file validation, metadata, and teacher information.
    """
    uploaded_by_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    folder_name = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    school = serializers.PrimaryKeyRelatedField(read_only=True)
    uploaded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Document
        fields = [
            'id', 'school', 'title', 'description', 'document_type',
            'file', 'file_url', 'file_size', 'uploaded_by', 'uploaded_by_name',
            'related_class', 'class_name', 'related_subject', 'subject_name',
            'folder', 'folder_name', 'created_at', 'updated_at', 'is_shared'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_shared']
    
    def validate_file(self, value):
        """
        Validate file upload:
        - Check file size (max 100MB)
        - Check file type
        """
        MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
        ALLOWED_EXTENSIONS = [
            'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
            'txt', 'jpg', 'jpeg', 'png', 'gif', 'zip', 'rar'
        ]
        
        if value.size > MAX_FILE_SIZE:
            raise serializers.ValidationError(
                f"File size must not exceed 100MB. Your file is {value.size / (1024*1024):.2f}MB"
            )
        
        # Get file extension
        file_ext = value.name.split('.')[-1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"File type '.{file_ext}' is not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        return value
    
    def get_uploaded_by_name(self, obj):
        """Get uploader's full name"""
        try:
            if obj.uploaded_by:
                return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        except:
            pass
        return None
    
    def get_subject_name(self, obj):
        """Get related subject name if exists"""
        try:
            return obj.related_subject.name if obj.related_subject else None
        except:
            return None
    
    def get_class_name(self, obj):
        """Get related class name if exists"""
        try:
            return obj.related_class.name if obj.related_class else None
        except:
            return None
    
    def get_folder_name(self, obj):
        """Get folder name if document is in a folder"""
        try:
            return obj.folder.name if obj.folder else "Root"
        except:
            return None
    
    def get_file_size(self, obj):
        """Get file size in human-readable format"""
        try:
            if obj.file:
                size = obj.file.size
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if size < 1024:
                        return f"{size:.2f} {unit}"
                    size /= 1024
                return f"{size:.2f} GB"
        except:
            pass
        return None
    
    def get_file_url(self, obj):
        """Get absolute file URL"""
        try:
            if obj.file:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.file.url)
                return obj.file.url
        except:
            pass
        return None
