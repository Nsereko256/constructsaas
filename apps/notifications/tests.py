from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase
from django.urls import path

from apps.accounts.models import Company, User
from apps.materials.models import Category, Material
from apps.procurement.models import PurchaseOrder, PurchaseOrderItem, PurchaseRequest
from apps.procurement.services import (
    notify_po_created_from_pr,
    notify_po_approved,
    notify_po_received,
    notify_pr_approved,
    notify_pr_rejected,
    notify_pr_submitted,
)
from apps.projects.models import Project
from apps.warehouse.models import StockMovement

from .consumers import NotificationConsumer
from .helpers import check_low_stock_for_company, send_notification
from .models import Notification


websocket_application = URLRouter(
    [
        path('ws/notifications/', NotificationConsumer.as_asgi()),
    ]
)


class NotificationRealtimeTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Realtime Construction')
        self.other_company = Company.objects.create(name='Outside Construction')
        self.admin = self.create_user('admin', User.ROLE_ADMIN)
        self.manager = self.create_user('manager', User.ROLE_PROJECT_MANAGER)
        self.engineer = self.create_user('engineer', User.ROLE_SITE_ENGINEER)
        self.procurement = self.create_user('procurement', User.ROLE_PROCUREMENT_OFFICER)
        self.storekeeper = self.create_user('storekeeper', User.ROLE_STOREKEEPER)
        self.finance_officer = self.create_user('finance_officer', User.ROLE_FINANCE_OFFICER)
        self.finance_manager = self.create_user('finance_manager', User.ROLE_FINANCE_MANAGER)
        self.no_company_user = User.objects.create_user(
            username='no_company',
            password='password',
            role=User.ROLE_ADMIN,
        )
        self.category = Category.objects.create(company=self.company, name='Steel')
        self.material = Material.objects.create(
            company=self.company,
            category=self.category,
            name='Y12 Steel Bar',
            code='Y12',
            unit=Material.UNIT_PIECE,
            unit_price=25000,
            min_stock_level=10,
        )
        self.project = Project.objects.create(
            company=self.company,
            name='Kampala Villas',
            code='KV-001',
            manager=self.manager,
        )
        self.purchase_request = PurchaseRequest.objects.create(
            company=self.company,
            project=self.project,
            number='PR-TEST-001',
            title='Steel for foundation',
            priority=PurchaseRequest.PRIORITY_HIGH,
            requested_by=self.engineer,
        )
        self.purchase_order = PurchaseOrder.objects.create(
            company=self.company,
            purchase_request=self.purchase_request,
            project=self.project,
            number='PO-TEST-001',
            supplier_name='Uganda Steel Supplies',
            status=PurchaseOrder.STATUS_PENDING,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=self.purchase_order,
            material=self.material,
            quantity=5,
            unit_price=25000,
        )

    def create_user(self, username, role):
        return User.objects.create_user(
            username=username,
            password='password',
            company=self.company,
            role=role,
        )

    async def connect_user(self, user):
        communicator = WebsocketCommunicator(websocket_application, '/ws/notifications/')
        communicator.scope['user'] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        initial_payload = await communicator.receive_json_from()
        self.assertEqual(initial_payload['type'], 'notification.count')
        return communicator

    def test_rejects_logged_in_user_without_company(self):
        async_to_sync(self._test_rejects_logged_in_user_without_company)()

    async def _test_rejects_logged_in_user_without_company(self):
        communicator = WebsocketCommunicator(websocket_application, '/ws/notifications/')
        communicator.scope['user'] = self.no_company_user

        connected, _ = await communicator.connect()

        self.assertFalse(connected)

    def test_bell_count_and_toast_payload_update_live(self):
        async_to_sync(self._test_bell_count_and_toast_payload_update_live)()

    async def _test_bell_count_and_toast_payload_update_live(self):
        communicator = await self.connect_user(self.admin)

        await database_sync_to_async(send_notification)(
            self.admin,
            Notification.TYPE_SYSTEM,
            Notification.LEVEL_INFO,
            'System check',
            'Realtime notifications are online.',
            '/dashboard/',
        )
        payload = await communicator.receive_json_from()

        self.assertEqual(payload['type'], 'notification.message')
        self.assertEqual(payload['unread_count'], 1)
        self.assertEqual(payload['notification']['title'], 'System check')
        self.assertEqual(payload['notification']['link'], '/dashboard/')

        await communicator.disconnect()

    def test_purchase_request_workflow_sends_live_notifications(self):
        async_to_sync(self._test_purchase_request_workflow_sends_live_notifications)()

    async def _test_purchase_request_workflow_sends_live_notifications(self):
        manager_socket = await self.connect_user(self.manager)
        await database_sync_to_async(notify_pr_submitted)(self.purchase_request)
        submitted_payload = await manager_socket.receive_json_from()
        self.assertEqual(submitted_payload['notification']['notification_type'], Notification.TYPE_PR_SUBMITTED)
        await manager_socket.disconnect()

        procurement_socket = await self.connect_user(self.procurement)
        requester_socket = await self.connect_user(self.engineer)
        await database_sync_to_async(notify_pr_approved)(self.purchase_request)
        procurement_payload = await procurement_socket.receive_json_from()
        requester_payload = await requester_socket.receive_json_from()
        self.assertEqual(procurement_payload['notification']['notification_type'], Notification.TYPE_PR_APPROVED)
        self.assertEqual(requester_payload['notification']['notification_type'], Notification.TYPE_PR_APPROVED)
        await procurement_socket.disconnect()
        await requester_socket.disconnect()

        self.purchase_request.rejection_reason = 'Budget needs revision.'
        requester_socket = await self.connect_user(self.engineer)
        await database_sync_to_async(notify_pr_rejected)(self.purchase_request)
        rejected_payload = await requester_socket.receive_json_from()
        self.assertEqual(rejected_payload['notification']['notification_type'], Notification.TYPE_PR_REJECTED)
        self.assertIn('Budget needs revision.', rejected_payload['notification']['message'])
        await requester_socket.disconnect()

    def test_purchase_order_workflow_sends_live_notifications(self):
        async_to_sync(self._test_purchase_order_workflow_sends_live_notifications)()

    async def _test_purchase_order_workflow_sends_live_notifications(self):
        requester_socket = await self.connect_user(self.engineer)
        finance_socket = await self.connect_user(self.finance_officer)
        await database_sync_to_async(notify_po_created_from_pr)(
            self.purchase_order,
            self.procurement,
        )
        created_payload = await requester_socket.receive_json_from()
        self.assertEqual(created_payload['notification']['notification_type'], Notification.TYPE_PO_CREATED)
        await requester_socket.disconnect()

        finance_created_payload = await finance_socket.receive_json_from()
        self.assertEqual(finance_created_payload['notification']['notification_type'], Notification.TYPE_PO_CREATED)
        self.assertIn('PO-TEST-001', finance_created_payload['notification']['title'])

        await database_sync_to_async(notify_po_approved)(self.purchase_order)
        finance_approved_payload = await finance_socket.receive_json_from()
        self.assertEqual(finance_approved_payload['notification']['notification_type'], Notification.TYPE_SYSTEM)
        self.assertIn('PO approved', finance_approved_payload['notification']['title'])
        await finance_socket.disconnect()

        storekeeper_socket = await self.connect_user(self.storekeeper)
        await database_sync_to_async(notify_po_received)(self.purchase_order)
        received_payload = await storekeeper_socket.receive_json_from()
        self.assertEqual(received_payload['notification']['notification_type'], Notification.TYPE_PO_RECEIVED)
        self.assertIn('Uganda Steel Supplies', received_payload['notification']['message'])
        await storekeeper_socket.disconnect()

    def test_low_stock_notification_is_live_and_not_duplicated(self):
        async_to_sync(self._test_low_stock_notification_is_live_and_not_duplicated)()

    async def _test_low_stock_notification_is_live_and_not_duplicated(self):
        storekeeper_socket = await self.connect_user(self.storekeeper)

        await database_sync_to_async(check_low_stock_for_company)(self.company)
        low_stock_payload = await storekeeper_socket.receive_json_from()
        self.assertEqual(low_stock_payload['notification']['notification_type'], Notification.TYPE_LOW_STOCK)

        await database_sync_to_async(check_low_stock_for_company)(self.company)
        self.assertTrue(await storekeeper_socket.receive_nothing(timeout=0.2))
        unread_low_stock_count = await Notification.objects.filter(
            company=self.company,
            recipient=self.storekeeper,
            notification_type=Notification.TYPE_LOW_STOCK,
            is_read=False,
        ).acount()
        self.assertEqual(unread_low_stock_count, 1)

        await storekeeper_socket.disconnect()
