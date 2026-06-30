"""
Core API Views - Student Notifications
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count
from django.utils import timezone
from .models import StudentNotification, NotificationTypeChoices
from .serializers import StudentNotificationSerializer, StudentNotificationListSerializer


class StudentNotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing student notifications.
    Students can view and mark their own notifications as read.
    Teachers and school admins can send notifications to students.
    """
    serializer_class = StudentNotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Students can only see their own notifications
        if user.role == 'student':
            return StudentNotification.objects.filter(student=user)
        
        # Teachers and school admins can see all notifications in their school
        if user.role in ['teacher', 'school_admin']:
            return StudentNotification.objects.filter(student__school=user.school)
        
        # Super admin can see all
        if user.role == 'super_admin':
            return StudentNotification.objects.all()
        
        return StudentNotification.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return StudentNotificationListSerializer
        return StudentNotificationSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'create_bulk']:
            # Teachers and school admins can create notifications for students
            if self.request.user.role in ['teacher', 'school_admin']:
                return [IsAuthenticated()]
            return [IsAuthenticated()]  # Will be denied in perform_create
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        # Only allow teachers/admins to create for other students
        if self.request.user.role not in ['teacher', 'school_admin', 'super_admin']:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only teachers and admins can send notifications")
        
        serializer.save()
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications for current user"""
        if request.user.role == 'student':
            count = StudentNotification.objects.filter(
                student=request.user,
                is_read=False
            ).count()
            return Response({'unread_count': count})
        
        # For teachers/admins, get count of unread for a specific student
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response({'unread_count': 0})
        
        try:
            count = StudentNotification.objects.filter(
                student_id=student_id,
                is_read=False
            ).count()
            return Response({'unread_count': count})
        except ValueError:
            return Response({'error': 'Invalid student_id'}, status=400)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_object()
        
        # Check permission
        if request.user.role == 'student' and notification.student != request.user:
            return Response({'error': 'Not authorized'}, status=403)
        
        notification.mark_as_read()
        return Response({'status': 'marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read for current student"""
        if request.user.role != 'student':
            return Response({'error': 'Only students can use this endpoint'}, status=403)
        
        updated = StudentNotification.objects.filter(
            student=request.user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
        
        return Response({'status': 'marked all as read', 'count': updated})
    
    @action(detail=False, methods=['get'])
    def unread_summary(self, request):
        """Get summary of unread notifications by type"""
        if request.user.role != 'student':
            return Response({'error': 'Only students can use this endpoint'}, status=403)
        
        summary = StudentNotification.objects.filter(
            student=request.user,
            is_read=False
        ).values('notification_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        return Response({
            'unread_by_type': list(summary),
            'total_unread': sum(item['count'] for item in summary)
        })
    
    @action(detail=False, methods=['post'])
    def create_bulk(self, request):
        """Create multiple notifications at once (for bulk operations)"""
        if request.user.role not in ['teacher', 'school_admin', 'super_admin']:
            return Response({'error': 'Not authorized'}, status=403)
        
        notifications_data = request.data.get('notifications', [])
        if not notifications_data:
            return Response({'error': 'No notifications provided'}, status=400)
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        created = []
        errors = []
        
        for i, data in enumerate(notifications_data):
            student_id = data.get('student_id')
            if not student_id:
                errors.append({'index': i, 'error': 'student_id required'})
                continue
            
            try:
                student = User.objects.get(id=student_id, role='student')
            except User.DoesNotExist:
                errors.append({'index': i, 'error': f'Student {student_id} not found'})
                continue
            
            notification = StudentNotification.objects.create(
                student=student,
                notification_type=data.get('notification_type', 'general'),
                title=data.get('title', 'Notification'),
                message=data.get('message', ''),
                related_object_id=data.get('related_object_id'),
                related_object_type=data.get('related_object_type'),
                priority=data.get('priority', 'normal')
            )
            created.append(notification.id)
        
        return Response({
            'created': created,
            'errors': errors,
            'total_created': len(created)
        })


def send_student_notification(
    student,
    notification_type,
    title,
    message,
    related_object_id=None,
    related_object_type=None,
    priority='normal'
):
    """
    Helper function to create a student notification.
    Used by other apps to send notifications when events occur.
    """
    return StudentNotification.objects.create(
        student=student,
        notification_type=notification_type,
        title=title,
        message=message,
        related_object_id=str(related_object_id) if related_object_id else None,
        related_object_type=related_object_type,
        priority=priority
    )


def send_notification_to_student_class(
    class_id,
    notification_type,
    title,
    message,
    related_object_id=None,
    related_object_type=None,
    priority='normal'
):
    """
    Send notification to all students in a class.
    """
    from apps.academics.models import StudentClass
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    student_ids = StudentClass.objects.filter(
        class_obj_id=class_id,
        is_active=True
    ).values_list('student_id', flat=True)
    
    students = User.objects.filter(id__in=student_ids, role='student')
    
    created = []
    for student in students:
        notification = StudentNotification.objects.create(
            student=student,
            notification_type=notification_type,
            title=title,
            message=message,
            related_object_id=str(related_object_id) if related_object_id else None,
            related_object_type=related_object_type,
            priority=priority
        )
        created.append(notification.id)
    
    return created


def send_notification_to_school(
    school,
    notification_type,
    title,
    message,
    related_object_id=None,
    related_object_type=None,
    priority='normal',
    target_roles=None
):
    """
    Send notification to all students in a school.
    Optionally filter by roles.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    queryset = User.objects.filter(school=school, role='student', is_active=True)
    
    if target_roles:
        queryset = queryset.filter(role__in=target_roles)
    
    created = []
    for student in queryset:
        notification = StudentNotification.objects.create(
            student=student,
            notification_type=notification_type,
            title=title,
            message=message,
            related_object_id=str(related_object_id) if related_object_id else None,
            related_object_type=related_object_type,
            priority=priority
        )
        created.append(notification.id)
    
    return created
