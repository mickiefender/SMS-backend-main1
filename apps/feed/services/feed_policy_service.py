"""
Feed moderation policy service.

Single source of truth for the Super Admin's Feed moderation policies and
creator restrictions. Policies live in the EXISTING platform SystemSetting
table (no new models); restrictions are a list of user ids in the same
table. Every consumer (lesson creation, comments, reports, the Feed
Supervisor APIs) reads policy state through this module so behaviour stays
consistent everywhere.
"""
from django.core.cache import cache

from apps.platform.models import SystemSetting

FEED_POLICIES_KEY = 'feed_moderation_policies'
RESTRICTED_CREATORS_KEY = 'feed_restricted_creators'
_POLICIES_CACHE_KEY = 'feed_moderation_policies_cached'
_RESTRICTED_CACHE_KEY = 'feed_restricted_creators_cached'

# moderation_mode values:
#   automatic_publishing     -> posts go live immediately
#   report_based_moderation  -> posts go live immediately, moderated when
#                               reported (RECOMMENDED default: scales without
#                               making the Super Admin a bottleneck)
#   manual_approval          -> every post waits for moderator approval
MODERATION_MODES = ('automatic_publishing', 'report_based_moderation', 'manual_approval')

DEFAULT_FEED_POLICIES = {
    'who_can_post': 'teachers',
    'allow_videos': True,
    'allow_documents': True,
    'allowed_file_types': ['video', 'pdf', 'image', 'audio'],
    'max_video_size_mb': 512,
    'max_video_duration_minutes': 30,
    'allow_comments': True,
    'allow_reporting': True,
    'moderation_mode': 'report_based_moderation',
}

MEDIA_TYPE_TO_POLICY_KEY = {
    'video': 'video',
    'pdf': 'pdf',
    'image': 'image',
    'audio': 'audio',
}


class FeedPolicyError(Exception):
    """Raised when an upload/action violates the configured feed policies."""


def _load_setting(key: str):
    return SystemSetting.objects.filter(key=key).first()


def get_feed_policies() -> dict:
    """Merged (defaults + stored) feed policies, cached briefly."""
    cached = cache.get(_POLICIES_CACHE_KEY)
    if cached:
        return cached
    row = _load_setting(FEED_POLICIES_KEY)
    stored = row.value if row and isinstance(row.value, dict) else {}
    merged = {**DEFAULT_FEED_POLICIES, **(stored or {})}
    cache.set(_POLICIES_CACHE_KEY, merged, 60)
    return merged


def save_feed_policies(updates: dict) -> dict:
    """Merge updates into the stored policies and bust caches."""
    current = get_feed_policies()
    merged = {**current, **updates}
    row = _load_setting(FEED_POLICIES_KEY)
    if row:
        row.value = merged
        row.save(update_fields=['value', 'updated_at'])
    else:
        SystemSetting.objects.create(
            key=FEED_POLICIES_KEY,
            value=merged,
            category='general',
            description='Alara Feed moderation policies (managed by the Feed Supervisor).',
        )
    cache.delete(_POLICIES_CACHE_KEY)
    cache.delete('feed_supervisor_overview')
    return merged


def get_feed_restricted_user_ids() -> set:
    cached = cache.get(_RESTRICTED_CACHE_KEY)
    if cached is not None:
        return set(cached)
    row = _load_setting(RESTRICTED_CREATORS_KEY)
    ids = row.value if row and isinstance(row.value, list) else []
    cache.set(_RESTRICTED_CACHE_KEY, list(ids or []), 60)
    return set(ids or [])


def is_feed_restricted(user) -> bool:
    return bool(user and getattr(user, 'pk', None) in get_feed_restricted_user_ids())


def set_creator_restricted(user_id: int, restricted: bool) -> None:
    """Add/remove a creator from the feed-posting restriction list."""
    ids = get_feed_restricted_user_ids()
    if restricted:
        ids.add(int(user_id))
    else:
        ids.discard(int(user_id))
    row = _load_setting(RESTRICTED_CREATORS_KEY)
    if row:
        row.value = sorted(ids)
        row.save(update_fields=['value', 'updated_at'])
    else:
        SystemSetting.objects.create(
            key=RESTRICTED_CREATORS_KEY,
            value=sorted(ids),
            category='general',
            description='User ids temporarily restricted from posting to the Feed.',
        )
    cache.delete(_RESTRICTED_CACHE_KEY)


def resolve_initial_status() -> str:
    """
    Initial FeedLesson.status for newly created posts according to the
    configured moderation mode.
    """
    mode = get_feed_policies().get('moderation_mode')
    return 'pending_review' if mode == 'manual_approval' else 'approved'


def assert_media_allowed(resource_types) -> None:
    """
    Validate the media types about to be attached to a new post against the
    configured policies. `resource_types` is an iterable like
    ['video', 'pdf', 'image'].
    """
    policies = get_feed_policies()
    allowed = set(policies.get('allowed_file_types') or [])
    for rt in set(resource_types or []):
        policy_key = MEDIA_TYPE_TO_POLICY_KEY.get(rt, rt)
        if policy_key == 'video' and not policies.get('allow_videos', True):
            raise FeedPolicyError('Video uploads to the Feed are currently disabled.')
        if policy_key in ('pdf', 'audio') and not policies.get('allow_documents', True):
            raise FeedPolicyError('Document uploads to the Feed are currently disabled.')
        if allowed and policy_key not in allowed:
            raise FeedPolicyError(f'"{policy_key}" files are not allowed on the Feed.')


def assert_video_constraints(file_obj=None, duration_seconds=None) -> None:
    """Best-effort enforcement of max video size / duration."""
    policies = get_feed_policies()
    max_mb = policies.get('max_video_size_mb')
    if file_obj is not None and max_mb:
        try:
            file_obj.seek(0, 2)
            size_mb = file_obj.tell() / (1024 * 1024)
            file_obj.seek(0)
        except Exception:
            size_mb = None
        if size_mb and size_mb > float(max_mb):
            raise FeedPolicyError(
                f'Video exceeds the maximum allowed size of {max_mb} MB.'
            )
    max_minutes = policies.get('max_video_duration_minutes')
    if duration_seconds and max_minutes and duration_seconds > float(max_minutes) * 60:
        raise FeedPolicyError(
            f'Video exceeds the maximum allowed duration of {max_minutes} minutes.'
        )


def assert_can_comment() -> None:
    if not get_feed_policies().get('allow_comments', True):
        raise FeedPolicyError('Comments are currently disabled on the Feed.')


def assert_can_report() -> None:
    if not get_feed_policies().get('allow_reporting', True):
        raise FeedPolicyError('Reporting is currently disabled on the Feed.')
