from rest_framework import serializers
from django.conf import settings
from django.utils import timezone
from apps.schools.models import School, Plan, Subscription, Announcement


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = '__all__'


class SchoolSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    logo_url_computed = serializers.SerializerMethodField()
    subscription_details = serializers.SerializerMethodField()
    
    class Meta:
        model = School
        fields = [
            'id', 'name', 'email', 'phone', 'address', 'city', 'state',
            'country', 'postal_code', 'logo', 'logo_url', 'website',
            'primary_color', 'secondary_color', 'sidebar_color', 'plan',
            'status', 'subscription_start', 'subscription_end', 'created_at',
            'updated_at', 'logo_url_computed', 'subscription_details',
        ]
    
    def get_logo_url_computed(self, obj):
        """Return the logo URL, preferring Supabase URL over local storage"""
        return obj.get_logo_url()

    def get_subscription_details(self, obj):
        subscription = getattr(obj, 'subscription', None)
        if subscription is None:
            return None

        today = timezone.localdate()
        days_remaining = (subscription.end_date - today).days
        is_expired = days_remaining < 0 or subscription.status != 'active'
        return {
            'plan': PlanSerializer(subscription.plan).data if subscription.plan else None,
            'status': 'expired' if is_expired else (
                'expiring_soon' if days_remaining <= 7 else 'active'
            ),
            'subscription_status': subscription.status,
            'start_date': subscription.start_date,
            'end_date': subscription.end_date,
            'days_remaining': max(days_remaining, 0),
            'is_expiring_soon': not is_expired and days_remaining <= 7,
        }


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
