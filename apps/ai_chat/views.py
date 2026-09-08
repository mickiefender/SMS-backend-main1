from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChatSession
from .serializers import ChatSessionSerializer


class ChatSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def _allowed(self, request):
        return request.user.role in ('student', 'teacher')

    def get(self, request):
        if not self._allowed(request):
            return Response({'error': 'AI chat history is unavailable for this account.'}, status=status.HTTP_403_FORBIDDEN)
        sessions = ChatSession.objects.filter(user=request.user)
        return Response(ChatSessionSerializer(sessions, many=True).data)

    def post(self, request):
        if not self._allowed(request):
            return Response({'error': 'AI chat history is unavailable for this account.'}, status=status.HTTP_403_FORBIDDEN)
        session_id = str(request.data.get('id', '')).strip()
        if not session_id:
            return Response({'error': 'id is required'}, status=status.HTTP_400_BAD_REQUEST)

        payload = request.data.copy()
        payload.pop('id', None)
        title = str(payload.get('title', 'Untitled Session'))[:255]
        created_at = int(payload.get('createdAt', 0))
        updated_at = int(payload.get('updatedAt', created_at))

        session, _ = ChatSession.objects.update_or_create(
            id=session_id,
            user=request.user,
            defaults={
                'title': title,
                'payload': payload,
                'created_at': created_at,
                'updated_at': updated_at,
            },
        )
        return Response(ChatSessionSerializer(session).data, status=status.HTTP_200_OK)

    def delete(self, request):
        if not self._allowed(request):
            return Response({'error': 'AI chat history is unavailable for this account.'}, status=status.HTTP_403_FORBIDDEN)
        ChatSession.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id):
        if request.user.role not in ('student', 'teacher'):
            return Response({'error': 'AI chat history is unavailable for this account.'}, status=status.HTTP_403_FORBIDDEN)
        deleted, _ = ChatSession.objects.filter(
            id=session_id,
            user=request.user,
        ).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
