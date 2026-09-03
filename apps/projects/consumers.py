from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .access import can_access_project_chat
from .models import ChatMessage, ChatRoom, Project


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        self.user = self.scope.get('user')

        room_data = await self.get_room_data()
        if not room_data:
            await self.close(code=4003)
            return

        self.room_id = room_data['room_id']
        self.group_name = f'chat_project_{self.project_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                'type': 'chat.history',
                'messages': await self.get_last_messages(),
            }
        )

    async def disconnect(self, close_code):
        group_name = getattr(self, 'group_name', None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})
            return

        message = (content.get('message') or content.get('content') or '').strip()
        if not message:
            return

        saved_message = await self.create_user_message(message)
        await self.broadcast_message(saved_message)

    async def chat_message(self, event):
        await self.send_json(
            {
                'type': 'chat.message',
                'message': event['message'],
            }
        )

    async def broadcast_message(self, message):
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'chat.message',
                'message': message,
            },
        )

    @database_sync_to_async
    def get_room_data(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated or not user.company_id:
            return None

        try:
            project = Project.objects.prefetch_related('site_engineers').get(
                pk=self.project_id,
                company_id=user.company_id,
            )
        except Project.DoesNotExist:
            return None
        if not can_access_project_chat(user, project):
            return None

        room, _ = ChatRoom.objects.get_or_create(
            project=project,
            defaults={'company_id': project.company_id},
        )
        return {
            'room_id': room.id,
        }

    @database_sync_to_async
    def get_last_messages(self):
        messages = list(
            ChatMessage.objects.filter(
                room_id=self.room_id,
                is_system_message=False,
            )
            .select_related('sender')
            .order_by('-created_at')[:30]
        )
        messages.reverse()
        return [self.serialize_message(message) for message in messages]

    @database_sync_to_async
    def create_user_message(self, content):
        message = ChatMessage.objects.create(
            room_id=self.room_id,
            sender=self.user,
            content=content,
        )
        return self.serialize_message(message)

    @staticmethod
    def serialize_message(message):
        created_at = timezone.localtime(message.created_at)
        sender_name = 'System'
        if not message.is_system_message and message.sender:
            sender_name = message.sender.get_full_name() or message.sender.username

        return {
            'id': message.id,
            'sender': sender_name,
            'sender_id': message.sender_id,
            'content': message.content,
            'is_system_message': message.is_system_message,
            'created_at': created_at.isoformat(),
            'created_at_display': created_at.strftime('%b %d, %H:%M'),
        }
