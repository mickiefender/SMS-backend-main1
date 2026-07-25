"""
Upload service: validates files, uploads to Supabase Storage (images, PDFs, audio,
assignments, quizzes) or Cloudflare Stream (video), extracts metadata, and
schedules background post-processing.

Now incorporates Cloudflare Stream for ALL video uploads, replacing the old
Supabase video upload path entirely. Non-video resources continue to use
Supabase Storage.
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
from apps.feed.services.cloudflare_stream_service import (
    CloudflareStreamService,
    CloudflareStreamError,
)
from apps.feed.utils import (
    detect_mime_type, get_bucket_for_resource, make_storage_path,
    validate_resource_metadata,
)

logger = logging.getLogger(__name__)


class UploadService:
    """
    Handles uploads for lesson resources.
    - Video files → Cloudflare Stream (stored ONLY on Cloudflare, never on Supabase)
    - Non-video files → Supabase Storage (existing flow)
    """

    # How long (seconds) to wait synchronously for Cloudflare Stream transcoding.
    # Most videos are ready within 3-10s.  If transcoding takes longer, a Celery
    # background task (finalize_cloudflare_video_upload) will finish the job.
    _CF_SYNC_POLL_SECONDS = 20

    @staticmethod
    def upload_resource(
        lesson: models.FeedLesson,
        file_obj,
        resource_type: str,
        title: Optional[str] = None,
        sort_order: int = 0,
        is_primary: bool = False,
    ) -> models.LessonResource:
        """
        Upload a resource to a lesson.

        For *video* resources this bypasses Supabase entirely and uploads to
        Cloudflare Stream. The lesson's cloudflare_* fields are populated
        directly (either synchronously if fast, or via a background task).

        For *non-video* resources the existing Supabase Storage flow is used.
        """
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)

        mime_type = detect_mime_type(file_obj)

        # ── Route video files to Cloudflare Stream ─────────────
        if resource_type == 'video' or mime_type.startswith('video'):
            return UploadService._upload_video_to_cloudflare(
                lesson=lesson,
                file_obj=file_obj,
                title=title or getattr(file_obj, 'name', 'video'),
                sort_order=sort_order,
                is_primary=is_primary,
            )

        # ── Non-video files → Supabase Storage ────────────────
        validation = validate_resource_metadata(resource_type, mime_type, size)
        if not validation['ok']:
            raise ValueError(validation['error'])

        original_name = getattr(file_obj, 'name', 'unknown')

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

        # Schedule background metadata extraction.
        from apps.feed.tasks import process_lesson_resource
        process_lesson_resource.delay(resource.id)
        return resource

    # ------------------------------------------------------------------
    # Cloudflare Stream video upload
    # ------------------------------------------------------------------

    @staticmethod
    def _upload_video_to_cloudflare(
        lesson: models.FeedLesson,
        file_obj,
        title: str = 'video',
        sort_order: int = 0,
        is_primary: bool = False,
    ) -> models.LessonResource:
        """
        Upload a video file to Cloudflare Stream.

        **Strategy**
        1. Upload raw bytes to Cloudflare Stream.
        2. Poll synchronously for up to ``_CF_SYNC_POLL_SECONDS`` (20s).
           Most videos transcode within seconds, so the playback URL is
           usually available before the HTTP response is sent.
        3. If transcoding takes longer, the LessonResource is created
           with just the UID and a Celery background task is scheduled
           to finalise the metadata later.

        A LessonResource record is always created so existing code that
        checks ``lesson.resources.exists()`` or looks at the primary
        resource continues to work.
        """
        file_obj.seek(0)
        video_bytes = file_obj.read()
        filename = getattr(file_obj, 'name', title) or 'video.mp4'

        # 1. Upload raw bytes to Cloudflare Stream.
        #    Poll synchronously for a short window so quick transcodes
        #    populate the playback URL immediately.
        try:
            cf_service = CloudflareStreamService()
            result = cf_service.upload_video(
                video_data=video_bytes,
                filename=filename,
                mime_type='video/mp4',
                max_poll_seconds=UploadService._CF_SYNC_POLL_SECONDS,
                poll_interval=2.0,
            )
        except (CloudflareStreamError, RuntimeError) as exc:
            logger.error(
                'Cloudflare Stream upload failed for lesson %s: %s',
                lesson.id, exc,
            )
            raise ValueError(f'Video upload to Cloudflare Stream failed: {exc}') from exc

        video_uid = result['uid']
        playback_url = result.get('playback_url') or ''
        thumbnail_url = result.get('thumbnail_url') or ''
        duration = result.get('duration', 0)

        # Cloudflare Stream often provides the HLS playback URL immediately
        # even though the video state is "unknown" (not yet "ready").  We
        # consider the upload "done" as long as Cloudflare gave us a valid
        # playback URL — the video will play back immediately while HLS
        # renditions are still being generated in the background.
        has_playback_url = bool(playback_url)
        is_ready = result.get('status') == 'ready' or has_playback_url

        if is_ready:
            # ── Transcoding completed within the sync window ──
            playback_url = result.get('playback_url') or ''
            thumbnail_url = result.get('thumbnail_url') or ''
            duration = result.get('duration', 0)

            UploadService._update_lesson_cloudflare_fields(
                lesson,
                video_uid=video_uid,
                playback_url=playback_url,
                thumbnail_url=thumbnail_url,
                duration=duration,
            )

            resource = models.LessonResource.objects.create(
                lesson=lesson,
                resource_type='video',
                title=title,
                storage_bucket='cloudflare-stream',
                storage_path=f'cf://{video_uid}',
                public_url=playback_url,
                file_size=len(video_bytes),
                mime_type='video/mp4',
                duration_seconds=int(duration),
                sort_order=sort_order,
                is_primary=is_primary,
                extra_metadata={
                    'cloudflare_uid': video_uid,
                    'cloudflare_thumbnail_url': thumbnail_url,
                    'upload_source': 'cloudflare_stream',
                    'processing_status': 'ready',
                },
            )

            logger.info(
                'Video for lesson %s uploaded to Cloudflare Stream — '
                'UID: %s (ready sync, duration: %.1fs)',
                lesson.id, video_uid, duration,
            )

            return resource

        # ── Transcoding still in progress — fire-and-forget mode ──
        #     Create the resource with a "processing" status and let
        #     the Celery background task finalise it.
        UploadService._update_lesson_cloudflare_fields(
            lesson,
            video_uid=video_uid,
            playback_url='',
            thumbnail_url='',
            duration=0,
        )

        resource = models.LessonResource.objects.create(
            lesson=lesson,
            resource_type='video',
            title=title,
            storage_bucket='cloudflare-stream',
            storage_path=f'cf://{video_uid}',
            public_url='',
            file_size=len(video_bytes),
            mime_type='video/mp4',
            duration_seconds=0,
            sort_order=sort_order,
            is_primary=is_primary,
            extra_metadata={
                'cloudflare_uid': video_uid,
                'cloudflare_thumbnail_url': '',
                'upload_source': 'cloudflare_stream',
                'processing_status': 'processing',
            },
        )

        # Schedule background task to poll Cloudflare for readiness.
        from apps.feed.tasks import finalize_cloudflare_video_upload
        finalize_cloudflare_video_upload.delay(resource.id)

        logger.info(
            'Video for lesson %s uploaded to Cloudflare Stream — '
            'UID: %s (still processing, bg task scheduled)',
            lesson.id, video_uid,
        )

        return resource

    # ------------------------------------------------------------------
    # Background finalisation of Cloudflare Stream video metadata
    # ------------------------------------------------------------------

    @staticmethod
    def finalize_cloudflare_resource(resource: models.LessonResource) -> bool:
        """
        Poll Cloudflare Stream until the video is ready and update the
        lesson + resource with playback URL, thumbnail, and duration.

        Returns ``True`` if the video became ready, ``False`` if it is
        still pending after the maximum wait (caller should retry later).
        """
        video_uid = resource.extra_metadata.get('cloudflare_uid', '')
        if not video_uid:
            logger.warning('No cloudflare_uid on resource %d — skipping finalise', resource.id)
            return False

        if resource.extra_metadata.get('processing_status') == 'ready':
            return True  # already finalised

        lesson = resource.lesson

        try:
            cf_service = CloudflareStreamService()
            result = cf_service.poll_until_ready(
                video_uid,
                max_seconds=300,       # up to 5 min in the background
                interval=2.0,
            )
        except CloudflareStreamError as exc:
            logger.error(
                'Background finalise failed for lesson %s, resource %d: %s',
                lesson.id, resource.id, exc,
            )
            return False

        playback_url = result.get('playback_url') or ''
        thumbnail_url = result.get('thumbnail_url') or ''

        # Accept as ready if Cloudflare returned a valid playback URL,
        # even if the status is still "unknown" (HLS manifests are available
        # before full transcoding completes).
        if result.get('status') != 'ready' and not playback_url:
            logger.info(
                'Video %s still processing after background poll (status=%s) — '
                'will retry on next finalise call',
                video_uid, result.get('status'),
            )
            return False
        duration = result['duration']

        UploadService._update_lesson_cloudflare_fields(
            lesson,
            video_uid=video_uid,
            playback_url=playback_url,
            thumbnail_url=thumbnail_url,
            duration=duration,
        )

        resource.public_url = playback_url or ''
        resource.duration_seconds = int(duration)
        resource.extra_metadata.update({
            'cloudflare_thumbnail_url': thumbnail_url or '',
            'processing_status': 'ready',
            'processing_error': '',
        })
        resource.save(update_fields=[
            'public_url',
            'duration_seconds',
            'extra_metadata',
        ])

        logger.info(
            'Video %s finalised — duration: %.1fs, playback: %s',
            video_uid, duration, playback_url,
        )
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _update_lesson_cloudflare_fields(
        lesson: models.FeedLesson,
        video_uid: str,
        playback_url: str,
        thumbnail_url: str,
        duration: float,
    ) -> None:
        """Set the Cloudflare-related fields on a FeedLesson and save."""
        lesson.cloudflare_video_uid = video_uid
        lesson.cloudflare_playback_url = playback_url
        lesson.cloudflare_thumbnail_url = thumbnail_url or ''
        lesson.video_duration = duration
        lesson.duration_seconds = max(lesson.duration_seconds, int(duration))
        if not lesson.poster_url and thumbnail_url:
            lesson.poster_url = thumbnail_url
        if not lesson.thumbnail_url and thumbnail_url:
            lesson.thumbnail_url = thumbnail_url
        lesson.save(update_fields=[
            'cloudflare_video_uid',
            'cloudflare_playback_url',
            'cloudflare_thumbnail_url',
            'video_duration',
            'duration_seconds',
            'poster_url',
            'thumbnail_url',
        ])

    # ------------------------------------------------------------------
    # Video compression (deprecated — Cloudflare Stream handles this)
    # ------------------------------------------------------------------

    @staticmethod
    def _compress_video_if_needed(file_obj, original_size: int) -> BytesIO:
        """
        **DEPRECATED** — Cloudflare Stream handles transcoding and adaptive
        bitrate on its own. This method is kept for backwards compatibility
        if the old Supabase upload path is still needed, but is no longer
        called for new video uploads.
        """
        try:
            compression_threshold = 10 * 1024 * 1024

            if original_size <= compression_threshold:
                logger.info(f'Video size {original_size / 1024 / 1024:.2f}MB is below threshold, skipping compression')
                return file_obj

            logger.info(f'Video size {original_size / 1024 / 1024:.2f}MB exceeds threshold, compressing...')

            if original_size > 100 * 1024 * 1024:
                quality = 'low'
            elif original_size > 50 * 1024 * 1024:
                quality = 'medium'
            else:
                quality = 'high'

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_input:
                tmp_input.write(file_obj.read())
                tmp_input_path = tmp_input.name
                file_obj.seek(0)

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_output:
                tmp_output_path = tmp_output.name

            try:
                BackendVideoCompressor.compress_video(
                    input_path=tmp_input_path,
                    output_path=tmp_output_path,
                    quality=quality,
                    timeout=600,
                )

                with open(tmp_output_path, 'rb') as f:
                    compressed_data = f.read()

                compressed_size = len(compressed_data)
                compression_ratio = ((1 - (compressed_size / original_size)) * 100)

                logger.info(
                    f'Video compression successful: '
                    f'{original_size / 1024 / 1024:.2f}MB -> {compressed_size / 1024 / 1024:.2f}MB '
                    f'({compression_ratio:.1f}% reduction)'
                )

                compressed_io = BytesIO(compressed_data)
                return compressed_io

            finally:
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

    # ------------------------------------------------------------------
    # Delete resource (handle both Supabase and Cloudflare Stream)
    # ------------------------------------------------------------------

    @staticmethod
    def delete_resource(resource: models.LessonResource) -> None:
        """
        Delete a resource. If the resource was stored on Cloudflare Stream
        (indicated by storage_bucket == 'cloudflare-stream'), delete the
        video from Cloudflare Stream. Otherwise delete from Supabase Storage.
        """
        if resource.storage_bucket == 'cloudflare-stream':
            video_uid = resource.extra_metadata.get('cloudflare_uid', '')
            if video_uid:
                try:
                    cf_service = CloudflareStreamService()
                    cf_service.delete_video(video_uid)
                except Exception as exc:
                    logger.warning('Failed to delete Cloudflare Stream video %s: %s', video_uid, exc)
            resource.delete()
            return

        # Supabase Storage deletion
        try:
            client = get_supabase_client()
            client.storage.from_(resource.storage_bucket).remove([resource.storage_path])
        except Exception as exc:
            logger.warning('Failed to remove Supabase object %s: %s', resource.storage_path, exc)
        resource.delete()

    # ------------------------------------------------------------------
    # Thumbnail extraction (video thumbnails now come from Cloudflare)
    # ------------------------------------------------------------------

    @staticmethod
    def generate_thumbnail_from_video(resource: models.LessonResource) -> Optional[str]:
        """
        **DEPRECATED** — Cloudflare Stream auto-generates thumbnails.
        """
        if resource.storage_bucket == 'cloudflare-stream':
            logger.info(
                'Cloudflare Stream video %s — thumbnail URL: %s',
                resource.extra_metadata.get('cloudflare_uid'),
                resource.lesson.cloudflare_thumbnail_url or 'N/A',
            )
            return resource.lesson.cloudflare_thumbnail_url
        logger.info('Thumbnail generation requested for Supabase resource %s', resource.id)
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
        except Exception as exc:
            logger.warning('Could not extract image dimensions: %s', exc)
            return None
