"""
Core Serializers - Student Notifications
"""
from rest_framework import serializers
from .models import StudentNotification, NotificationTypeChoices


class StudentNotificationSerializer(serializers.ModelSerializer):
    """Serializer for StudentNotification model"""
    
    student_name = serializers.CharField(source='student.name', read_only=True)
    
    class Meta:
        model = StudentNotification
        fields = [
            'id',
            'student',
            'student_name',
            'notification_type',
            'title',
            'message',
            'related_object_id',
            'related_object_type',
            'is_read',
            'is_pinned',
            'priority',
            'created_at',
            'read_at',
        ]
        read_only_fields = ['id', 'created_at', 'read_at']
    
    def create(self, validated_data):
        # Set student from request context
        validated_data['student'] = self.context['request'].user
        return super().create(validated_data)


class StudentNotificationCreateSerializer(serializers.Serializer):
    """Serializer for creating notifications (admin/teacher use)"""
    
    student_id = serializers.IntegerField()
    notification_type = serializers.ChoiceField(
        choices=NotificationTypeChoices.choices
    )
    title = serializers.CharField(max_length=200)
    message = serializers.CharField()
    related_object_id = serializers.IntegerField(required=False, allow_null=True)
    related_object_type = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high', 'urgent'],
        default='normal'
    )


class StudentNotificationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing notifications"""
    
    class Meta:
        model = StudentNotification
        fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'is_read',
            'is_pinned',
            'priority',
            'created_at',
        ]
