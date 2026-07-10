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


def _image_content_type(file_obj) -> str:
    """Derive a valid image/* MIME type from a file object.

    The Supabase SDK defaults file content-type to text/plain, so we
    must supply a correct value via file_options['content-type'].
    """
    ct = (file_obj.content_type or "").strip()
    if ct.startswith("image/"):
        return ct
    guessed = mimetypes.guess_type(file_obj.name)[0]
    if guessed and guessed.startswith("image/"):
        return guessed
    # Fall back to the extension if possible, otherwise JPEG
    ext = os.path.splitext(file_obj.name)[1].lower()
    mapping = {
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }
    return mapping.get(ext, "image/jpeg")


class SupabaseStorageService:
    def __init__(self):
        self.supabase_url = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
        # Try to get service role key first (bypasses RLS), fall back to anon key
        self.supabase_key = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('SUPABASE_ANON_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')

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
            file_ext = os.path.splitext(file_obj.name)[1] or '.jpg'
            filename = f"user_{user_id}_{uuid.uuid4().hex[:8]}{file_ext}"
            file_path = f"{user_id}/{filename}"

            content_type = _image_content_type(file_obj)
            file_content = file_obj.read()

            self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "content-type": content_type,
                    "cacheControl": "60",
                    "upsert": "false",
                    "metadata": {
                        "user_id": str(user_id),
                        "uploaded_at": datetime.now().isoformat()
                    }
                }
            )

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
            filename = f"school_{school_id}_{uuid.uuid4().hex[:8]}{file_ext}"
            file_path = f"{school_id}/{filename}"

            content_type = _image_content_type(file_obj)
            file_content = file_obj.read()

            self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "content-type": content_type,
                    "cacheControl": "3600",
                    "upsert": "false",
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

            content_type = file_obj.content_type or "application/octet-stream"

            self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "content-type": content_type,
                    "cacheControl": "3600",
                    "upsert": "false",
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
            public_url = f"{self.supabase_url}/storage/v1/object/public/{bucket_name}/{file_path}"
            return public_url
        except Exception as e:
            raise Exception(f"Failed to get public URL: {str(e)}")

    def upload_news_banner(
        self,
        file_obj,
        school_id: int,
        news_id: int,
    ) -> Tuple[str, str]:
        """
        Upload a news banner image to Supabase 'news-banners' bucket.

        Args:
            file_obj: File object to upload
            school_id: School ID
            news_id: News item ID

        Returns:
            Tuple of (bucket_path, public_url)
        """
        try:
            bucket_name = 'news-banners'
            file_ext = os.path.splitext(file_obj.name)[1] or '.jpg'
            filename = f"school_{school_id}_news_{news_id}_{uuid.uuid4().hex[:8]}{file_ext}"
            file_path = f"{school_id}/{filename}"

            content_type = _image_content_type(file_obj)
            file_content = file_obj.read()

            self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "content-type": content_type,
                    "cacheControl": "3600",
                    "upsert": "true",
                    "metadata": {
                        "school_id": str(school_id),
                        "news_id": str(news_id),
                        "uploaded_at": datetime.now().isoformat(),
                    }
                }
            )

            public_url = self.get_public_url(bucket_name, file_path)
            return file_path, public_url

        except Exception as e:
            raise Exception(f"Failed to upload news banner: {str(e)}")

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
            self.delete_file(bucket_name, old_file_path)

            file_content = file_obj.read()
            file_path = new_file_path or old_file_path

            content_type = file_obj.content_type or "application/octet-stream"

            self.client.storage.from_(bucket_name).upload(
                file_path,
                file_content,
                file_options={
                    "content-type": content_type,
                    "cacheControl": "3600",
                    "upsert": "true",
                }
            )

            public_url = self.get_public_url(bucket_name, file_path)
            return file_path, public_url

        except Exception as e:
            raise Exception(f"Failed to update file: {str(e)}")
