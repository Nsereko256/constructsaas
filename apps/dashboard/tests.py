from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase
from django.urls import path

from apps.accounts.models import Company, User
from apps.materials.models import Category, Material
from apps.projects.models import Project
from apps.warehouse.models import StockMovement

from .consumers import DashboardConsumer
from .helpers import push_dashboard_update


websocket_application = URLRouter(
    [
        path('ws/dashboard/', DashboardConsumer.as_asgi()),
    ]
)


class DashboardConsumerTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Dashboard Demo')
        self.other_company = Company.objects.create(name='Other Dashboard Demo')
        self.user = User.objects.create_user(
            username='admin',
            password='password',
            company=self.company,
            role=User.ROLE_ADMIN,
        )
        self.other_user = User.objects.create_user(
            username='other-admin',
            password='password',
            company=self.other_company,
            role=User.ROLE_ADMIN,
        )
        self.no_company_user = User.objects.create_user(
            username='no-company-admin',
            password='password',
            role=User.ROLE_ADMIN,
        )
        self.category = Category.objects.create(company=self.company, name='Cement')
        self.material = Material.objects.create(
            company=self.company,
            category=self.category,
            name='Hima Cement',
            code='HC-001',
            unit=Material.UNIT_BAG,
            unit_price=35000,
            min_stock_level=10,
        )
        self.project = Project.objects.create(
            company=self.company,
            name='Office Block',
            code='OB-001',
        )
        StockMovement.objects.create(
            company=self.company,
            material=self.material,
            project=self.project,
            movement_type=StockMovement.MOVEMENT_IN,
            source=StockMovement.SOURCE_SUPPLIER,
            quantity=20,
            unit_price=35000,
            created_by=self.user,
        )

    def test_sends_dashboard_payload_on_connect(self):
        async_to_sync(self._test_sends_dashboard_payload_on_connect)()

    async def _test_sends_dashboard_payload_on_connect(self):
        communicator = WebsocketCommunicator(websocket_application, '/ws/dashboard/')
        communicator.scope['user'] = self.user

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        payload = await communicator.receive_json_from()
        self.assertEqual(payload['type'], 'dashboard.update')
        self.assertEqual(payload['payload']['total_active_materials'], 1)
        self.assertEqual(payload['payload']['active_projects'], 1)
        self.assertEqual(payload['payload']['stock_in_today'], '20')
        self.assertEqual(len(payload['payload']['recent_stock_movements']), 1)

        await communicator.disconnect()

    def test_rejects_user_without_company(self):
        async_to_sync(self._test_rejects_user_without_company)()

    async def _test_rejects_user_without_company(self):
        communicator = WebsocketCommunicator(websocket_application, '/ws/dashboard/')
        communicator.scope['user'] = self.no_company_user

        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    def test_push_dashboard_update_reaches_company_group(self):
        async_to_sync(self._test_push_dashboard_update_reaches_company_group)()

    async def _test_push_dashboard_update_reaches_company_group(self):
        communicator = WebsocketCommunicator(websocket_application, '/ws/dashboard/')
        communicator.scope['user'] = self.user

        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()

        await database_sync_to_async(push_dashboard_update)(self.company)
        payload = await communicator.receive_json_from()

        self.assertEqual(payload['type'], 'dashboard.update')
        self.assertEqual(payload['payload']['inventory_value'], '700000')

        await communicator.disconnect()

    def test_dashboard_updates_are_company_isolated(self):
        async_to_sync(self._test_dashboard_updates_are_company_isolated)()

    async def _test_dashboard_updates_are_company_isolated(self):
        first_company_socket = WebsocketCommunicator(websocket_application, '/ws/dashboard/')
        first_company_socket.scope['user'] = self.user
        second_company_socket = WebsocketCommunicator(websocket_application, '/ws/dashboard/')
        second_company_socket.scope['user'] = self.other_user

        connected, _ = await first_company_socket.connect()
        self.assertTrue(connected)
        connected, _ = await second_company_socket.connect()
        self.assertTrue(connected)
        await first_company_socket.receive_json_from()
        await second_company_socket.receive_json_from()

        await database_sync_to_async(push_dashboard_update)(self.company)
        payload = await first_company_socket.receive_json_from()
        self.assertEqual(payload['type'], 'dashboard.update')
        self.assertTrue(await second_company_socket.receive_nothing(timeout=0.2))

        await first_company_socket.disconnect()
        await second_company_socket.disconnect()
