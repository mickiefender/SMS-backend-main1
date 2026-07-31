"""
Firebase Cloud Messaging service — sends push notifications via the
Firebase Admin SDK.

Uses a Firebase service-account credential (NOT the legacy server key):
  - FIREBASE_SERVICE_ACCOUNT_PATH: path to the downloaded service-account
    JSON file (Firebase Console → Project settings → Service accounts →
    Generate new private key).
  - OR FIREBASE_SERVICE_ACCOUNT_JSON: the contents of that file (useful for
    serverless deployments / Supabase-hosted backends where files aren't
    persistent).

Automatically deactivates invalid/unregistered FCM tokens, matching the
preferred security model of the Admin SDK.
"""
import json
import logging
import os

from django.conf import settings
from firebase_admin import credentials, initialize_app, messaging
from firebase_admin import _DEFAULT_APP_NAME
from firebase_admin.exceptions import FirebaseError

from apps.notifications.models import Device

logger = logging.getLogger(__name__)

_app = None


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def _resolve_path(path):
    """
    Resolve a service-account path to an absolute path.

    Tries (in order):
      1. The path as-is (absolute or resolvable from the CWD)
      2. The path resolved against Django's BASE_DIR
      3. `backend/` prefixed versions of the path (covers running from the
         repo root while BASE_DIR is the backend directory)
    """
    if not path:
        return None

    candidates = [
        path,
        os.path.join(str(settings.BASE_DIR), path),
    ]
    # If path starts with 'backend/', also try stripping it (run from backend/)
    if path.startswith('backend/'):
        candidates.append(os.path.join(str(settings.BASE_DIR), path[len('backend/'):]))
    # If path does NOT start with 'backend/', also try adding it (run from repo root)
    if not path.startswith('backend/'):
        candidates.append(os.path.join(str(settings.BASE_DIR).rsplit(os.sep, 1)[0], 'backend', path))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)

    return None


def _load_credentials():
    """Load service-account credentials from settings."""
    path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_PATH', '')
    json_str = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_JSON', '')

    if path:
        if not isinstance(path, str) or not path.strip():
            return None
        if path.strip().startswith('{'):
            # Raw JSON passed via the PATH setting (defensive)
            try:
                return credentials.Certificate(json.loads(path))
            except Exception:
                return None
        resolved = _resolve_path(path)
        if resolved is None:
            logger.warning(
                'FIREBASE_SERVICE_ACCOUNT_PATH does not exist or is not a file: %s '
                '(searched CWD and BASE_DIR)', path
            )
            return None
        return credentials.Certificate(resolved)

    if json_str:
        try:
            if isinstance(json_str, str):
                json_str = json.loads(json_str)
            return credentials.Certificate(json_str)
        except Exception as e:
            logger.warning('Invalid FIREBASE_SERVICE_ACCOUNT_JSON: %s', e)
            return None

    return None


def _get_app():
    """Lazily initialise and return the Firebase Admin app."""
    global _app
    if _app is not None:
        return _app

    try:
        # Already initialised (e.g. by another part of the app)
        import firebase_admin
        return firebase_admin.get_app(_DEFAULT_APP_NAME)
    except ValueError:
        pass

    cred = _load_credentials()
    if cred is None:
        logger.warning(
            'Firebase Admin SDK not configured. Set FIREBASE_SERVICE_ACCOUNT_PATH '
            'or FIREBASE_SERVICE_ACCOUNT_JSON in the environment. Notifications '
            'will still be stored in the database but NOT delivered via push.'
        )
        _app = False  # Cache the failure so we don't retry every send
        return None

    try:
        _app = initialize_app(credential=cred)
        logger.info('Firebase Admin SDK initialised')
    except Exception as e:
        logger.error('Failed to initialise Firebase Admin SDK: %s', e)
        _app = False
        return None

    return _app if _app is not False else None


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def _build_notification_payload(notification):
    """Build the FCM Notification object for display."""
    return messaging.Notification(
        title=notification.title,
        body=notification.message,
        image=notification.image_url or None,
    )


def _build_data_payload(notification, extra=None):
    """Build the FCM data payload for a notification (deep-link metadata)."""
    payload = {
        'id': str(notification.id),
        'type': notification.notification_type,
        'category': notification.category,
        'title': notification.title,
        'body': notification.message,
        'target_screen': notification.target_screen or '',
        'target_id': notification.target_id or '',
        'image_url': notification.image_url or '',
        'priority': notification.priority,
        'timestamp': notification.created_at.isoformat(),
    }
    if extra:
        payload.update(extra)
    # FCM data values must be strings
    return {k: (str(v) if v is not None else '') for k, v in payload.items()}


def _android_config(notification):
    """Android-specific config with priority."""
    from firebase_admin.messaging import AndroidConfig, AndroidNotification

    priority = 'normal'
    if notification.priority in ('high', 'urgent'):
        priority = 'high'

    return AndroidConfig(
        priority=priority,
        notification=AndroidNotification(
            sound='default',
            channel_id='alara_high_importance',
            default_vibrate_timings=True,
        ),
    )


def _apns_config(notification):
    from firebase_admin.messaging import APNSConfig, APNSPayload, Aps

    return APNSConfig(
        payload=APNSPayload(
            aps=Aps(
                alert=notification.title,
                sound='default',
                badge=1,
                content_available=True,
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Delivery functions
# ---------------------------------------------------------------------------

def send_to_device(notification, device, extra_data=None):
    """Send a push notification to a single device via the Admin SDK."""
    app = _get_app()
    if app is None:
        return False

    message = messaging.Message(
        token=device.fcm_token,
        notification=_build_notification_payload(notification),
        data=_build_data_payload(notification, extra_data),
        android=_android_config(notification),
        apns=_apns_config(notification),
    )

    try:
        response = messaging.send(message, app=app)
        logger.debug('FCM message sent to device %s: %s', device.id, response)
        return True
    except messaging.UnregisteredError:
        # Token no longer valid — deactivate it
        device.is_active = False
        device.save(update_fields=['is_active'])
        logger.info('Deactivated unregistered FCM token for device %s', device.id)
        return False
    except messaging.SenderIdMismatchError:
        device.is_active = False
        device.save(update_fields=['is_active'])
        logger.info('Deactivated mismatched FCM token for device %s', device.id)
        return False
    except messaging.InvalidArgumentError as e:
        # Malformed token — deactivate
        device.is_active = False
        device.save(update_fields=['is_active'])
        logger.info('Deactivated invalid FCM token for device %s: %s', device.id, e)
        return False
    except (FirebaseError, ValueError) as e:
        logger.error('FCM send failed for device %s: %s', device.id, e)
        return False


def send_to_user(notification, user, extra_data=None):
    """Send push notification to all active devices of a user."""
    devices = Device.objects.filter(user=user, is_active=True)
    if not devices.exists():
        logger.debug('No active devices for user %s', user.id)
        return 0

    sent_count = 0
    for device in devices:
        if send_to_device(notification, device, extra_data):
            sent_count += 1
    return sent_count


def send_to_multiple_users(notification, user_ids, extra_data=None):
    """Send a notification to multiple users by their IDs."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    devices = Device.objects.filter(
        user_id__in=user_ids, is_active=True
    ).select_related('user')

    if not devices.exists():
        logger.debug('No active devices for any of the %s users', len(user_ids))
        return 0

    sent_count = 0
    for device in devices:
        if send_to_device(notification, device, extra_data):
            sent_count += 1
    return sent_count


def send_to_topic(topic, notification, extra_data=None):
    """Send a notification to an FCM topic via the Admin SDK."""
    app = _get_app()
    if app is None:
        return False

    message = messaging.Message(
        topic=topic,
        notification=_build_notification_payload(notification),
        data=_build_data_payload(notification, extra_data),
        android=_android_config(notification),
        apns=_apns_config(notification),
    )

    try:
        response = messaging.send(message, app=app)
        logger.debug('FCM topic message sent to %s: %s', topic, response)
        return True
    except (FirebaseError, ValueError) as e:
        logger.error('FCM topic send failed for %s: %s', topic, e)
        return False
