from django.urls import path
from .views import ChatSessionDetailView, ChatSessionListView


urlpatterns = [
    path('sessions/', ChatSessionListView.as_view(), name='ai-chat-sessions'),
    path('sessions/<str:session_id>/', ChatSessionDetailView.as_view(), name='ai-chat-session-detail'),
]
