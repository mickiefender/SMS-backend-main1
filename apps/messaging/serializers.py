from rest_framework import serializers
from .models import Message, Announcement, AnnouncementRead, Notice


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    recipient_name = serializers.CharField(source='recipient.get_full_name', read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'sender_name', 'recipient', 'recipient_name', 'subject', 'content', 'priority', 'is_read', 'created_at', 'updated_at']
        read_only_fields = ['id', 'sender', 'sender_name', 'recipient_name', 'created_at', 'updated_at']


class AnnouncementReadSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = AnnouncementRead
        fields = ['id', 'user', 'user_name', 'read_at']
        read_only_fields = ['id', 'read_at']


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    read_count = serializers.SerializerMethodField()
    class_names = serializers.StringRelatedField(source='classes', many=True, read_only=True)

    class Meta:
        model = Announcement
        fields = ['id', 'school', 'created_by', 'created_by_name', 'title', 'content', 'status', 'send_to_teachers', 'send_to_students', 'send_to_all', 'classes', 'class_names', 'published_date', 'read_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'created_by', 'created_by_name', 'read_count', 'created_at', 'updated_at']

    def get_read_count(self, obj):
        return obj.read_by.count()


class NoticeSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = Notice
        fields = ['id', 'school', 'created_by', 'created_by_name', 'title', 'content', 'priority', 'send_to_teachers', 'send_to_students', 'send_to_all', 'is_pinned', 'expiry_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'created_by', 'created_by_name', 'created_at', 'updated_at']
