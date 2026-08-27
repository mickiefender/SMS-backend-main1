"""
Serializers for the Notification models.
"""
from rest_framework import serializers
from apps.notifications.models import (
    Notification,
    NotificationPreference,
    Device,
    NotificationType,
)


class NotificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationType
        fields = ['id', 'name', 'slug', 'description', 'is_enabled_by_default', 'sort_order']


class NotificationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for notification lists."""

    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'category', 'title', 'message',
            'image_url', 'target_screen', 'target_id', 'priority',
            'is_read', 'is_pinned', 'created_at',
        ]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    """Full notification serializer with read tracking."""

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'notification_type', 'category',
            'title', 'message', 'image_url', 'target_screen', 'target_id',
            'priority', 'is_read', 'is_pinned', 'read_at', 'created_at',
        ]
        read_only_fields = ['id', 'recipient', 'created_at', 'read_at', 'dedup_hash']


class NotificationMarkReadSerializer(serializers.Serializer):
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False
    )


class DeviceSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Device
        fields = ['id', 'user', 'fcm_token', 'platform', 'device_name',
                  'is_active', 'last_seen_at', 'created_at']
        read_only_fields = ['id', 'user', 'is_active', 'last_seen_at', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        if not user:
            raise serializers.ValidationError('Authentication required.')

        fcm_token = validated_data.get('fcm_token')
        platform = validated_data.get('platform', 'android')
        device_name = validated_data.get('device_name', '')

        device, created = Device.objects.update_or_create(
            fcm_token=fcm_token,
            defaults={
                'user': user,
                'platform': platform,
                'device_name': device_name,
                'is_active': True,
            }
        )
        return device


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'user', 'preferences', 'push_enabled', 'email_enabled',
            'quiet_hours_start', 'quiet_hours_end', 'created_at', 'updated_at',
            # ── Daily Learning Reminder ──────────────────────
            'daily_reminder_enabled',
            'daily_reminder_time',
            'last_daily_reminder_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'last_daily_reminder_at']
        extra_kwargs = {
            'daily_reminder_time': {'required': False, 'allow_null': True},
            'daily_reminder_enabled': {'required': False},
        }

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class BulkNotificationCreateSerializer(serializers.Serializer):
    """Serializer for creating notifications in bulk (teacher/admin only)."""
    notification_type = serializers.CharField(max_length=50)
    category = serializers.ChoiceField(
        choices=[
            'feed', 'school_announcement', 'assignment', 'assignment_reminder',
            'grade', 'attendance', 'fee_reminder', 'message', 'live_class',
            'upload_status', 'comment', 'like', 'daily_reminder', 'app_update',
        ]
    )
    title = serializers.CharField(max_length=255)
    message = serializers.CharField()
    target_screen = serializers.CharField(max_length=255, required=False, allow_blank=True)
    target_id = serializers.CharField(max_length=50, required=False, allow_blank=True)
    image_url = serializers.URLField(max_length=1000, required=False, allow_blank=True)
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high', 'urgent'], default='normal'
    )

    # Recipient targets (choose one)
    user_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
    class_id = serializers.IntegerField(required=False)
    school_id = serializers.IntegerField(required=False)
    role = serializers.CharField(max_length=20, required=False)
