from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .helpers import get_unread_count


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
        if not getattr(user, 'company_id', None):
            await self.close(code=4003)
            return

        self.user = user
        self.group_name = f'notify_user_{user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                'type': 'notification.count',
                'unread_count': await self.get_unread_count(),
            }
        )

    async def disconnect(self, close_code):
        group_name = getattr(self, 'group_name', None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('type') == 'ping':
            await self.send_json(
                {
                    'type': 'pong',
                    'unread_count': await self.get_unread_count(),
                }
            )

    async def notification_message(self, event):
        await self.send_json(
            {
                'type': 'notification.message',
                'notification': event['notification'],
                'unread_count': event['unread_count'],
            }
        )

    async def notification_count(self, event):
        await self.send_json(
            {
                'type': 'notification.count',
                'unread_count': event['unread_count'],
            }
        )

    @database_sync_to_async
    def get_unread_count(self):
        return get_unread_count(self.user, getattr(self.user, 'company', None))
