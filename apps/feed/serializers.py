"""
Serializers for the Alara Learning Feed.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model

from apps.feed import models

User = get_user_model()


class FeedAcademicLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedAcademicLevel
        fields = ['id', 'name', 'slug', 'order', 'is_active']


class FeedAcademicClassSerializer(serializers.ModelSerializer):
    level = FeedAcademicLevelSerializer(read_only=True)

    class Meta:
        model = models.FeedAcademicClass
        fields = ['id', 'name', 'slug', 'level', 'order', 'is_active']


class FeedSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedSubject
        fields = ['id', 'name', 'slug', 'is_active']


class FeedTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedTag
        fields = ['id', 'name', 'slug', 'usage_count']


class LessonResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LessonResource
        fields = [
            'id', 'resource_type', 'title', 'storage_bucket', 'storage_path',
            'public_url', 'file_size', 'mime_type', 'duration_seconds',
            'width', 'height', 'page_count', 'sort_order', 'is_primary',
            'extra_metadata', 'created_at'
        ]
        read_only_fields = fields


class LessonListSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True)
    teacher_profile_picture = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    level_name = serializers.CharField(source='level.name', read_only=True)
    class_name = serializers.CharField(source='class_obj.name', read_only=True)
    tags = FeedTagSerializer(many=True, read_only=True)
    primary_resource = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    is_following_teacher = serializers.SerializerMethodField()

    # ── Cloudflare Stream fields (replace old video_url / media_url / poster_url) ──
    video_url = serializers.SerializerMethodField()
    video_uid = serializers.CharField(source='cloudflare_video_uid', read_only=True)
    playback_url = serializers.CharField(source='cloudflare_playback_url', read_only=True)
    cloudflare_thumbnail_url = serializers.URLField(read_only=True)
    video_duration = serializers.FloatField(read_only=True)

    # New lesson metadata fields
    content_type_name = serializers.SerializerMethodField()
    difficulty_level_name = serializers.SerializerMethodField()
    curriculum_name = serializers.SerializerMethodField()
    learning_objective_name = serializers.SerializerMethodField()

    class Meta:
        model = models.FeedLesson
        fields = [
            'id', 'title', 'description', 'topic', 'teacher_id', 'teacher_name',
            'school_id', 'school_name', 'level_id', 'level_name',
            'class_obj_id', 'class_name', 'subject_id', 'subject_name',
            'content_type_id', 'content_type_name',
            'difficulty_level_id', 'difficulty_level_name',
            'curriculum_id', 'curriculum_name',
            'learning_objective_id', 'learning_objective_name',
            'keywords', 'hashtags',
            'visibility', 'status', 'verification_status',
            'duration_seconds', 'thumbnail_url', 'poster_url',
            'video_url', 'video_uid', 'playback_url',
            'cloudflare_thumbnail_url', 'video_duration',
            'view_count', 'unique_view_count', 'like_count', 'save_count',
            'comment_count', 'share_count', 'download_count',
            'completion_rate', 'avg_watch_seconds', 'trending_score',
            'tags', 'primary_resource', 'is_liked', 'is_saved',
            'teacher_profile_picture',
            'is_following_teacher', 'published_at', 'created_at',
        ]

    def _get_primary_resource(self, obj):
        return obj.resources.filter(is_primary=True).first() or obj.resources.first()

    def get_primary_resource(self, obj):
        resource = self._get_primary_resource(obj)
        return LessonResourceSerializer(resource).data if resource else None

    def get_video_url(self, obj):
        """
        Returns the Cloudflare Stream HLS playback URL if available.
        Falls back to the old resource-based video URL for backwards compatibility
        during migration.
        """
        if obj.cloudflare_playback_url:
            return obj.cloudflare_playback_url
        resource = self._get_primary_resource(obj)
        return resource.public_url if resource and resource.resource_type == 'video' else None

    def get_is_liked(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return False
        return models.FeedLike.objects.filter(user=user, lesson=obj).exists()

    def get_is_saved(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return False
        return models.FeedSave.objects.filter(user=user, lesson=obj).exists()

    def get_teacher_profile_picture(self, obj):
        try:
            profile_pic = getattr(obj.teacher, 'profile_picture', None)
            if profile_pic:
                return profile_pic.display_url
        except Exception:
            pass
        return None

    def get_is_following_teacher(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return False
        return models.TeacherFollower.objects.filter(user=user, teacher=obj.teacher).exists()

    def get_content_type_name(self, obj):
        return obj.content_type.name if obj.content_type else None

    def get_difficulty_level_name(self, obj):
        return obj.difficulty_level.name if obj.difficulty_level else None

    def get_curriculum_name(self, obj):
        return obj.curriculum.name if obj.curriculum else None

    def get_learning_objective_name(self, obj):
        return obj.learning_objective.name if obj.learning_objective else None


class LessonDetailSerializer(LessonListSerializer):
    resources = LessonResourceSerializer(many=True, read_only=True)

    class Meta(LessonListSerializer.Meta):
        fields = LessonListSerializer.Meta.fields + ['resources', 'extra_metadata']


class LessonWriteSerializer(serializers.ModelSerializer):
    tags = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, write_only=True
    )
    resources = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )
    media_file = serializers.FileField(required=False, write_only=True)
    thumbnail_file = serializers.FileField(required=False, write_only=True)
    content_type_id = serializers.IntegerField(required=False, allow_null=True)
    difficulty_level_id = serializers.IntegerField(required=False, allow_null=True)
    curriculum_id = serializers.IntegerField(required=False, allow_null=True)
    learning_objective_id = serializers.IntegerField(required=False, allow_null=True)
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, allow_empty=True
    )
    hashtags = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, allow_empty=True
    )

    class Meta:
        model = models.FeedLesson
        fields = [
            'id', 'title', 'description', 'topic', 'school', 'level', 'class_obj',
            'subject', 'tags', 'resources', 'media_file', 'thumbnail_file',
            'visibility', 'status',
            'duration_seconds', 'thumbnail_url', 'poster_url', 'extra_metadata',
            'content_type_id', 'difficulty_level_id', 'curriculum_id',
            'learning_objective_id', 'keywords', 'hashtags',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        if attrs.get('class_obj') and attrs.get('level'):
            if attrs['class_obj'].level_id != attrs['level'].id:
                raise serializers.ValidationError(
                    {'class_obj': 'Selected class does not belong to the selected level.'}
                )
        return attrs


class LearningProfileSerializer(serializers.ModelSerializer):
    preferred_subjects = FeedSubjectSerializer(many=True, read_only=True)
    subject_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = models.LearningProfile
        fields = [
            'id', 'user', 'preferred_level', 'preferred_class', 'preferred_subjects',
            'subject_ids', 'preferred_subject_ids', 'preferences',
            'learning_streak_days', 'last_learning_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        subject_ids = validated_data.pop('subject_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if subject_ids is not None:
            instance.preferred_subjects.set(subject_ids)
            instance.preferred_subject_ids = subject_ids
            instance.save(update_fields=['preferred_subject_ids'])
        return instance


class FeedCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    content = serializers.SerializerMethodField()
    lesson_id = serializers.IntegerField(read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    parent_comment_id = serializers.IntegerField(source='parent_id', read_only=True)
    is_liked = serializers.SerializerMethodField()
    replies_count = serializers.IntegerField(source='replies.count', read_only=True)

    class Meta:
        model = models.FeedComment
        fields = [
            'id', 'lesson', 'lesson_id', 'user', 'user_id', 'user_name', 'parent',
            'parent_comment_id', 'body', 'content', 'is_pinned', 'is_moderated',
            'is_deleted', 'like_count', 'is_liked', 'replies_count', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'lesson', 'lesson_id', 'user', 'user_id', 'user_name',
            'parent', 'parent_comment_id', 'body', 'content', 'like_count', 'replies_count',
            'is_pinned', 'is_moderated', 'is_deleted', 'created_at', 'updated_at',
        ]

    def get_content(self, obj):
        return obj.body

    def get_is_liked(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return False
        return models.CommentLike.objects.filter(user=user, comment=obj).exists()


class CommentCreateSerializer(serializers.Serializer):
    content = serializers.CharField(required=True, allow_blank=False, write_only=True)
    parent_comment_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedComment.objects.all(),
        required=False,
        allow_null=True,
        source='parent',
        write_only=True,
    )

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Comment cannot be empty.')
        return value

    def validate(self, attrs):
        attrs['body'] = attrs.pop('content').strip()
        return attrs


class TeacherFollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TeacherFollower
        fields = ['id', 'user', 'teacher', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class FeedReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedReport
        fields = [
            'id', 'reporter', 'target_type', 'lesson', 'comment', 'teacher',
            'reason', 'description', 'status', 'resolution', 'resolved_by',
            'resolved_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'reporter', 'status', 'resolution', 'resolved_by', 'resolved_at', 'created_at', 'updated_at']


class FeedNotificationSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.get_full_name', read_only=True)

    class Meta:
        model = models.FeedNotification
        fields = [
            'id', 'notification_type', 'title', 'message', 'lesson', 'comment',
            'actor', 'actor_name', 'related_object_type', 'related_object_id',
            'is_read', 'priority', 'created_at', 'read_at',
        ]
        read_only_fields = fields


class WatchHistorySerializer(serializers.ModelSerializer):
    lesson = LessonListSerializer(read_only=True)

    class Meta:
        model = models.WatchHistory
        fields = [
            'id', 'lesson', 'watch_seconds', 'completion_percentage',
            'is_completed', 'resume_position_seconds', 'last_watched_at',
        ]
        read_only_fields = ['id', 'lesson']


class WatchEventSerializer(serializers.Serializer):
    watch_seconds = serializers.IntegerField(min_value=0)
    resume_position = serializers.IntegerField(min_value=0, default=0)


# =============================================================================
# Guest Learner Serializer
# =============================================================================

class GuestLearnerSerializer(serializers.ModelSerializer):
    """Serializer for GuestLearner model (DB-persisted guest profiles)."""

    class Meta:
        model = models.GuestLearner
        fields = [
            'device_id', 'name', 'level_id', 'class_obj_id',
            'subject_ids', 'liked_lesson_ids',
            'onboarding_completed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['onboarding_completed_at', 'created_at', 'updated_at']