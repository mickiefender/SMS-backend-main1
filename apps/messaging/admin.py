from django.contrib import admin
from .models import Message, Announcement, AnnouncementRead, Notice


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'recipient', 'subject', 'is_read', 'created_at')
    list_filter = ('is_read', 'priority', 'created_at')
    search_fields = ('subject', 'content', 'sender__email', 'recipient__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'school', 'status', 'published_date', 'created_at')
    list_filter = ('status', 'school', 'send_to_teachers', 'send_to_students', 'created_at')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('classes',)


@admin.register(AnnouncementRead)
class AnnouncementReadAdmin(admin.ModelAdmin):
    list_display = ('announcement', 'user', 'read_at')
    list_filter = ('read_at', 'announcement__school')
    search_fields = ('announcement__title', 'user__email')


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ('title', 'school', 'priority', 'is_pinned', 'expiry_date', 'created_at')
    list_filter = ('priority', 'is_pinned', 'school', 'send_to_teachers', 'send_to_students', 'created_at')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'updated_at')
