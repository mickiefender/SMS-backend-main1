"""
Serializers for the Alara Learning Feed.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model

from apps.feed import models
from apps.schools.models import School

User = get_user_model()


class FeedAcademicLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedAcademicLevel
        fields = ['id', 'name', 'slug', 'order', 'is_active']
        extra_kwargs = {'slug': {'required': False}}


class FeedAcademicClassSerializer(serializers.ModelSerializer):
    level = FeedAcademicLevelSerializer(read_only=True)
    level_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedAcademicLevel.objects.all(),
        write_only=True,
        required=False,
        source='level',
    )

    class Meta:
        model = models.FeedAcademicClass
        fields = ['id', 'name', 'slug', 'level', 'level_id', 'order', 'is_active']
        extra_kwargs = {'slug': {'required': False}}


class FeedSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedSubject
        fields = ['id', 'name', 'slug', 'is_active']
        extra_kwargs = {'slug': {'required': False}}


class FeedContentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedContentType
        fields = ['id', 'name', 'slug', 'is_active']
        extra_kwargs = {'slug': {'required': False}}


class FeedDifficultyLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedDifficultyLevel
        fields = ['id', 'name', 'slug', 'order', 'is_active']
        extra_kwargs = {'slug': {'required': False}}


class FeedCurriculumSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedCurriculum
        fields = ['id', 'name', 'slug', 'is_active']
        extra_kwargs = {'slug': {'required': False}}


class FeedLearningObjectiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedLearningObjective
        fields = ['id', 'name', 'slug', 'is_active']
        extra_kwargs = {'slug': {'required': False}}


class FeedTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedTag
        fields = ['id', 'name', 'slug', 'usage_count']
        extra_kwargs = {'slug': {'required': False}, 'usage_count': {'read_only': True}}


class FeedVisibilityScopeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedVisibilityScope
        fields = ['id', 'name', 'slug', 'description']
        extra_kwargs = {'slug': {'required': False}}


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
    school_id = serializers.PrimaryKeyRelatedField(
        queryset=School.objects.all(),
        required=False,
        write_only=True,
        source='school',
    )
    academic_level_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedAcademicLevel.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
        source='level',
    )
    academic_class_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedAcademicClass.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
        source='class_obj',
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedSubject.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
        source='subject',
    )
    content_type_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedContentType.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
        source='content_type',
    )
    difficulty_level_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedDifficultyLevel.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
        source='difficulty_level',
    )
    curriculum_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedCurriculum.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
        source='curriculum',
    )
    learning_objective_id = serializers.PrimaryKeyRelatedField(
        queryset=models.FeedLearningObjective.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
        source='learning_objective',
    )
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, allow_empty=True
    )
    hashtags = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, allow_empty=True
    )
    cloudflare_video_uid = serializers.CharField(
        required=False, allow_blank=True, write_only=True,
        help_text='UID from direct upload to Cloudflare Stream. When provided, media_file is ignored for videos.'
    )

    class Meta:
        model = models.FeedLesson
        fields = [
            'id', 'title', 'description', 'topic',
            'school_id', 'academic_level_id', 'academic_class_id', 'subject_id',
            'tags', 'resources', 'media_file', 'thumbnail_file',
            'visibility', 'status',
            'duration_seconds', 'thumbnail_url', 'poster_url', 'extra_metadata',
            'content_type_id', 'difficulty_level_id', 'curriculum_id',
            'learning_objective_id', 'keywords', 'hashtags',
            'cloudflare_video_uid',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        class_obj = attrs.get('class_obj')
        level = attrs.get('level')
        if class_obj and level and class_obj.level_id != level.id:
            # The class is the more specific entity. Align the level to the
            # class's level so a stale slug-based pairing (e.g. after the
            # super admin re-orders the reference data) can never fail an
            # otherwise valid upload.
            attrs['level'] = class_obj.level if class_obj.level_id else None
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
    user_profile_picture = serializers.SerializerMethodField()
    user_school_logo = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    lesson_id = serializers.IntegerField(read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    parent_comment_id = serializers.IntegerField(source='parent_id', read_only=True)
    is_liked = serializers.SerializerMethodField()
    replies_count = serializers.IntegerField(source='replies.count', read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = models.FeedComment
        fields = [
            'id', 'lesson', 'lesson_id', 'user', 'user_id', 'user_name',
            'user_profile_picture', 'user_school_logo',
            'parent', 'parent_comment_id', 'body', 'content', 'is_pinned',
            'is_moderated', 'is_deleted', 'like_count', 'is_liked',
            'replies_count', 'replies', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'lesson', 'lesson_id', 'user', 'user_id', 'user_name',
            'user_profile_picture', 'user_school_logo',
            'parent', 'parent_comment_id', 'body', 'content', 'like_count', 'replies_count',
            'is_pinned', 'is_moderated', 'is_deleted', 'created_at', 'updated_at',
        ]

    def get_content(self, obj):
        return obj.body

    def get_user_profile_picture(self, obj):
        try:
            profile_pic = getattr(obj.user, 'profile_picture', None)
            if profile_pic:
                return profile_pic.display_url
        except Exception:
            pass
        return None

    def get_user_school_logo(self, obj):
        try:
            if obj.user and obj.user.school:
                return obj.user.school.get_logo_url()
        except Exception:
            pass
        return None

    def get_replies(self, obj):
        # Nest replies up to 2 levels to avoid unbounded recursion while
        # still showing threads. Depth is threaded through the context.
        depth = self.context.get('replies_depth', 1)
        if depth > 2:
            return []
        qs = obj.replies.all().order_by('created_at')
        serializer = FeedCommentSerializer(
            qs,
            many=True,
            context={**self.context, 'replies_depth': depth + 1},
        )
        return serializer.data

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
    actor_profile_picture = serializers.SerializerMethodField()
    actor_school_logo = serializers.SerializerMethodField()

    class Meta:
        model = models.FeedNotification
        fields = [
            'id', 'notification_type', 'title', 'message', 'lesson', 'comment',
            'actor', 'actor_name', 'actor_profile_picture', 'actor_school_logo',
            'related_object_type', 'related_object_id',
            'is_read', 'priority', 'created_at', 'read_at',
        ]
        read_only_fields = fields

    def get_actor_profile_picture(self, obj):
        try:
            profile_pic = getattr(obj.actor, 'profile_picture', None)
            if profile_pic:
                return profile_pic.display_url
        except Exception:
            pass
        return None

    def get_actor_school_logo(self, obj):
        try:
            if obj.actor and obj.actor.school:
                return obj.actor.school.get_logo_url()
        except Exception:
            pass
        return None


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
