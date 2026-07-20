"""
Shared utilities for the Learning Feed.
"""
import hashlib
import magic
import uuid
from pathlib import Path
from django.utils import timezone


MIME_BUCKET_MAP = {
    'video/mp4': 'lesson-videos',
    'video/webm': 'lesson-videos',
    'video/quicktime': 'lesson-videos',
    'video/x-msvideo': 'lesson-videos',
    'video/mpeg': 'lesson-videos',
    'video/ogg': 'lesson-videos',
    'image/jpeg': 'lesson-images',
    'image/png': 'lesson-images',
    'image/webp': 'lesson-images',
    'image/gif': 'lesson-images',
    'image/svg+xml': 'lesson-images',
    'application/pdf': 'lesson-pdfs',
    'audio/mpeg': 'lesson-audio',
    'audio/mp3': 'lesson-audio',
    'audio/wav': 'lesson-audio',
    'audio/ogg': 'lesson-audio',
    'audio/aac': 'lesson-audio',
    'audio/webm': 'lesson-audio',
    'application/msword': 'lesson-assignments',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'lesson-assignments',
    'application/vnd.ms-excel': 'lesson-assignments',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'lesson-assignments',
    'text/plain': 'lesson-assignments',
    'application/json': 'lesson-quizzes',
}

BUCKET_MIME_TYPES = {
    'lesson-videos': [
        'video/mp4', 'video/webm', 'video/quicktime', 'video/x-msvideo',
        'video/mpeg', 'video/ogg',
    ],
    'lesson-images': [
        'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/svg+xml',
    ],
    'lesson-pdfs': ['application/pdf'],
    'lesson-thumbnails': ['image/jpeg', 'image/png', 'image/webp'],
    'lesson-audio': [
        'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/aac', 'audio/webm',
    ],
    'lesson-assignments': [
        'application/pdf', 'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/plain',
    ],
    'lesson-quizzes': ['application/json', 'application/pdf', 'text/plain'],
}

BUCKET_SIZE_LIMITS = {
    'lesson-videos': 5 * 1024 * 1024 * 1024,  # 5 GB
    'lesson-images': 100 * 1024 * 1024,       # 100 MB
    'lesson-pdfs': 200 * 1024 * 1024,         # 200 MB
    'lesson-thumbnails': 50 * 1024 * 1024,    # 50 MB
    'lesson-audio': 200 * 1024 * 1024,        # 200 MB
    'lesson-assignments': 100 * 1024 * 1024,  # 100 MB
    'lesson-quizzes': 50 * 1024 * 1024,       # 50 MB
}


def detect_mime_type(file_obj) -> str:
    """Detect MIME type from file content using libmagic."""
    file_obj.seek(0)
    blob = file_obj.read(4096)
    file_obj.seek(0)
    mime = magic.from_buffer(blob, mime=True)
    return mime


def get_bucket_for_resource(resource_type: str, mime_type: str) -> str:
    """Return the Supabase bucket for a given resource type / MIME type."""
    bucket = MIME_BUCKET_MAP.get(mime_type)
    if bucket:
        return bucket
    if resource_type == 'video':
        return 'lesson-videos'
    if resource_type == 'audio':
        return 'lesson-audio'
    if resource_type == 'image':
        return 'lesson-images'
    if resource_type == 'pdf':
        return 'lesson-pdfs'
    if resource_type == 'assignment':
        return 'lesson-assignments'
    if resource_type == 'quiz':
        return 'lesson-quizzes'
    return 'lesson-videos'


def make_storage_path(bucket: str, file_name: str, user_id: int) -> str:
    """Generate a deterministic storage path with user-scoped folder."""
    ext = Path(file_name).suffix.lower()
    unique = uuid.uuid4().hex[:16]
    today = timezone.now().strftime('%Y/%m/%d')
    return f"{user_id}/{today}/{unique}{ext}"


def hash_ip(ip: str) -> str:
    """Hash an IP address for privacy-preserving analytics."""
    return hashlib.sha256(ip.encode()).hexdigest()[:64]


def validate_resource_metadata(resource_type: str, mime_type: str, size: int) -> dict:
    """Validate a resource. Returns {'ok': bool, 'error': str}."""
    bucket = get_bucket_for_resource(resource_type, mime_type)
    allowed = BUCKET_MIME_TYPES.get(bucket, [])
    if mime_type not in allowed:
        return {'ok': False, 'error': f'MIME type {mime_type} not allowed for {bucket}.'}
    limit = BUCKET_SIZE_LIMITS.get(bucket, 0)
    if size > limit:
        return {'ok': False, 'error': f'File size {size} exceeds limit {limit} for {bucket}.'}
    return {'ok': True, 'error': None}
