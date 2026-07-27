"""
API view for Cloudflare Stream direct creator upload.

The Flutter app calls this endpoint to get a one-time upload URL.
The app then uploads the video directly to Cloudflare Stream,
bypassing nginx (which has a small client_max_body_size limit).

After the upload completes, the app calls /api/feed/lesson/ with
the cloudflare_video_uid to create the lesson metadata.
"""
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.feed.services.cloudflare_stream_service import (
    CloudflareStreamService,
    CloudflareStreamError,
)

logger = logging.getLogger(__name__)


class DirectUploadUrlView(APIView):
    """
    POST /api/feed/direct-upload-url/

    Returns a one-time upload URL for Cloudflare Stream direct creator upload.
    The Flutter app uploads the video directly to this URL, bypassing nginx.

    Response:
      {
        "upload_url": "https://upload...",   # ← POST video bytes here
        "video_uid": "abc123...",            # ← save this for later
      }

    Usage (Flutter):
      1. POST to /api/feed/direct-upload-url/ → get upload_url + video_uid
      2. PUT video bytes to upload_url
      3. POST to /api/feed/lesson/ with cloudflare_video_uid = video_uid
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        max_duration_seconds = request.data.get('max_duration_seconds', 600)

        try:
            cf_service = CloudflareStreamService()
            result = cf_service.create_direct_upload_url(
                max_duration_seconds=max_duration_seconds,
            )
        except CloudflareStreamError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            'upload_url': result['upload_url'],
            'video_uid': result['uid'],
        })
