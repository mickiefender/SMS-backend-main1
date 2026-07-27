"""
Cloudflare Stream service.

Uploads videos to Cloudflare Stream and retrieves playback metadata.

Cloudflare Stream becomes the ONLY place videos are stored. The Flutter app
never downloads MP4 files — it uses HLS/DASH playback URLs from Cloudflare.

Upload flow:
  1. Django receives the video file from Flutter (multipart upload to DRF)
  2. Django uploads the raw bytes to Cloudflare Stream via their API
  3. Cloudflare returns a video UID; Django polls until processing is done
  4. Cloudflare provides: playback URL (HLS), thumbnail URL, duration
  5. Django stores these on FeedLesson.cloudflare_* fields
  6. Flutter receives only the playback URL and thumbnail URL
"""
import logging
import time
import requests
from typing import Optional, Dict, Any
from urllib.parse import urljoin

from django.conf import settings

logger = logging.getLogger(__name__)


class CloudflareStreamError(Exception):
    """Raised when a Cloudflare Stream API call fails."""
    pass


class CloudflareStreamService:
    """Handles video upload to and metadata retrieval from Cloudflare Stream."""

    API_BASE = 'https://api.cloudflare.com/client/v4'

    def __init__(self):
        self.account_id = getattr(settings, 'CLOUDFLARE_STREAM_ACCOUNT_ID', '')
        self.api_token = getattr(settings, 'CLOUDFLARE_STREAM_API_TOKEN', '')
        self.signing_key = getattr(settings, 'CLOUDFLARE_STREAM_SIGNING_KEY', '')

        if not self.account_id or not self.api_token:
            raise CloudflareStreamError(
                'CLOUDFLARE_STREAM_ACCOUNT_ID and CLOUDFLARE_STREAM_API_TOKEN '
                'must be configured in settings.'
            )

        self._headers = {
            'Authorization': f'Bearer {self.api_token}',
        }

    def _api_url(self, path: str) -> str:
        """Build a full Cloudflare Stream API URL."""
        base = f'{self.API_BASE}/accounts/{self.account_id}/stream'
        return urljoin(base + '/', path.lstrip('/'))

    # ------------------------------------------------------------------
    # Upload: send raw video bytes to Cloudflare Stream
    # ------------------------------------------------------------------

    def upload_video(
        self,
        video_data: bytes,
        filename: str = 'video.mp4',
        mime_type: str = 'video/mp4',
        max_poll_seconds: int = 0,
        poll_interval: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Upload a video file to Cloudflare Stream.

        Cloudflare Stream's simple upload API expects the file as a
        multipart/form-data POST to the /stream endpoint.

        By default (max_poll_seconds=0) this method returns immediately
        after Cloudflare accepts the upload — it does NOT wait for
        transcoding.  The caller gets back a minimal result with the UID
        and status='queued'.  A background task should poll via
        poll_until_ready() later.

        If max_poll_seconds > 0, the method blocks and polls until the
        video is ready (or the timeout expires).

        Returns a dict with:
          - uid: Cloudflare video UID
          - playback_url: HLS manifest URL (empty if not yet ready)
          - thumbnail_url: thumbnail URL (empty if not yet ready)
          - duration: video duration in seconds (0 if not yet ready)
          - status: 'queued' | 'ready' | 'error'
          - error_message: human-readable error if any
        """
        url = self._api_url('')
        logger.info(
            'Uploading %s (%d bytes) to Cloudflare Stream…',
            filename, len(video_data),
        )

        try:
            files = {
                'file': (filename, video_data, mime_type),
            }
            resp = requests.post(
                url,
                headers=self._headers,
                files=files,
                timeout=600,
            )
        except requests.RequestException as exc:
            raise CloudflareStreamError(f'Upload request failed: {exc}') from exc

        if resp.status_code != 200:
            body = resp.text
            try:
                body = resp.json()
            except ValueError:
                pass
            raise CloudflareStreamError(
                f'Cloudflare Stream upload failed (HTTP {resp.status_code}): {body}'
            )

        result = resp.json()
        if not result.get('success'):
            errors = result.get('errors', [])
            raise CloudflareStreamError(
                f'Cloudflare Stream upload returned errors: {errors}'
            )

        video_uid = result['result']['uid']
        logger.info('Video uploaded to Cloudflare Stream — UID: %s', video_uid)

        # If caller doesn't want to wait, return immediately with just the UID
        if max_poll_seconds <= 0:
            return {
                'uid': video_uid,
                'status': 'queued',
                'playback_url': None,
                'thumbnail_url': None,
                'duration': 0,
                'error_message': '',
            }

        # Poll until the video is ready
        return self.poll_until_ready(video_uid, max_poll_seconds, poll_interval)

    # ------------------------------------------------------------------
    # Upload via URL (alternative — Cloudflare fetches from a URL)
    # ------------------------------------------------------------------

    def upload_from_url(
        self,
        source_url: str,
        meta: Optional[Dict[str, Any]] = None,
        max_poll_seconds: int = 300,
        poll_interval: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Upload a video by asking Cloudflare to fetch it from *source_url*.

        Useful when the video is already hosted somewhere temporary.
        """
        url = self._api_url('copy')
        body = {
            'url': source_url,
            'meta': meta or {},
        }

        try:
            resp = requests.post(url, headers=self._headers, json=body, timeout=30)
        except requests.RequestException as exc:
            raise CloudflareStreamError(f'Copy-from-URL request failed: {exc}') from exc

        if resp.status_code != 200:
            raise CloudflareStreamError(
                f'Cloudflare Stream copy-from-URL failed (HTTP {resp.status_code}): {resp.text}'
            )

        result = resp.json()
        if not result.get('success'):
            raise CloudflareStreamError(
                f'Cloudflare Stream copy errors: {result.get("errors")}'
            )

        video_uid = result['result']['uid']
        logger.info('Cloudflare fetching video from %s — UID: %s', source_url, video_uid)

        return self.poll_until_ready(video_uid, max_poll_seconds, poll_interval)

    # ------------------------------------------------------------------
    # Check if a video info response is playable
    # ------------------------------------------------------------------

    @staticmethod
    def _video_is_playable(video_info: Dict[str, Any]) -> bool:
        """
        Check whether a Cloudflare Stream video is playable.

        Cloudflare returns state "ready" when fully transcoded, but often
        provides the HLS playback URL **immediately** even in states like
        "unknown" or "inprogress".  The video is playable as soon as the
        HLS manifest URL appears in the response.

        We consider the video playable when:
        - ``playback.hls`` or ``playback.dash`` is a non-empty string.
        """
        playback = video_info.get('playback', {}) or {}
        return bool(playback.get('hls') or playback.get('dash'))

    # ------------------------------------------------------------------
    # Poll until the video is processed and ready
    # ------------------------------------------------------------------

    def poll_until_ready(
        self,
        video_uid: str,
        max_seconds: int = 300,
        interval: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Poll Cloudflare Stream's video status endpoint until the video is
        ready for playback or an error occurs.

        **Important**: Cloudflare Stream makes the HLS playback URL available
        almost immediately — even before full transcoding is complete (the
        video state may be "unknown" or "inprogress" while the playback URL
        is already valid).  We therefore check for the *presence of a
        playback URL* as our readiness signal, not just the ``ready`` state.
        """
        started = time.time()
        last_state = 'queued'

        while time.time() - started < max_seconds:
            info = self.get_video_info(video_uid)
            state = info.get('state', 'unknown')

            if state != last_state:
                logger.info('Video %s state changed: %s → %s', video_uid, last_state, state)
                last_state = state

            # Ready if Cloudflare says so, OR if the HLS playback URL is
            # already present (Cloudflare often provides it before reaching
            # the "ready" state).
            if state == 'ready' or self._video_is_playable(info):
                return self._build_result(info)

            if state in ('error', 'deleted', 'failed'):
                err_msg = info.get('errorMessage', info.get('errormessage', 'Unknown error'))
                logger.error('Video %s processing failed: %s', video_uid, err_msg)
                return {
                    'uid': video_uid,
                    'status': 'error',
                    'error_message': err_msg,
                    'playback_url': None,
                    'thumbnail_url': None,
                    'duration': 0,
                }

            time.sleep(interval)

        # ── Timeout — do one final check for a playback URL ──
        # Even after timeout, the video might have a playback URL.
        # This catches the edge case where the HLS URL appeared between
        # the last poll and the timeout check.
        try:
            info = self.get_video_info(video_uid)
            if self._video_is_playable(info):
                logger.info(
                    'Video %s recovered after timeout — playback URL found on final check',
                    video_uid,
                )
                return self._build_result(info)
        except Exception:
            pass

        logger.warning(
            'Video %s did not become ready within %ds — giving up',
            video_uid, max_seconds,
        )
        return {
            'uid': video_uid,
            'status': 'pending',
            'error_message': f'Processing did not complete within {max_seconds}s',
            'playback_url': None,
            'thumbnail_url': None,
            'duration': 0,
        }

    # ------------------------------------------------------------------
    # Get video info
    # ------------------------------------------------------------------

    def get_video_info(self, video_uid: str) -> Dict[str, Any]:
        """
        Return the full video object from Cloudflare Stream.

        See: https://developers.cloudflare.com/api/operations/stream-videos-list-videos
        """
        url = self._api_url(video_uid)
        try:
            resp = requests.get(url, headers=self._headers, timeout=15)
        except requests.RequestException as exc:
            raise CloudflareStreamError(f'Get video info failed: {exc}') from exc

        if resp.status_code != 200:
            raise CloudflareStreamError(
                f'Get video info failed (HTTP {resp.status_code}): {resp.text}'
            )

        result = resp.json()
        if not result.get('success'):
            raise CloudflareStreamError(
                f'Cloudflare API get-video errors: {result.get("errors")}'
            )

        return result['result']

    # ------------------------------------------------------------------
    # Generate a signed URL (optional — for private videos)
    # ------------------------------------------------------------------

    def get_signed_playback_url(
        self,
        video_uid: str,
        expires_seconds: int = 3600,
    ) -> Optional[str]:
        """
        Generate a signed HLS manifest URL using Cloudflare's signing key.

        Only works if CLOUDFLARE_STREAM_SIGNING_KEY is configured and
        the video requires signed URLs.
        """
        signing_key = self.signing_key
        if not signing_key:
            logger.warning('CLOUDFLARE_STREAM_SIGNING_KEY not set — cannot generate signed URL')
            return None

        import jwt
        from datetime import datetime, timedelta

        payload = {
            'sub': video_uid,
            'kid': signing_key[:40],  # first 40 chars as key id
            'exp': int((datetime.utcnow() + timedelta(seconds=expires_seconds)).timestamp()),
            'nbf': int(datetime.utcnow().timestamp()),
        }

        token = jwt.encode(payload, signing_key, algorithm='HS256')

        # The signed URL format:
        # https://customer-{customer_code}.cloudflarestream.com/{token}/manifest/video.m3u8
        customer_code = self._get_customer_code()
        return (
            f'https://customer-{customer_code}.cloudflarestream.com/'
            f'{token}/manifest/video.m3u8'
        )

    # ------------------------------------------------------------------
    # Delete a video
    # ------------------------------------------------------------------

    def delete_video(self, video_uid: str) -> bool:
        """Delete a video from Cloudflare Stream."""
        url = self._api_url(video_uid)
        try:
            resp = requests.delete(url, headers=self._headers, timeout=15)
        except requests.RequestException as exc:
            logger.error('Delete video %s failed: %s', video_uid, exc)
            return False

        if resp.status_code not in (200, 204):
            logger.warning('Delete video %s returned HTTP %d', video_uid, resp.status_code)
            return False

        return True

    # ------------------------------------------------------------------
    # Direct creator upload (bypasses nginx for large files)
    # ------------------------------------------------------------------

    def create_direct_upload_url(
        self,
        max_duration_seconds: int = 600,
    ) -> Dict[str, str]:
        """
        Get a one-time upload URL from Cloudflare Stream.

        The Flutter app should PUT/POST the video file directly to the
        returned ``upload_url``, bypassing the Django server's nginx.

        Returns:
          {
            "upload_url": "https://upload.videodelivery.net/...",
            "uid": "abc123...",
          }
        """
        url = self._api_url('direct_upload')
        body = {
            'maxDurationSeconds': max_duration_seconds,
        }

        try:
            resp = requests.post(url, headers=self._headers, json=body, timeout=15)
        except requests.RequestException as exc:
            raise CloudflareStreamError(f'Direct upload request failed: {exc}') from exc

        if resp.status_code != 200:
            raise CloudflareStreamError(
                f'Cloudflare direct upload failed (HTTP {resp.status_code}): {resp.text}'
            )

        result = resp.json()
        if not result.get('success'):
            raise CloudflareStreamError(
                f'Cloudflare direct upload errors: {result.get("errors")}'
            )

        return {
            'upload_url': result['result']['uploadURL'],
            'uid': result['result']['uid'],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_result(video_info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the fields we care about from a full Cloudflare video object."""
        uid = video_info.get('uid', '')
        status = video_info.get('state', 'unknown')

        # Playback URLs — prefer HLS manifest, fall back to DASH
        playback = video_info.get('playback', {}) or {}
        hls_url = playback.get('hls') or playback.get('dash') or ''

        # Thumbnail URL — Cloudflare provides this immediately on the video
        # info endpoint, or we construct the default template URL.
        thumbnail = video_info.get('thumbnail', '')
        if not thumbnail and uid:
            thumbnail = (
                f'https://customer-'
                f'{CloudflareStreamService._get_customer_code_from_info(video_info)}'
                f'.cloudflarestream.com/{uid}/thumbnails/thumbnail.jpg'
            )

        # Duration — available from the input metadata even before transcoding
        duration = float(video_info.get('duration', 0) or 0)
        if duration <= 0:
            duration = float(video_info.get('input', {}).get('duration', 0) or 0)

        logger.info(
            'Cloudflare video %s — status=%s, playback=%s, thumb=%s, duration=%.1f',
            uid, status,
            hls_url[:80] + '…' if len(hls_url) > 80 else hls_url,
            thumbnail[:80] + '…' if len(thumbnail) > 80 else thumbnail,
            duration,
        )

        return {
            'uid': uid,
            'status': status,
            'playback_url': hls_url,
            'thumbnail_url': thumbnail,
            'duration': duration,
            'error_message': video_info.get('errorMessage', ''),
        }

    @staticmethod
    def _get_customer_code_from_info(video_info: Dict[str, Any]) -> str:
        """Try to extract customer code from video info (e.g. from thumbnail URL)."""
        thumb = video_info.get('thumbnail', '')
        if thumb and 'customer-' in thumb:
            # https://customer-xxxxx.cloudflarestream.com/...
            parts = thumb.split('/')
            for part in parts:
                if part.startswith('customer-'):
                    return part.replace('customer-', '')
        return ''

    def _get_customer_code(self) -> str:
        """
        Retrieve the customer subdomain code by calling the Stream API.
        Cached per instance.
        """
        if hasattr(self, '_customer_code'):
            return self._customer_code

        # The customer code is embedded in the API response or can be derived.
        # For simplicity we fetch the first video's thumbnail to extract it.
        # In practice, you'd set CLOUDFLARE_STREAM_CUSTOMER_CODE in settings.
        try:
            url = self._api_url('')
            resp = requests.get(url, headers=self._headers, params={'per_page': 1}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                videos = (data.get('result') or [])
                if videos and isinstance(videos, list):
                    code = self._get_customer_code_from_info(videos[0])
                    if code:
                        self._customer_code = code
                        return code
        except Exception as exc:
            logger.warning('Could not determine customer code from Stream API: %s', exc)

        # Fallback — if the user configured it directly
        self._customer_code = getattr(settings, 'CLOUDFLARE_STREAM_CUSTOMER_CODE', '')
        return self._customer_code
