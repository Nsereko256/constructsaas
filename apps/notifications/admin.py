from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'company',
        'recipient',
        'notification_type',
        'level',
        'is_read',
        'created_at',
    )
    list_filter = ('company', 'notification_type', 'level', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username', 'company__name')
    readonly_fields = ('created_at',)
