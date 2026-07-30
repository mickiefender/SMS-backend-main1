"""
API views for the centralized notification system.

Endpoints:
  /api/notifications/notifications/        — in-app notification center
  /api/notifications/devices/              — FCM token registry
  /api/notifications/preferences/          — per-user notification settings
  /api/notifications/send/                 — send notification (admin/teacher)
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count

from apps.notifications import models, serializers
from apps.notifications.services import notification_service


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/notifications/notifications/        — paginated notification list
    GET  /api/notifications/notifications/{id}/   — notification detail
    POST /api/notifications/notifications/{id}/mark_read/
    POST /api/notifications/notifications/mark_all_read/
    GET  /api/notifications/notifications/unread_count/
    GET  /api/notifications/notifications/unread_summary/
    """
    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get_serializer_class(self):
        if self.action == 'list':
            return serializers.NotificationListSerializer
        return serializers.NotificationSerializer

    def get_queryset(self):
        qs = models.Notification.objects.filter(recipient=self.request.user)
        # Filters
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == 'true')
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'status': 'marked as read'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        count = notification_service.mark_all_as_read(request.user)
        return Response({'status': 'all marked as read', 'count': count})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = notification_service.get_unread_count(request.user)
        return Response({'unread_count': count})

    @action(detail=False, methods=['get'])
    def unread_summary(self, request):
        summary = models.Notification.objects.filter(
            recipient=request.user, is_read=False
        ).values('category').annotate(count=Count('id')).order_by('-count')
        return Response({
            'unread_by_type': list(summary),
            'total_unread': sum(item['count'] for item in summary),
        })


class DeviceViewSet(viewsets.ModelViewSet):
    """
    POST   /api/notifications/devices/               — register FCM token
    DELETE /api/notifications/devices/?fcm_token=xxx  — unregister
    GET    /api/notifications/devices/                — list my devices
    """
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.DeviceSerializer

    def get_queryset(self):
        return models.Device.objects.filter(user=self.request.user, is_active=True)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        fcm_token = request.query_params.get('fcm_token')
        if fcm_token:
            notification_service.unregister_device(fcm_token)
            return Response(status=status.HTTP_204_NO_CONTENT)
        return super().destroy(request, *args, **kwargs)


class NotificationPreferenceView(APIView):
    """
    GET  /api/notifications/preferences/  — get my preferences
    PUT  /api/notifications/preferences/  — update my preferences
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = notification_service.get_or_create_preferences(request.user)
        serializer = serializers.NotificationPreferenceSerializer(prefs)
        return Response(serializer.data)

    def put(self, request):
        prefs, _ = notification_service.get_or_create_preferences(request.user)
        serializer = serializers.NotificationPreferenceSerializer(
            prefs, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SendNotificationView(APIView):
    """
    POST /api/notifications/send/
    Requires teacher or admin role.

    Sends a notification to one of:
      - Specific user IDs (user_ids)
      - A class (class_id)
      - A school (school_id)
      - A role (role)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Only teachers, admins, and super_admins can send
        allowed_roles = {'teacher', 'school_admin', 'academic_admin', 'super_admin'}
        if request.user.role not in allowed_roles:
            return Response(
                {'error': 'Only teachers and admins can send notifications.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = serializers.BulkNotificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        notification_type = data['notification_type']
        category = data['category']
        title = data['title']
        message = data['message']
        target_screen = data.get('target_screen', '')
        target_id = data.get('target_id', '')
        image_url = data.get('image_url', '')
        priority = data.get('priority', 'normal')

        created_count = 0

        # Send to specific user IDs
        if data.get('user_ids'):
            for uid in data['user_ids']:
                n = notification_service.send_notification(
                    recipient=uid,
                    notification_type=notification_type,
                    category=category,
                    title=title,
                    message=message,
                    target_screen=target_screen,
                    target_id=target_id,
                    image_url=image_url,
                    priority=priority,
                )
                if n:
                    created_count += 1

        # Send to a class
        if data.get('class_id'):
            from apps.academics.models import Class as AcademicClass
            try:
                class_obj = AcademicClass.objects.get(id=data['class_id'])
                results = notification_service.send_notification_to_class(
                    class_obj=class_obj,
                    notification_type=notification_type,
                    category=category,
                    title=title,
                    message=message,
                    target_screen=target_screen,
                    target_id=target_id,
                    priority=priority,
                )
                created_count += len(results)
            except AcademicClass.DoesNotExist:
                return Response({'error': 'Class not found.'}, status=status.HTTP_400_BAD_REQUEST)

        # Send to a school
        if data.get('school_id'):
            from apps.schools.models import School
            try:
                school = School.objects.get(id=data['school_id'])
                results = notification_service.send_notification_to_school(
                    school=school,
                    notification_type=notification_type,
                    category=category,
                    title=title,
                    message=message,
                    target_screen=target_screen,
                    target_id=target_id,
                    priority=priority,
                    target_roles=['student'],
                )
                created_count += len(results)
            except School.DoesNotExist:
                return Response({'error': 'School not found.'}, status=status.HTTP_400_BAD_REQUEST)

        # Send to a role
        if data.get('role'):
            results = notification_service.send_notification_to_role(
                role=data['role'],
                notification_type=notification_type,
                category=category,
                title=title,
                message=message,
                target_screen=target_screen,
                target_id=target_id,
                priority=priority,
            )
            created_count += len(results)

        if created_count == 0:
            return Response(
                {'error': 'No recipients matched.', 'created': 0},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'status': 'notifications created',
            'created_count': created_count,
        }, status=status.HTTP_201_CREATED)
