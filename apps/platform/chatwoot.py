"""Server-side Chatwoot API proxy for the Alara Help inbox."""
import logging
import os
from urllib.parse import urljoin

import requests
from rest_framework.exceptions import APIException, NotFound, ValidationError

logger = logging.getLogger(__name__)


class ChatwootConfigurationError(APIException):
    status_code = 503
    default_detail = 'Chatwoot support is not configured.'
    default_code = 'chatwoot_not_configured'


class ChatwootUpstreamError(APIException):
    status_code = 502
    default_detail = 'Chatwoot could not complete the request.'
    default_code = 'chatwoot_upstream_error'


def _configuration():
    names = (
        'CHATWOOT_BASE_URL',
        'CHATWOOT_API_TOKEN',
        'CHATWOOT_ACCOUNT_ID',
        'CHATWOOT_INBOX_ID',
    )
    values = {name: os.environ.get(name, '').strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ChatwootConfigurationError(
            detail=(
                'Chatwoot support is not configured. Set the following Django '
                f'environment variable(s): {", ".join(missing)}.'
            )
        )

    return (
        values['CHATWOOT_BASE_URL'].rstrip('/'),
        values['CHATWOOT_API_TOKEN'],
        values['CHATWOOT_ACCOUNT_ID'],
        values['CHATWOOT_INBOX_ID'],
    )


def _request(method, path, params=None, payload=None):
    base_url, api_token, _, _ = _configuration()
    url = urljoin(f'{base_url}/', path.lstrip('/'))

    try:
        response = requests.request(
            method,
            url,
            headers={
                'api_access_token': api_token,
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            params=params,
            json=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        raise ChatwootUpstreamError(
            detail='Could not connect to the Chatwoot support service.'
        ) from exc

    if response.status_code == 404:
        raise NotFound('The Chatwoot conversation was not found.')
    if not response.ok:
        upstream_detail = _get_upstream_error_detail(response)
        logger.warning(
            'Chatwoot request failed: method=%s path=%s status=%s detail=%s',
            method,
            path,
            response.status_code,
            upstream_detail.replace(api_token, '[REDACTED]'),
        )
        raise ChatwootUpstreamError(
            detail=(
                f'Chatwoot returned HTTP {response.status_code}'
                + (
                    f': {upstream_detail.replace(api_token, "[REDACTED]")}'
                    if upstream_detail else '.'
                )
            )
        )

    if response.status_code == 204 or not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise ChatwootUpstreamError(
            detail='Chatwoot returned an invalid response.'
        ) from exc


def _get_upstream_error_detail(response):
    """Extract a bounded, non-secret error description from Chatwoot."""
    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    if isinstance(payload, dict):
        payload = (
            payload.get('message')
            or payload.get('error')
            or payload.get('errors')
            or payload.get('detail')
        )
    if isinstance(payload, (dict, list)):
        from json import dumps
        detail = dumps(payload, ensure_ascii=True)
    elif payload is not None:
        detail = str(payload).strip()
    else:
        detail = ''
    return detail[:500]


def list_conversations(page=1, status_filter='all'):
    _, _, account_id, inbox_id = _configuration()
    params = {
        'status': status_filter,
        'page': page,
        'assignee_type': 'all',
    }
    params['inbox_id'] = inbox_id
    return _request(
        'GET',
        f'/api/v1/accounts/{account_id}/conversations',
        params=params,
    )


def _ensure_alara_conversation(conversation_id):
    _, _, account_id, inbox_id = _configuration()
    conversation = _request(
        'GET',
        f'/api/v1/accounts/{account_id}/conversations/{conversation_id}',
    )
    if isinstance(conversation, dict) and isinstance(conversation.get('payload'), dict):
        conversation = conversation['payload']
    if not isinstance(conversation, dict):
        raise ChatwootUpstreamError(detail='Chatwoot returned an invalid conversation.')
    conversation_inbox_id = conversation.get('inbox_id')
    if conversation_inbox_id is None:
        conversation_inbox_id = (
            conversation.get('meta', {}).get('inbox', {}).get('id')
            if isinstance(conversation.get('meta'), dict)
            else None
        )
    if str(conversation_inbox_id) != inbox_id:
        raise NotFound('The Chatwoot conversation was not found in the Alara Help inbox.')


def get_messages(conversation_id):
    _, _, account_id, _ = _configuration()
    _ensure_alara_conversation(conversation_id)
    return _request(
        'GET',
        f'/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages',
    )


def send_reply(conversation_id, content):
    content = content.strip() if isinstance(content, str) else ''
    if not content:
        raise ValidationError({'content': 'A reply message is required.'})
    if len(content) > 10000:
        raise ValidationError({'content': 'The reply must be 10,000 characters or fewer.'})

    _, _, account_id, _ = _configuration()
    _ensure_alara_conversation(conversation_id)
    return _request(
        'POST',
        f'/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages',
        payload={
            'content': content,
            'message_type': 'outgoing',
            'private': False,
            'content_type': 'text',
        },
    )


def update_conversation_status(conversation_id, status):
    if status not in ('open', 'resolved'):
        raise ValidationError({'status': 'Status must be open or resolved.'})

    _, _, account_id, _ = _configuration()
    _ensure_alara_conversation(conversation_id)
    return _request(
        'POST',
        f'/api/v1/accounts/{account_id}/conversations/{conversation_id}/toggle_status',
        payload={'status': status},
    )
