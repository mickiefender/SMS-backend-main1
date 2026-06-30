from rest_framework import serializers
from django.conf import settings
from apps.schools.models import School, Plan, Subscription, Announcement


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = '__all__'


class SchoolSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    logo_url_computed = serializers.SerializerMethodField()
    
    class Meta:
        model = School
        fields = '__all__'
    
    def get_logo_url_computed(self, obj):
        """Return the logo URL, preferring Supabase URL over local storage"""
        return obj.get_logo_url()


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    school = SchoolSerializer(read_only=True)
    
    class Meta:
        model = Subscription
        fields = '__all__'


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = Announcement
        fields = '__all__'
