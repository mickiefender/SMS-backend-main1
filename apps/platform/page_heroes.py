"""
Hero images for the public marketing pages.

The About, Careers, Join the team, Contact, and Support pages all render a page
hero. The copy lives in the frontend, but the background image is managed by
the super admin from the console and stored in the `pages.hero_images`
SystemSetting as:

    {
        "about": {"url": "...", "storage_path": "page-heroes/...", "updated_at": "..."},
        ...
    }

`PublicPageHeroesView` exposes the published mapping anonymously so the
marketing site can render it; `PageHeroView` is the super-admin management API.
"""
import logging
import os
import secrets

from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform.models import SystemSetting, write_audit_log

logger = logging.getLogger(__name__)

SETTING_KEY = 'pages.hero_images'
STORAGE_FOLDER = 'page-heroes'

# Public page key -> console metadata. Keep in sync with
# frontend/lib/page-heroes.ts.
PAGE_HERO_PAGES = [
    {
        'key': 'about',
        'label': 'About',
        'path': '/about',
        'description': 'Hero image shown at the top of the About page.',
    },
    {
        'key': 'careers',
        'label': 'Careers',
        'path': '/careers',
        'description': 'Hero image shown at the top of the Careers page.',
    },
    {
        'key': 'join-team',
        'label': 'Join the Team',
        'path': '/join-team',
        'description': 'Hero image shown at the top of the Join the Team application page.',
    },
    {
        'key': 'contact',
        'label': 'Contact',
        'path': '/contact',
        'description': 'Hero image shown at the top of the Contact page.',
    },
    {
        'key': 'support',
        'label': 'Support',
        'path': '/support',
        'description': 'Hero image shown at the top of the Support page.',
    },
]

PAGE_HERO_KEYS = {page['key'] for page in PAGE_HERO_PAGES}

ALLOWED_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
BUCKET_MARKER = '/storage/v1/object/public/'


def get_hero_setting():
    """Return (and lazily create) the hero-image SystemSetting row."""
    setting, _ = SystemSetting.objects.get_or_create(
        key=SETTING_KEY,
        defaults={
            'category': 'branding',
            'description': 'Hero images for the public About, Careers, Join the team, Contact, and Support pages',
            'value': {},
        },
    )
    return setting


def hero_map(setting):
    """The stored mapping, guarded against legacy or unexpected value shapes."""
    value = setting.value if setting else None
    return value if isinstance(value, dict) else {}


def storage_path_from_url(url):
    """Recover the storage key from a public URL (older rows carry no path)."""
    if not url or BUCKET_MARKER not in url:
        return ''
    return url.split(BUCKET_MARKER, 1)[1].split('/', 1)[1]


def delete_stored_file(path):
    """Best-effort removal of a superseded hero file from storage."""
    if not path:
        return
    try:
        default_storage.delete(path)
    except Exception as error:  # storage backends can fail on missing objects
        logger.warning('Could not delete page hero file %s: %s', path, error)


def validate_upload(upload):
    """Return an error message for an invalid file, or '' when it is accepted."""
    if upload.size > MAX_UPLOAD_BYTES:
        return 'Hero images must be 8 MB or smaller.'
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        return 'Only JPEG, PNG, and WebP hero images are supported.'
    if os.path.splitext(upload.name)[1].lower() not in ALLOWED_EXTENSIONS:
        return 'Only .jpg, .jpeg, .png, and .webp files are supported.'
    return ''


class PublicPageHeroesView(APIView):
    """Anonymous read of the published page hero images."""
    permission_classes = [AllowAny]

    def get(self, request):
        setting = SystemSetting.objects.filter(key=SETTING_KEY).first()
        heroes = hero_map(setting)
        published = {
            key: {
                'url': entry.get('url', ''),
                'updated_at': entry.get('updated_at', ''),
            }
            for key, entry in heroes.items()
            if isinstance(entry, dict) and entry.get('url')
        }
        return Response({'heroes': published})


class PageHeroView(APIView):
    """Super-admin management of the public page hero images.

    Reuses the platform `IsSuperAdmin` rules (role check plus the
    `content.manage` permission for platform staff) without importing the
    platform views module at import time, which would be circular.
    """

    def get_permissions(self):
        from apps.platform.views import IsSuperAdmin
        return [IsSuperAdmin()]

    def get(self, request):
        setting = get_hero_setting()
        return Response({
            'pages': PAGE_HERO_PAGES,
            'heroes': hero_map(setting),
        })

    def post(self, request):
        page_key = str(request.data.get('page', '')).strip()
        upload = request.FILES.get('image')

        if page_key not in PAGE_HERO_KEYS:
            return Response(
                {'detail': 'Select a valid page to attach the hero image to.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload:
            return Response({'detail': 'A hero image file is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        error = validate_upload(upload)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

        extension = os.path.splitext(upload.name)[1].lower()
        storage_path = default_storage.save(
            f'{STORAGE_FOLDER}/{page_key}-{secrets.token_hex(16)}{extension}', upload)

        setting = get_hero_setting()
        heroes = dict(hero_map(setting))
        previous = heroes.get(page_key)
        previous_path = previous.get('storage_path', '') if isinstance(previous, dict) else ''

        hero = {
            'url': default_storage.url(storage_path),
            'storage_path': storage_path,
            'updated_at': timezone.now().isoformat(),
        }
        heroes[page_key] = hero
        setting.value = heroes
        setting.updated_by = request.user
        setting.save(update_fields=['value', 'updated_by', 'updated_at'])

        delete_stored_file(previous_path)
        write_audit_log(request, request.user, 'page_hero.updated',
                        'system_setting', setting.id, page_key,
                        {'url': hero['url'], 'replaced': bool(previous_path)})
        return Response(hero, status=status.HTTP_201_CREATED)

    def delete(self, request, page_key):
        setting = SystemSetting.objects.filter(key=SETTING_KEY).first()
        heroes = dict(hero_map(setting))
        hero = heroes.get(page_key)
        if not isinstance(hero, dict) or not hero.get('url'):
            return Response(
                {'detail': 'No hero image is set for this page.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        storage_path = hero.get('storage_path') or storage_path_from_url(hero.get('url', ''))
        heroes.pop(page_key, None)
        setting.value = heroes
        setting.updated_by = request.user
        setting.save(update_fields=['value', 'updated_by', 'updated_at'])

        delete_stored_file(storage_path)
        write_audit_log(request, request.user, 'page_hero.removed',
                        'system_setting', setting.id, page_key,
                        {'url': hero.get('url', '')})
        return Response(status=status.HTTP_204_NO_CONTENT)
