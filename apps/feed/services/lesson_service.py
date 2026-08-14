"""
Lesson service: creation, updates, deletion, visibility checks, and
view / completion tracking.
"""
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.feed import models
from apps.feed.services.upload_service import UploadService
from apps.feed.services.analytics_service import AnalyticsService
from apps.feed.utils import detect_mime_type


class LessonService:
    @staticmethod
    def _get_resource_type_from_file(file_obj):
        content_type = getattr(file_obj, 'content_type', None) or ''
        if content_type:
            if content_type.startswith('video'):
                return 'video'
            if content_type.startswith('image'):
                return 'image'
            if content_type == 'application/pdf':
                return 'pdf'
            if content_type.startswith('audio'):
                return 'audio'
            return 'video'

        try:
            mime_type = detect_mime_type(file_obj)
            if mime_type.startswith('video'):
                return 'video'
            if mime_type.startswith('image'):
                return 'image'
            if mime_type == 'application/pdf':
                return 'pdf'
            if mime_type.startswith('audio'):
                return 'audio'
        except Exception:
            pass
        return 'video'

    @staticmethod
    def create_lesson(teacher, validated_data, resource_files=None):
        """
        Create a lesson and optionally attach resources.
        `validated_data` should already be serializer-validated.
        """
        cloudflare_video_uid = validated_data.pop('cloudflare_video_uid', '')
        tags = validated_data.pop('tags', [])
        resources = validated_data.pop('resources', [])
        media_file = validated_data.pop('media_file', None)
        thumbnail_file = validated_data.pop('thumbnail_file', None)
        media_resource_type = None
        status = validated_data.get('status', 'pending_review')
        visibility = validated_data.get('visibility', 'public')

        # Default the school to the teacher's school when the client does not
        # provide one (the mobile app has no school picker on upload).
        if not validated_data.get('school'):
            validated_data['school'] = teacher.school

        if status == 'approved' and visibility == 'public':
            validated_data['published_at'] = timezone.now()

        # If cloudflare_video_uid was provided (direct upload), set it immediately
        # so the lesson has a video even before transcoding finishes.
        if cloudflare_video_uid:
            validated_data['cloudflare_video_uid'] = cloudflare_video_uid

        lesson = models.FeedLesson.objects.create(teacher=teacher, **validated_data)
        if tags:
            lesson.tags.set(tags)

        # If a Cloudflare direct upload UID was provided, poll Cloudflare
        # synchronously for the playback URL. The video was already uploaded
        # by the Flutter app directly to Cloudflare Stream's upload URL.
        # We only need to wait for Cloudflare to finish transcoding.
        if cloudflare_video_uid:
            from apps.feed.services.cloudflare_stream_service import (
                CloudflareStreamService,
                CloudflareStreamError,
            )
            cf_service = CloudflareStreamService()
            try:
                cf_result = cf_service.poll_until_ready(
                    cloudflare_video_uid,
                    max_seconds=60,   # wait up to 60s for playback URL
                    interval=2.0,
                )
            except CloudflareStreamError:
                cf_result = {
                    'uid': cloudflare_video_uid,
                    'status': 'pending',
                    'playback_url': None,
                    'thumbnail_url': None,
                    'duration': 0,
                }

            playback_url = cf_result.get('playback_url') or ''
            thumbnail_url = cf_result.get('thumbnail_url') or ''
            duration = cf_result.get('duration', 0)

            # Update lesson Cloudflare fields
            lesson.cloudflare_playback_url = playback_url
            lesson.cloudflare_thumbnail_url = thumbnail_url or ''
            lesson.video_duration = duration
            lesson.duration_seconds = max(lesson.duration_seconds, int(duration))
            if not lesson.poster_url and thumbnail_url:
                lesson.poster_url = thumbnail_url
            if not lesson.thumbnail_url and thumbnail_url:
                lesson.thumbnail_url = thumbnail_url
            lesson.save(update_fields=[
                'cloudflare_playback_url',
                'cloudflare_thumbnail_url',
                'video_duration',
                'duration_seconds',
                'poster_url',
                'thumbnail_url',
            ])

            # Create LessonResource with the playback URL immediately
            resource = models.LessonResource.objects.create(
                lesson=lesson,
                resource_type='video',
                title='Video',
                storage_bucket='cloudflare-stream',
                storage_path=f'cf://{cloudflare_video_uid}',
                public_url=playback_url,
                file_size=0,
                mime_type='video/mp4',
                duration_seconds=int(duration),
                sort_order=0,
                is_primary=True,
                extra_metadata={
                    'cloudflare_uid': cloudflare_video_uid,
                    'cloudflare_thumbnail_url': thumbnail_url,
                    'upload_source': 'direct_upload',
                    'processing_status': 'ready' if playback_url else 'processing',
                },
            )

            # If playback URL not ready yet, schedule a background task
            if not playback_url:
                from apps.feed.tasks import finalize_cloudflare_video_upload
                finalize_cloudflare_video_upload.delay(resource.id)

        # Handle media file upload if provided
        if media_file:
            media_resource_type = LessonService._get_resource_type_from_file(media_file)
            resource = UploadService.upload_resource(
                lesson=lesson,
                file_obj=media_file,
                resource_type=media_resource_type,
                title=getattr(media_file, 'name', 'media'),
                sort_order=0,
                is_primary=True,
            )
            if media_resource_type == 'image' and not lesson.thumbnail_url:
                lesson.thumbnail_url = resource.public_url
                lesson.save(update_fields=['thumbnail_url'])
            if media_resource_type == 'video' and not lesson.poster_url:
                lesson.poster_url = resource.public_url
                lesson.save(update_fields=['poster_url'])

        if thumbnail_file:
            thumbnail_resource = UploadService.upload_resource(
                lesson=lesson,
                file_obj=thumbnail_file,
                resource_type='image',
                title=getattr(thumbnail_file, 'name', 'thumbnail'),
                sort_order=1,
                is_primary=False,
            )
            changed_fields = []
            if not lesson.thumbnail_url:
                lesson.thumbnail_url = thumbnail_resource.public_url
                changed_fields.append('thumbnail_url')

            if media_resource_type == 'video':
                lesson.poster_url = thumbnail_resource.public_url
                changed_fields.append('poster_url')
            elif not lesson.poster_url:
                lesson.poster_url = thumbnail_resource.public_url
                changed_fields.append('poster_url')

            if changed_fields:
                lesson.save(update_fields=changed_fields)

        for idx, res in enumerate(resources):
            UploadService.upload_resource(
                lesson=lesson,
                file_obj=res['file'],
                resource_type=res['resource_type'],
                title=res.get('title', ''),
                sort_order=res.get('sort_order', idx + 1),
                is_primary=res.get('is_primary', False),
            )

        # Ensure analytics row exists.
        models.LessonAnalytics.objects.get_or_create(lesson=lesson)
        LessonService.update_quality_score(lesson)
        return lesson

    @staticmethod
    def update_quality_score(lesson: models.FeedLesson):
        """Score basic content completeness until user feedback is available."""
        score = 0
        score += 20 if lesson.title.strip() else 0
        score += 20 if lesson.description.strip() else 0
        score += 15 if lesson.subject_id else 0
        score += 15 if lesson.level_id else 0
        score += 10 if lesson.class_obj_id else 0
        score += 20 if lesson.resources.exists() else 0
        lesson.quality_score = Decimal(score)
        lesson.save(update_fields=['quality_score'])

    @staticmethod
    def update_lesson(lesson, validated_data):
        tags = validated_data.pop('tags', None)
        for attr, value in validated_data.items():
            setattr(lesson, attr, value)

        # Auto-publish when approved and public.
        if lesson.status == 'approved' and lesson.visibility == 'public' and not lesson.published_at:
            lesson.published_at = timezone.now()

        lesson.save()
        if tags is not None:
            lesson.tags.set(tags)
        return lesson

    @staticmethod
    def delete_lesson(lesson):
        with transaction.atomic():
            for resource in lesson.resources.all():
                UploadService.delete_resource(resource)
            lesson.delete()

    @staticmethod
    def can_view_lesson(lesson, user) -> bool:
        """
        Public lessons are viewable by everyone. School-only lessons require
        an authenticated user belonging to the same school.
        """
        if lesson.visibility == 'public' and lesson.status == 'approved':
            return True
        if not user or not user.is_authenticated:
            return False
        if user.role in ['super_admin', 'school_admin']:
            return True
        if lesson.visibility == 'school_only' and lesson.status == 'approved':
            return bool(user.school_id and user.school_id == lesson.school_id)
        if lesson.teacher_id == user.id:
            return True
        return False

    @staticmethod
    def record_watch(
        user,
        lesson: models.FeedLesson,
        watch_seconds: int,
        resume_position: int,
    ) -> models.WatchHistory:
        AnalyticsService.track_view(lesson, user)

        history, created = models.WatchHistory.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={
                'watch_seconds': watch_seconds,
                'resume_position_seconds': resume_position,
            },
        )
        if not created:
            history.watch_seconds = max(history.watch_seconds, watch_seconds)
            history.resume_position_seconds = resume_position

        duration = max(lesson.duration_seconds, 1)
        completion = min((history.watch_seconds / duration) * 100, 100)
        history.completion_percentage = Decimal(completion).quantize(Decimal('0.01'))
        history.is_completed = history.completion_percentage >= 90
        history.save()

        if history.is_completed:
            AnalyticsService.track_completion(lesson)

        return history
