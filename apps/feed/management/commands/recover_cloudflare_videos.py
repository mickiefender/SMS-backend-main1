"""
Management command to retroactively recover Cloudflare Stream videos that
were uploaded with the old fire-and-forget approach (max_poll_seconds=0) and
never had their playback URL populated.

Usage:
    python manage.py recover_cloudflare_videos              # all stuck videos
    python manage.py recover_cloudflare_videos --lesson 42  # one lesson
    python manage.py recover_cloudflare_videos --dry-run     # just count
"""
import logging

from django.core.management.base import BaseCommand

from apps.feed import models
from apps.feed.services.upload_service import UploadService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recover Cloudflare Stream videos where playback_url is empty'

    def add_arguments(self, parser):
        parser.add_argument(
            '--lesson',
            type=int,
            default=None,
            help='Recover a specific lesson by ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only count and report, do not update',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        lesson_id = options['lesson']

        # Find lessons with a Cloudflare UID but no playback URL
        qs = models.FeedLesson.objects.exclude(
            cloudflare_video_uid=''
        ).filter(
            cloudflare_playback_url=''
        )
        if lesson_id:
            qs = qs.filter(id=lesson_id)

        total = qs.count()
        self.stdout.write(f'Found {total} lesson(s) with empty cloudflare_playback_url')

        if total == 0:
            return

        if dry_run:
            self.stdout.write('Dry-run — no changes made.')
            return

        recovered = 0
        errors = 0

        for lesson in qs:
            video_uid = lesson.cloudflare_video_uid
            self.stdout.write(
                f'  Lesson {lesson.id} ("{lesson.title[:50]}") '
                f'UID: {video_uid[:20]}…'
            )

            # Find the associated LessonResource
            resource = models.LessonResource.objects.filter(
                lesson=lesson,
                storage_bucket='cloudflare-stream',
            ).order_by('-is_primary', 'sort_order', 'id').first()

            if not resource:
                self.stdout.write(
                    self.style.WARNING(f'    No cloudflare-stream resource found — skipping')
                )
                continue

            try:
                success = UploadService.finalize_cloudflare_resource(resource)
                if success:
                    self.stdout.write(
                        self.style.SUCCESS(f'    Recovered — playback URL set')
                    )
                    recovered += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f'    Still processing on Cloudflare — will retry later')
                    )
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f'    Error: {exc}')
                )
                errors += 1

        self.stdout.write(f'\nDone: {recovered} recovered, {errors} errors, {total - recovered - errors} still pending')
