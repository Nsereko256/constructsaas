from django.contrib import admin

from .models import ChatMessage, ChatRoom, Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'status', 'manager', 'budget', 'is_active')
    list_filter = ('company', 'status', 'is_active')
    search_fields = ('name', 'code', 'client', 'location')


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('project', 'company', 'created_at')
    list_filter = ('company',)
    search_fields = ('project__name', 'project__code', 'company__name')
    readonly_fields = ('created_at',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender', 'is_system_message', 'created_at')
    list_filter = ('room__company', 'is_system_message', 'created_at')
    search_fields = ('content', 'sender__username', 'room__project__name')
    readonly_fields = ('created_at',)
