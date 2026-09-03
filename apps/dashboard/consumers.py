from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .helpers import get_dashboard_payload


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        company_id = getattr(user, 'company_id', None)
        if not company_id:
            await self.close(code=4003)
            return

        self.company_id = company_id
        self.group_name = f'dashboard_company_{company_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                'type': 'dashboard.update',
                'payload': await self.get_dashboard_payload(),
            }
        )

    async def disconnect(self, close_code):
        group_name = getattr(self, 'group_name', None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    async def dashboard_update(self, event):
        await self.send_json(
            {
                'type': 'dashboard.update',
                'payload': event.get('payload', {}),
            }
        )

    @database_sync_to_async
    def get_dashboard_payload(self):
        return get_dashboard_payload(self.scope['user'].company)
