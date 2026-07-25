"""
Celery background tasks for the Learning Feed.
"""
import logging
from io import BytesIO
from datetime import date, timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Avg, F
from django.utils import timezone

from apps.feed import models
from apps.feed.services.analytics_service import AnalyticsService
from apps.feed.services.upload_service import UploadService
from apps.feed.utils import get_bucket_for_resource
from apps.feed.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:  # pragma: no cover
    HAS_PYMUPDF = False

try:
    import ffmpeg
    HAS_FFMPEG = True
except ImportError:  # pragma: no cover
    HAS_FFMPEG = False


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_lesson_resource(self, resource_id: int):
    """Extract metadata and generate thumbnails for a lesson resource."""
    try:
        resource = models.LessonResource.objects.select_related('lesson').get(pk=resource_id)
    except models.LessonResource.DoesNotExist:
        return

    client = get_supabase_client()
    try:
        data = client.storage.from_(resource.storage_bucket).download(resource.storage_path)
    except Exception as exc:
        logger.warning('Resource download failed: %s', exc)
        return

    updated = {}

    if resource.resource_type == 'image' and HAS_PIL:
        try:
            img = Image.open(BytesIO(data))
            updated['width'] = img.width
            updated['height'] = img.height
        except Exception as exc:
            logger.warning('Image processing failed: %s', exc)

    if resource.resource_type == 'pdf' and HAS_PYMUPDF:
        try:
            doc = fitz.open(stream=data, filetype='pdf')
            updated['page_count'] = doc.page_count
            if not resource.lesson.thumbnail_url:
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=72)
                thumb_bytes = pix.tobytes('png')
                thumb_path = f"{resource.lesson.teacher_id}/thumbs/{resource.id}.png"
                client.storage.from_('lesson-thumbnails').upload(
                    path=thumb_path,
                    file=thumb_bytes,
                    file_options={'content-type': 'image/png'},
                )
                resource.lesson.thumbnail_url = client.storage.from_('lesson-thumbnails').get_public_url(thumb_path)
                resource.lesson.save(update_fields=['thumbnail_url'])
        except Exception as exc:
            logger.warning('PDF processing failed: %s', exc)

    if resource.resource_type == 'video':
        if not resource.lesson.poster_url:
            resource.lesson.poster_url = resource.public_url
            resource.lesson.save(update_fields=['poster_url'])

    if resource.resource_type == 'video' and HAS_FFMPEG:
        try:
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            probe = ffmpeg.probe(tmp_path)
            stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
            if stream:
                updated['width'] = int(stream.get('width', 0))
                updated['height'] = int(stream.get('height', 0))
            duration = float(probe['format'].get('duration', 0))
            updated['duration_seconds'] = int(duration)
            resource.lesson.duration_seconds = max(resource.lesson.duration_seconds, int(duration))
            resource.lesson.save(update_fields=['duration_seconds'])
            os.unlink(tmp_path)
        except Exception as exc:
            logger.warning('Video processing failed: %s', exc)

    if updated:
        for field, value in updated.items():
            setattr(resource, field, value)
        resource.save(update_fields=list(updated.keys()))


@shared_task
def refresh_trending_materialized_views():
    """Refresh materialized views for trending and popular teachers."""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY mv_feed_trending_lessons;')
        cursor.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY mv_feed_popular_teachers;')


@shared_task
def recalculate_trending_scores():
    """
    Recompute trending_score for all approved public lessons.
    Score decays with age and rewards engagement.
    """
    now = timezone.now()
    lessons = models.FeedLesson.objects.filter(status='approved', visibility='public')
    for lesson in lessons:
        age_hours = max(1, (now - lesson.published_at).total_seconds() / 3600) if lesson.published_at else 720
        score = (
            float(lesson.view_count) * 1.0
            + float(lesson.unique_view_count) * 2.0
            + float(lesson.like_count) * 4.0
            + float(lesson.save_count) * 5.0
            + float(lesson.comment_count) * 3.0
            + float(lesson.share_count) * 6.0
            + float(lesson.completion_rate or 0) * 10.0
            + float(lesson.avg_watch_seconds or 0) * 0.1
        ) / (age_hours ** 0.5)
        lesson.trending_score = score
        lesson.save(update_fields=['trending_score'])


@shared_task
def aggregate_watch_metrics():
    """Recompute avg watch time and completion rate for all lessons."""
    for lesson in models.FeedLesson.objects.iterator():
        AnalyticsService.update_watch_metrics(lesson)


@shared_task
def aggregate_daily_analytics():
    """Aggregate per-lesson counters into the daily analytics table."""
    today = date.today()
    metrics = [
        ('views', 'view_count'),
        ('likes', 'like_count'),
        ('saves', 'save_count'),
        ('comments', 'comment_count'),
        ('shares', 'share_count'),
    ]
    for metric_name, field_name in metrics:
        qs = models.FeedLesson.objects.values('school_id').annotate(
            total=F(field_name)
        )
        for row in qs:
            models.DailyAnalytics.objects.update_or_create(
                date=today,
                school_id=row['school_id'],
                metric_name=metric_name,
                dimension='',
                defaults={'metric_value': row['total']},
            )


@shared_task
def invalidate_expired_recommendation_cache():
    """Remove expired recommendation cache rows."""
    models.RecommendationCache.objects.filter(expires_at__lt=timezone.now()).delete()


@shared_task
def clear_stale_feed_caches():
    """Clear guest feed caches older than TTL."""
    from django.core.cache import cache
    try:
        client = cache.client.get_client()
        for key in client.scan_iter(match='feed:guest:*'):
            client.delete(key)
    except Exception as exc:
        logger.warning('Failed to clear stale caches: %s', exc)


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def finalize_cloudflare_video_upload(self, resource_id: int):
    """
    Poll Cloudflare Stream until the video is ready and update the lesson +
    resource with playback URL, thumbnail, and duration.

    This is the background counterpart to the synchronous poll in
    ``UploadService._upload_video_to_cloudflare``.  It is scheduled when
    Cloudflare's transcoding does not complete within the short sync window.

    Retries up to 10 times (≈10 min) with exponential back-off.
    """
    try:
        resource = models.LessonResource.objects.select_related('lesson').get(pk=resource_id)
    except models.LessonResource.DoesNotExist:
        logger.warning('Resource %d not found for Cloudflare finalisation', resource_id)
        return

    if resource.storage_bucket != 'cloudflare-stream':
        logger.debug('Resource %d is not a Cloudflare Stream resource — skipping', resource_id)
        return

    if resource.extra_metadata.get('processing_status') == 'ready':
        logger.info('Resource %d already finalised — skipping', resource_id)
        return

    success = UploadService.finalize_cloudflare_resource(resource)

    if not success:
        logger.info(
            'Resource %d (Cloudflare UID %s) not ready yet — will retry (attempt %d/%d)',
            resource_id,
            resource.extra_metadata.get('cloudflare_uid', ''),
            self.request.retries + 1,
            self.max_retries + 1,
        )
        raise self.retry()
