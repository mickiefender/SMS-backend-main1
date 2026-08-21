from rest_framework import serializers
from .models import Message, Announcement, AnnouncementRead, Notice, PersonalNotice


class PersonalNoticeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = PersonalNotice
        fields = ['id', 'school', 'student', 'student_name', 'created_by', 'created_by_name', 'title', 'content', 'sent_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'student', 'student_name', 'created_by', 'created_by_name', 'sent_at', 'created_at', 'updated_at']


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
    recipient_names = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ['id', 'school', 'created_by', 'created_by_name', 'title', 'content', 'status',
                  'send_to_teachers', 'send_to_students', 'send_to_all', 'recipients', 'recipient_names',
                  'classes', 'class_names', 'priority', 'published_date', 'read_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'created_by', 'created_by_name', 'status', 'published_date', 'read_count', 'created_at', 'updated_at']

    def get_read_count(self, obj):
        return obj.read_by.count()

    def get_recipient_names(self, obj):
        return [u.get_full_name() or u.username for u in obj.recipients.all()]


class NoticeSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    recipient_names = serializers.SerializerMethodField()

    class Meta:
        model = Notice
        fields = ['id', 'school', 'created_by', 'created_by_name', 'title', 'content', 'priority',
                  'send_to_teachers', 'send_to_students', 'send_to_all', 'recipients', 'recipient_names',
                  'is_pinned', 'expiry_date', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'created_by', 'created_by_name', 'created_at', 'updated_at']

    def get_recipient_names(self, obj):
        return [u.get_full_name() or u.username for u in obj.recipients.all()]
