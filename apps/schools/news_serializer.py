from rest_framework import serializers
from apps.schools.news_models import News


class NewsSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = News
        fields = [
            'id',
            'school',
            'school_name',
            'title',
            'excerpt',
            'content',
            'category',
            'audience',
            'banner_image_url',
            'is_published',
            'is_banner',
            'created_by',
            'created_by_name',
            'published_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'school',
            'school_name',
            'created_by',
            'created_by_name',
            'published_at',
            'created_at',
            'updated_at',
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request.user, 'school') and request.user.school:
            validated_data['school'] = request.user.school
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class NewsListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views (no full content body)."""
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = News
        fields = [
            'id',
            'title',
            'excerpt',
            'category',
            'audience',
            'banner_image_url',
            'is_published',
            'is_banner',
            'created_by_name',
            'published_at',
            'created_at',
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None
