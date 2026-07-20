"""
Upload service: validates files, uploads to Supabase Storage, extracts metadata,
and schedules background post-processing (thumbnails, duration, etc.).
"""
import logging
import tempfile
from io import BytesIO
from typing import Optional
import os

from django.conf import settings
from PIL import Image

from apps.feed import models
from apps.feed.services.supabase_client import get_supabase_client
from apps.feed.services.video_compression import BackendVideoCompressor, VideoCompressionError
from apps.feed.utils import (
    detect_mime_type, get_bucket_for_resource, make_storage_path,
    validate_resource_metadata,
)

logger = logging.getLogger(__name__)


class UploadService:
    """
    Handles uploads for lesson resources.
    Keeps views thin and ensures validation / storage logic is centralized.
    """

    @staticmethod
    def upload_resource(
        lesson: models.FeedLesson,
        file_obj,
        resource_type: str,
        title: Optional[str] = None,
        sort_order: int = 0,
        is_primary: bool = False,
    ) -> models.LessonResource:
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)

        mime_type = detect_mime_type(file_obj)
        validation = validate_resource_metadata(resource_type, mime_type, size)
        if not validation['ok']:
            raise ValueError(validation['error'])

        # Preserve original filename if available
        original_name = getattr(file_obj, 'name', 'unknown')

        # Compress video if resource type is video
        if resource_type == 'video':
            file_obj = UploadService._compress_video_if_needed(file_obj, size)
            file_obj.seek(0, 2)
            size = file_obj.tell()
            file_obj.seek(0)

            # After compression, re-detect mime type and validate again
            new_mime = detect_mime_type(file_obj)
            if new_mime and new_mime != mime_type:
                mime_type = new_mime

            validation = validate_resource_metadata(resource_type, mime_type, size)
            if not validation['ok']:
                raise ValueError(validation['error'])

            # If compressed to mp4, ensure filename has .mp4 extension for storage path
            try:
                base, _ = os.path.splitext(original_name)
                original_name = f"{base}.mp4"
            except Exception:
                original_name = original_name or 'video.mp4'

        bucket = get_bucket_for_resource(resource_type, mime_type)
        path = make_storage_path(bucket, original_name, lesson.teacher_id)

        client = get_supabase_client()
        storage = client.storage.from_(bucket)
        file_obj.seek(0)
        content = file_obj.read()
        storage.upload(
            path=path,
            file=content,
            file_options={'content-type': mime_type},
        )
        public_url = storage.get_public_url(path)

        resource = models.LessonResource.objects.create(
            lesson=lesson,
            resource_type=resource_type,
            title=title or original_name,
            storage_bucket=bucket,
            storage_path=path,
            public_url=public_url,
            file_size=size,
            mime_type=mime_type,
            sort_order=sort_order,
            is_primary=is_primary,
        )

        # Schedule background metadata extraction / thumbnail generation.
        from apps.feed.tasks import process_lesson_resource
        process_lesson_resource.delay(resource.id)
        return resource

    @staticmethod
    def _compress_video_if_needed(file_obj, original_size: int) -> BytesIO:
        """
        Compress video file if it's larger than the threshold.
        Returns either the compressed video or the original.
        """
        try:
            # Threshold: 10MB
            compression_threshold = 10 * 1024 * 1024
            
            if original_size <= compression_threshold:
                logger.info(f'Video size {original_size / 1024 / 1024:.2f}MB is below threshold, skipping compression')
                return file_obj
            
            logger.info(f'Video size {original_size / 1024 / 1024:.2f}MB exceeds threshold, compressing...')
            
            # Determine quality based on file size
            if original_size > 100 * 1024 * 1024:
                quality = 'low'
            elif original_size > 50 * 1024 * 1024:
                quality = 'medium'
            else:
                quality = 'high'
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_input:
                tmp_input.write(file_obj.read())
                tmp_input_path = tmp_input.name
                file_obj.seek(0)
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_output:
                tmp_output_path = tmp_output.name
            
            try:
                # Compress the video
                BackendVideoCompressor.compress_video(
                    input_path=tmp_input_path,
                    output_path=tmp_output_path,
                    quality=quality,
                    timeout=600,
                )
                
                # Read compressed video
                with open(tmp_output_path, 'rb') as f:
                    compressed_data = f.read()
                
                compressed_size = len(compressed_data)
                compression_ratio = ((1 - (compressed_size / original_size)) * 100)
                
                logger.info(
                    f'Video compression successful: '
                    f'{original_size / 1024 / 1024:.2f}MB -> {compressed_size / 1024 / 1024:.2f}MB '
                    f'({compression_ratio:.1f}% reduction)'
                )
                
                # Return as BytesIO
                compressed_io = BytesIO(compressed_data)
                return compressed_io
                
            finally:
                # Clean up temporary files
                import os
                try:
                    os.unlink(tmp_input_path)
                    os.unlink(tmp_output_path)
                except Exception as e:
                    logger.warning(f'Failed to clean up temp files: {e}')
                    
        except VideoCompressionError as e:
            logger.warning(f'Video compression failed: {e}, using original video')
            return file_obj
        except Exception as e:
            logger.error(f'Unexpected error during video compression: {e}')
            return file_obj

    @staticmethod
    def delete_resource(resource: models.LessonResource) -> None:
        try:
            client = get_supabase_client()
            client.storage.from_(resource.storage_bucket).remove([resource.storage_path])
        except Exception as exc:  # pragma: no cover
            logger.warning('Failed to remove Supabase object %s: %s', resource.storage_path, exc)
        resource.delete()

    @staticmethod
    def generate_thumbnail_from_video(resource: models.LessonResource) -> Optional[str]:
        """
        Placeholder for video thumbnail generation. In production this calls
        ffmpeg on the downloaded file and uploads the frame to lesson-thumbnails.
        """
        logger.info('Thumbnail generation requested for resource %s', resource.id)
        return None

    @staticmethod
    def extract_image_dimensions(resource: models.LessonResource) -> Optional[tuple]:
        if resource.resource_type not in ('image', 'video'):
            return None
        try:
            client = get_supabase_client()
            data = client.storage.from_(resource.storage_bucket).download(resource.storage_path)
            img = Image.open(BytesIO(data))
            return img.width, img.height
        except Exception as exc:  # pragma: no cover
            logger.warning('Could not extract image dimensions: %s', exc)
            return None
