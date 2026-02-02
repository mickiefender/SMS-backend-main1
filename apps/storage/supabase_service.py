"""
Supabase storage service for handling file uploads
Integrates with Supabase Storage API for profile pictures, school logos, and documents
"""
import os
import uuid
from datetime import datetime
from typing import Optional, Tuple
from supabase import create_client, Client
import mimetypes

class SupabaseStorageService:
    def __init__(self):
        self.supabase_url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
        self.supabase_key = os.environ.get('SUPABASE_ANON_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase URL and key must be set in environment variables")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
    
    def upload_profile_picture(
        self, 
        file_obj,
        user_id: int,
        user_name: str
    ) -> Tuple[str, str]:
        """
        Upload a profile picture to Supabase storage
        
        Args:
            file_obj: File object to upload
            user_id: User ID (for organizing files)
            user_name: User name (for reference)
        
        Returns:
            Tuple of (bucket_path, public_url)
        """
        try:
            bucket_name = 'profile-pictures'
            # Create unique filename: user_{id}_{timestamp}.{ext}
            file_ext = os.path.splitext(file_obj.name)[1] or '.jpg'
            filename = f"user_{user_id}_{datetime.now().timestamp()}{file_ext}"
            file_path = f"{user_id}/{filename}"
            
            # Read file content
            file_content = file_obj.read()
            
            # Upload to Supabase
            response = self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "cacheControl": "3600",
                    "upsert": False,
                    "contentType": file_obj.content_type or "image/jpeg"
                }
            )
            
            # Generate public URL
            public_url = self.get_public_url(bucket_name, file_path)
            
            return file_path, public_url
        
        except Exception as e:
            raise Exception(f"Failed to upload profile picture: {str(e)}")
    
    def upload_school_logo(
        self,
        file_obj,
        school_id: int,
        school_name: str
    ) -> Tuple[str, str]:
        """
        Upload a school logo to Supabase storage
        
        Args:
            file_obj: File object to upload
            school_id: School ID
            school_name: School name (for reference)
        
        Returns:
            Tuple of (bucket_path, public_url)
        """
        try:
            bucket_name = 'school-logos'
            file_ext = os.path.splitext(file_obj.name)[1] or '.png'
            filename = f"school_{school_id}_{datetime.now().timestamp()}{file_ext}"
            file_path = f"{school_id}/{filename}"
            
            file_content = file_obj.read()
            
            response = self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "cacheControl": "86400",  # 24 hours
                    "upsert": False,
                    "contentType": file_obj.content_type or "image/png"
                }
            )
            
            public_url = self.get_public_url(bucket_name, file_path)
            return file_path, public_url
        
        except Exception as e:
            raise Exception(f"Failed to upload school logo: {str(e)}")
    
    def upload_document(
        self,
        file_obj,
        school_id: int,
        class_id: Optional[int] = None,
        subject_id: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Upload a document to Supabase storage
        
        Args:
            file_obj: File object to upload
            school_id: School ID
            class_id: Optional class ID
            subject_id: Optional subject ID
        
        Returns:
            Tuple of (bucket_path, public_url)
        """
        try:
            bucket_name = 'documents'
            
            # Create path structure
            path_parts = [str(school_id)]
            if class_id:
                path_parts.append(f"class_{class_id}")
            if subject_id:
                path_parts.append(f"subject_{subject_id}")
            
            file_ext = os.path.splitext(file_obj.name)[1]
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            path_parts.append(unique_filename)
            
            file_path = "/".join(path_parts)
            file_content = file_obj.read()
            
            response = self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "cacheControl": "3600",
                    "upsert": False,
                    "contentType": file_obj.content_type or "application/octet-stream"
                }
            )
            
            public_url = self.get_public_url(bucket_name, file_path)
            return file_path, public_url
        
        except Exception as e:
            raise Exception(f"Failed to upload document: {str(e)}")
    
    def delete_file(self, bucket_name: str, file_path: str) -> bool:
        """
        Delete a file from Supabase storage
        
        Args:
            bucket_name: Name of the bucket
            file_path: Path to the file
        
        Returns:
            True if successful, raises Exception otherwise
        """
        try:
            self.client.storage.from_(bucket_name).remove([file_path])
            return True
        except Exception as e:
            raise Exception(f"Failed to delete file: {str(e)}")
    
    def get_public_url(self, bucket_name: str, file_path: str) -> str:
        """
        Get public URL for a file in Supabase storage
        
        Args:
            bucket_name: Name of the bucket
            file_path: Path to the file
        
        Returns:
            Public URL for the file
        """
        try:
            url = self.client.storage.from_(bucket_name).get_public_url(file_path)
            return url.get('publicUrl', '')
        except Exception as e:
            raise Exception(f"Failed to get public URL: {str(e)}")
    
    def update_file(
        self,
        file_obj,
        bucket_name: str,
        old_file_path: str,
        new_file_path: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Update/replace a file in Supabase storage
        
        Args:
            file_obj: New file object
            bucket_name: Name of the bucket
            old_file_path: Path to old file (will be deleted)
            new_file_path: Optional new path (if None, uses same path)
        
        Returns:
            Tuple of (bucket_path, public_url)
        """
        try:
            # Delete old file
            self.delete_file(bucket_name, old_file_path)
            
            file_content = file_obj.read()
            file_path = new_file_path or old_file_path
            
            # Upload new file
            self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "cacheControl": "3600",
                    "upsert": True,
                    "contentType": file_obj.content_type or "application/octet-stream"
                }
            )
            
            public_url = self.get_public_url(bucket_name, file_path)
            return file_path, public_url
        
        except Exception as e:
            raise Exception(f"Failed to update file: {str(e)}")
