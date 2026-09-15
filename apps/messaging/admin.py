from django.contrib import admin
from .models import (
    Message, Announcement, AnnouncementRead, Notice, SMSConfiguration,
    SMSBalance, SMSTemplate, SMSJob, SMSMessage, SMSCreditLedger,
)


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


@admin.register(SMSConfiguration)
class SMSConfigurationAdmin(admin.ModelAdmin):
    list_display = ("school", "sender_id", "sender_id_status", "is_enabled", "updated_at")
    list_filter = ("sender_id_status", "is_enabled")
    search_fields = ("school__name", "sender_id")


@admin.register(SMSBalance)
class SMSBalanceAdmin(admin.ModelAdmin):
    list_display = ("school", "credits", "updated_at")
    search_fields = ("school__name",)


@admin.register(SMSTemplate)
class SMSTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "category", "is_active", "updated_at")
    list_filter = ("category", "is_active", "school")


@admin.register(SMSJob)
class SMSJobAdmin(admin.ModelAdmin):
    list_display = ("id", "school", "status", "recipient_count", "credits_reserved", "created_at")
    list_filter = ("status", "school")


@admin.register(SMSMessage)
class SMSMessageAdmin(admin.ModelAdmin):
    list_display = ("school", "sender_id", "recipient", "status", "credits_used", "created_at")
    list_filter = ("status", "school", "category")
    search_fields = ("recipient", "message", "provider_message_id")


@admin.register(SMSCreditLedger)
class SMSCreditLedgerAdmin(admin.ModelAdmin):
    list_display = ("school", "amount", "balance_after", "reason", "created_at")
    list_filter = ("reason", "school")
