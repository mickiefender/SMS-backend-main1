"""
Firebase Cloud Messaging service — sends push notifications to devices.

Uses FCM legacy HTTP API to deliver notifications to individual devices
or topics. Automatically deactivates invalid FCM tokens.
"""
import logging
import requests
from django.conf import settings

from apps.notifications.models import Device

logger = logging.getLogger(__name__)

FCM_SEND_URL = 'https://fcm.googleapis.com/fcm/send'

FCM_PRIORITY_MAP = {
    'low': 'normal',
    'normal': 'high',
    'high': 'high',
    'urgent': 'high',
}


def _get_fcm_key():
    key = getattr(settings, 'FCM_SERVER_KEY', '')
    if not key:
        logger.warning('FCM_SERVER_KEY not configured — push will not be sent')
    return key


def _build_headers():
    key = _get_fcm_key()
    if not key:
        return None
    return {
        'Authorization': f'key={key}',
        'Content-Type': 'application/json',
    }


def _build_data_payload(notification, extra=None):
    """Build the FCM data payload for a notification."""
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
    return payload


def _build_notification_payload(notification):
    """Build the notification display payload for FCM."""
    return {
        'title': notification.title,
        'body': notification.message,
        'sound': 'default',
        'badge': '1',
    }


def send_to_device(notification, device, extra_data=None):
    """Send a push notification to a single device via FCM."""
    headers = _build_headers()
    if not headers:
        return False

    payload = {
        'to': device.fcm_token,
        'priority': FCM_PRIORITY_MAP.get(notification.priority, 'high'),
        'notification': _build_notification_payload(notification),
        'data': _build_data_payload(notification, extra_data),
    }

    try:
        response = requests.post(FCM_SEND_URL, headers=headers, json=payload, timeout=10)
        result = response.json()

        if response.status_code == 200:
            if result.get('failure', 0) > 0:
                if 'results' in result:
                    res = result['results'][0]
                    error = res.get('error', '')
                    if error in ('InvalidRegistration', 'NotRegistered', 'MismatchSenderId'):
                        device.is_active = False
                        device.save(update_fields=['is_active'])
                        logger.info(f'Deactivated invalid FCM token for device {device.id}: {error}')
                return False
            return True
        return False
    except requests.RequestException as e:
        logger.error(f'FCM send failed for device {device.id}: {e}')
        return False


def send_to_user(notification, user, extra_data=None):
    """Send push notification to all active devices of a user."""
    devices = Device.objects.filter(user=user, is_active=True)
    if not devices.exists():
        logger.debug(f'No active devices for user {user.id}')
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
        logger.debug(f'No active devices for any of the {len(user_ids)} users')
        return 0

    sent_count = 0
    for device in devices:
        if send_to_device(notification, device, extra_data):
            sent_count += 1
    return sent_count


def send_to_topic(topic, notification, extra_data=None):
    """Send a notification to an FCM topic (e.g. all_users, role_teacher)."""
    headers = _build_headers()
    if not headers:
        return False

    payload = {
        'to': f'/topics/{topic}',
        'priority': FCM_PRIORITY_MAP.get(notification.priority, 'high'),
        'notification': _build_notification_payload(notification),
        'data': _build_data_payload(notification, extra_data),
    }

    try:
        response = requests.post(FCM_SEND_URL, headers=headers, json=payload, timeout=15)
        return response.status_code == 200
    except requests.RequestException as e:
        logger.error(f'FCM topic send failed for {topic}: {e}')
        return False
