from django.contrib import admin
from apps.notifications.models import Notification, Device, NotificationPreference, NotificationType


@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_enabled_by_default', 'sort_order']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['user', 'platform', 'device_name', 'is_active', 'last_seen_at']
    list_filter = ['platform', 'is_active']
    search_fields = ['user__email', 'user__username', 'fcm_token']


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'push_enabled', 'email_enabled']
    list_filter = ['push_enabled', 'email_enabled']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'recipient', 'category', 'notification_type', 'is_read', 'priority', 'created_at']
    list_filter = ['category', 'is_read', 'priority', 'notification_type']
    search_fields = ['title', 'message', 'recipient__email']
    date_hierarchy = 'created_at'
    readonly_fields = ['id', 'created_at', 'dedup_hash']
