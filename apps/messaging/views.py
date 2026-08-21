from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth import get_user_model
from core.permissions import IsSchoolAdminOrHigher, IsTeacher, IsStudent
from .models import Message, Announcement, AnnouncementRead, Notice, PersonalNotice
from .serializers import MessageSerializer, AnnouncementSerializer, AnnouncementReadSerializer, NoticeSerializer, PersonalNoticeSerializer
from .tasks import (
    send_notice_email, send_announcement_email, send_personal_notice_email,
    send_notice_push, send_announcement_push, send_personal_notice_push,
)

User = get_user_model()


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
        """Create announcement and send emails when published"""
        print(f"[v0] Creating announcement. User ID: {self.request.user.pk}, Exists: {User.objects.filter(pk=self.request.user.pk).exists()}")
        
        # Always save without created_by first to avoid FK constraint issues
        # created_by is read_only in serializer anyway
        announcement = serializer.save(school=self.request.user.school)
        
        # Try to set created_by if user exists in DB
        try:
            if User.objects.filter(pk=self.request.user.pk).exists():
                announcement.created_by = self.request.user
                announcement.save(update_fields=['created_by'])
                print(f"[v0] Set created_by to user {self.request.user.pk}")
            else:
                print(f"[v0] User {self.request.user.pk} does not exist in database, created_by will be NULL")
        except Exception as e:
            print(f"[v0] Error setting created_by: {e}")
        
        # Auto-publish on create (align with Notice)
        announcement.status = 'published'
        announcement.published_date = timezone.now()
        announcement.save(update_fields=['status', 'published_date'])

        # Queue email + in-app/FCM push delivery to the resolved recipients
        # (audience flags + individually targeted recipients).
        send_announcement_email.delay(announcement.id)
        send_announcement_push.delay(announcement.id)
        print(f"[v0] Auto-published announcement {announcement.id}; email + push queued")

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish an announcement and send emails + push"""
        announcement = self.get_object()
        announcement.status = 'published'
        announcement.published_date = timezone.now()
        announcement.save()

        # Send emails + push asynchronously
        send_announcement_email.delay(announcement.id)
        send_announcement_push.delay(announcement.id)

        return Response({'status': 'announcement published; emails and push notifications queued'})

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
        """Create notice and send emails asynchronously"""
        print(f"[v0] Creating notice. User ID: {self.request.user.pk}, Exists: {User.objects.filter(pk=self.request.user.pk).exists()}")
        
        # Always save without created_by first to avoid FK constraint issues
        # created_by is read_only in serializer anyway
        notice = serializer.save(school=self.request.user.school)
        
        # Try to set created_by if user exists in DB
        try:
            if User.objects.filter(pk=self.request.user.pk).exists():
                notice.created_by = self.request.user
                notice.save(update_fields=['created_by'])
                print(f"[v0] Set created_by to user {self.request.user.pk}")
            else:
                print(f"[v0] User {self.request.user.pk} does not exist in database, created_by will be NULL")
        except Exception as e:
            print(f"[v0] Error setting created_by: {e}")
        
        # Send emails + in-app/FCM push asynchronously
        send_notice_email.delay(notice.id)
        send_notice_push.delay(notice.id)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSchoolAdminOrHigher()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'], permission_classes=[IsSchoolAdminOrHigher()])
    def recipients(self, request):
        """
        Directory of possible individual recipients (students + teachers)
        in the admin's school — powers the recipient picker on the
        Notices / Announcements pages.
        """
        school = request.user.school
        users = User.objects.filter(school=school, is_active=True, role__in=['student', 'teacher'])

        role_filter = request.query_params.get('role')
        if role_filter:
            users = users.filter(role=role_filter)

        search = request.query_params.get('search')
        if search:
            from django.db.models import Q as _Q
            users = users.filter(
                _Q(first_name__icontains=search) |
                _Q(last_name__icontains=search) |
                _Q(username__icontains=search) |
                _Q(email__icontains=search)
            )

        data = [
            {
                'id': u.id,
                'name': u.get_full_name() or u.username,
                'email': u.email,
                'role': u.role,
            }
            for u in users.order_by('role', 'first_name')[:500]
        ]
        return Response({'results': data})

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        """Pin a notice"""
        notice = self.get_object()
        notice.is_pinned = not notice.is_pinned
        notice.save()
        return Response({'status': f"notice {'pinned' if notice.is_pinned else 'unpinned'}"})

    @action(detail=False, methods=['post'], permission_classes=[IsSchoolAdminOrHigher()])
    def send_personal_notice(self, request):
        """Send personal notice to a specific student"""
        student_id = request.data.get('student_id')
        title = request.data.get('title')
        content = request.data.get('content')
        
        if not all([student_id, title, content]):
            return Response({'error': 'student_id, title, and content are required'}, status=400)
        
        try:
            student = User.objects.get(id=student_id, school=request.user.school, role='student', is_active=True)
        except User.DoesNotExist:
            return Response({'error': 'Student not found or not in your school'}, status=404)
        
        personal_notice = PersonalNotice.objects.create(
            school=request.user.school,
            student=student,
            created_by=request.user,
            title=title,
            content=content
        )

        # Email + in-app/FCM push to the individual student
        send_personal_notice_email.delay(personal_notice.id)
        send_personal_notice_push.delay(personal_notice.id)

        serializer = PersonalNoticeSerializer(personal_notice)
        return Response({
            'status': 'personal notice sent successfully',
            'notice': serializer.data
        })

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_personal_notices(self, request):
        """Get personal notices for the current student"""
        personal_notices = PersonalNotice.objects.filter(
            student=request.user,
            school=request.user.school
        ).select_related('created_by', 'school').order_by('-sent_at')
        
        serializer = PersonalNoticeSerializer(personal_notices, many=True)
        return Response(serializer.data)
