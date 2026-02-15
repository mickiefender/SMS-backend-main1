"""
Custom Django storage backend for Supabase Storage
Handles file uploads to Supabase storage buckets
"""
import os
import mimetypes
from django.core.files.storage import Storage
from django.conf import settings
from supabase import create_client, Client
from urllib.parse import urljoin
import uuid


class SupabaseStorage(Storage):
    """
    Custom storage backend for Supabase Storage.
    Uploads files to Supabase storage bucket instead of local filesystem.
    """
    
    def __init__(self):
        from django.conf import settings
        
        self.supabase_url = getattr(settings, 'SUPABASE_URL', None) or os.environ.get('SUPABASE_URL')
        self.supabase_key = getattr(settings, 'SUPABASE_SERVICE_KEY', None) or os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('SUPABASE_KEY')
        self.bucket_name = getattr(settings, 'SUPABASE_STORAGE_BUCKET', 'school-documents')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables or Django settings. "
                f"Current values: SUPABASE_URL={self.supabase_url}, SUPABASE_SERVICE_KEY={'***' if self.supabase_key else 'None'}"
            )
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.storage = self.client.storage.from_(self.bucket_name)
    
    def _save(self, name, content):
        """
        Save file to Supabase storage.
        Returns the name of the saved file.
        """
        # Generate unique filename to avoid collisions
        file_extension = os.path.splitext(name)[1]
        unique_name = f"{uuid.uuid4()}{file_extension}"
        
        # Get content type
        content_type, _ = mimetypes.guess_type(name)
        if not content_type:
            content_type = 'application/octet-stream'
        
        # Read file content
        content.seek(0)
        file_data = content.read()
        
        # Upload to Supabase
        try:
            self.storage.upload(
                path=unique_name,
                file=file_data,
                file_options={"content-type": content_type}
            )
            return unique_name
        except Exception as e:
            raise IOError(f"Failed to upload file to Supabase: {str(e)}")
    
    def _open(self, name, mode='rb'):
        """
        Retrieve a file from Supabase storage.
        """
        try:
            response = self.storage.download(name)
            from django.core.files.base import ContentFile
            return ContentFile(response)
        except Exception as e:
            raise IOError(f"Failed to download file from Supabase: {str(e)}")
    
    def delete(self, name):
        """
        Delete a file from Supabase storage.
        """
        try:
            self.storage.remove([name])
        except Exception as e:
            # Log error but don't raise exception
            print(f"Failed to delete file from Supabase: {str(e)}")
    
    def exists(self, name):
        """
        Check if a file exists in Supabase storage.
        """
        try:
            files = self.storage.list()
            return any(f['name'] == name for f in files)
        except:
            return False
    
    def url(self, name):
        """
        Return the public URL for the file.
        """
        try:
            # Get public URL
            public_url = self.storage.get_public_url(name)
            return public_url
        except Exception as e:
            # Fallback to constructing URL manually
            return f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{name}"
    
    def size(self, name):
        """
        Return the size of the file in bytes.
        """
        try:
            files = self.storage.list()
            for f in files:
                if f['name'] == name:
                    return f.get('metadata', {}).get('size', 0)
            return 0
        except:
            return 0
    
    def get_available_name(self, name, max_length=None):
        """
        Return a filename that's available in the storage.
        Since we use UUIDs, we don't need to check for availability.
        """
        return name
