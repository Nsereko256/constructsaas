import json

from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase
from django.urls import path

from apps.accounts.models import Company, User

from .consumers import ChatConsumer
from .models import ChatMessage, Project


websocket_application = URLRouter(
    [
        path('ws/chat/<int:project_id>/', ChatConsumer.as_asgi()),
    ]
)


class ProjectChatConsumerTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Demo Construction')
        self.other_company = Company.objects.create(name='Other Construction')
        self.user = User.objects.create_user(
            username='manager',
            password='password',
            company=self.company,
            role=User.ROLE_PROJECT_MANAGER,
        )
        self.other_user = User.objects.create_user(
            username='outsider',
            password='password',
            company=self.other_company,
            role=User.ROLE_PROJECT_MANAGER,
        )
        self.second_user = User.objects.create_user(
            username='engineer',
            password='password',
            company=self.company,
            role=User.ROLE_SITE_ENGINEER,
        )
        self.no_company_user = User.objects.create_user(
            username='no_company',
            password='password',
            role=User.ROLE_PROJECT_MANAGER,
        )
        self.project = Project.objects.create(
            company=self.company,
            name='Tower Site',
            code='TS-001',
            manager=self.user,
        )
        self.project.site_engineers.add(self.second_user)
        self.room_id = self.project.chat_room.id

    def test_allows_company_user_and_broadcasts_message(self):
        async_to_sync(self._test_allows_company_user_and_broadcasts_message)()

    async def _test_allows_company_user_and_broadcasts_message(self):
        await ChatMessage.objects.acreate(
            room_id=self.room_id,
            content='Old connection update.',
            is_system_message=True,
        )
        await ChatMessage.objects.acreate(
            room_id=self.room_id,
            sender=self.user,
            content='Existing typed message.',
        )
        communicator = WebsocketCommunicator(
            websocket_application,
            f'/ws/chat/{self.project.pk}/',
        )
        communicator.scope['user'] = self.user

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        history_payload = await communicator.receive_json_from()
        self.assertEqual(history_payload['type'], 'chat.history')
        self.assertEqual(len(history_payload['messages']), 1)
        self.assertEqual(history_payload['messages'][0]['content'], 'Existing typed message.')
        self.assertFalse(history_payload['messages'][0]['is_system_message'])

        await communicator.send_to(text_data=json.dumps({'message': 'Cement delivered to site.'}))
        message_payload = await communicator.receive_json_from()

        self.assertEqual(message_payload['type'], 'chat.message')
        self.assertEqual(message_payload['message']['content'], 'Cement delivered to site.')
        self.assertEqual(message_payload['message']['sender'], 'manager')
        self.assertFalse(message_payload['message']['is_system_message'])
        self.assertTrue(
            await ChatMessage.objects.filter(
                room_id=self.room_id,
                sender=self.user,
                content='Cement delivered to site.',
            ).aexists()
        )

        await communicator.disconnect()

    def test_broadcasts_message_to_second_company_user_in_room(self):
        async_to_sync(self._test_broadcasts_message_to_second_company_user_in_room)()

    async def _test_broadcasts_message_to_second_company_user_in_room(self):
        first = WebsocketCommunicator(
            websocket_application,
            f'/ws/chat/{self.project.pk}/',
        )
        first.scope['user'] = self.user
        second = WebsocketCommunicator(
            websocket_application,
            f'/ws/chat/{self.project.pk}/',
        )
        second.scope['user'] = self.second_user

        connected, _ = await first.connect()
        self.assertTrue(connected)
        await first.receive_json_from()

        connected, _ = await second.connect()
        self.assertTrue(connected)
        await second.receive_json_from()

        await first.send_to(text_data=json.dumps({'message': 'Please confirm Y12 stock at gate.'}))
        first_payload = await first.receive_json_from()
        second_payload = await second.receive_json_from()

        self.assertEqual(first_payload['message']['content'], 'Please confirm Y12 stock at gate.')
        self.assertEqual(second_payload['message']['content'], 'Please confirm Y12 stock at gate.')

        await first.disconnect()
        await second.disconnect()

    def test_rejects_user_from_another_company(self):
        async_to_sync(self._test_rejects_user_from_another_company)()

    async def _test_rejects_user_from_another_company(self):
        communicator = WebsocketCommunicator(
            websocket_application,
            f'/ws/chat/{self.project.pk}/',
        )
        communicator.scope['user'] = self.other_user

        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    def test_rejects_user_without_company(self):
        async_to_sync(self._test_rejects_user_without_company)()

    async def _test_rejects_user_without_company(self):
        communicator = WebsocketCommunicator(
            websocket_application,
            f'/ws/chat/{self.project.pk}/',
        )
        communicator.scope['user'] = self.no_company_user

        connected, _ = await communicator.connect()
        self.assertFalse(connected)
