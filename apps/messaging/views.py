from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from core.permissions import IsSchoolAdminOrHigher, IsTeacher, IsStudent
from .models import Message, Announcement, AnnouncementRead, Notice
from .serializers import MessageSerializer, AnnouncementSerializer, AnnouncementReadSerializer, NoticeSerializer


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if self.action == 'list':
            # Show received messages by default
            return Message.objects.filter(recipient=user).order_by('-created_at')
        return Message.objects.filter(Q(sender=user) | Q(recipient=user))

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    @action(detail=False, methods=['get'])
    def sent(self, request):
        """Get sent messages"""
        messages = Message.objects.filter(sender=request.user).order_by('-created_at')
        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a message as read"""
        message = self.get_object()
        if message.recipient == request.user:
            message.is_read = True
            message.save()
            return Response({'status': 'marked as read'})
        return Response({'error': 'Unauthorized'}, status=403)


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'super_admin':
            return Announcement.objects.all()
        
        # School admins see all announcements in their school
        if user.role == 'school_admin':
            return Announcement.objects.filter(school=user.school)
        
        # Teachers and students see published announcements in their school
        return Announcement.objects.filter(
            school=user.school,
            status='published'
        )

    def perform_create(self, serializer):
        try:
            serializer.save(school=self.request.user.school, created_by=self.request.user)
        except Exception as e:
            print(f"[v0] Error in AnnouncementViewSet.perform_create: {e}")
            serializer.save(school=self.request.user.school, created_by=None)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish an announcement"""
        announcement = self.get_object()
        announcement.status = 'published'
        announcement.published_date = timezone.now()
        announcement.save()
        return Response({'status': 'announcement published'})

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark announcement as read by current user"""
        announcement = self.get_object()
        AnnouncementRead.objects.get_or_create(announcement=announcement, user=request.user)
        return Response({'status': 'marked as read'})

    @action(detail=True, methods=['get'])
    def read_by(self, request, pk=None):
        """Get list of users who read this announcement"""
        announcement = self.get_object()
        reads = AnnouncementRead.objects.filter(announcement=announcement)
        serializer = AnnouncementReadSerializer(reads, many=True)
        return Response(serializer.data)


class NoticeViewSet(viewsets.ModelViewSet):
    serializer_class = NoticeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'super_admin':
            return Notice.objects.all()
        
        # School admins see all notices in their school
        if user.role == 'school_admin':
            return Notice.objects.filter(school=user.school).order_by('-is_pinned', '-created_at')
        
        # Teachers and students see active notices in their school
        now = timezone.now()
        return Notice.objects.filter(
            school=user.school,
            expiry_date__isnull=True
        ) | Notice.objects.filter(
            school=user.school,
            expiry_date__gt=now
        )

    def perform_create(self, serializer):
        try:
            serializer.save(school=self.request.user.school, created_by=self.request.user)
        except Exception as e:
            print(f"[v0] Error in NoticeViewSet.perform_create: {e}")
            serializer.save(school=self.request.user.school, created_by=None)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        """Pin a notice"""
        notice = self.get_object()
        notice.is_pinned = not notice.is_pinned
        notice.save()
        return Response({'status': f"notice {'pinned' if notice.is_pinned else 'unpinned'}"})
