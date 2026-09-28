from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import Company, User
from apps.finance.models import FinanceAuditEvent
from apps.materials.models import Category, Material
from apps.projects.models import Project
from apps.notifications.models import Notification
from .models import ExternalMoveOrder, ExternalStockEvent, StockMovement, Warehouse, BinLocation
from .valuation_services import valuation_state, record_opening_balance
from . import valuation_services


class ExternalTransferTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='External transfers QA')
        self.admin = User.objects.create_user(username='external-admin', company=self.company, role='admin')
        self.store = User.objects.create_user(username='external-store', company=self.company, role='storekeeper')
        self.procurement = User.objects.create_user(username='external-procurement', company=self.company, role='procurement_officer')
        self.engineer = User.objects.create_user(username='external-engineer', company=self.company, role='site_engineer')
        self.finance = User.objects.create_user(username='external-finance', company=self.company, role='finance_manager')
        self.category = Category.objects.create(company=self.company, name='Materials')
        self.material = Material.objects.create(company=self.company, category=self.category, name='Cement', code='CEM', unit='bag')
        self.other_material = Material.objects.create(company=self.company, category=self.category, name='Bricks', code='BRK', unit='piece')
        self.warehouse = Warehouse.objects.create(company=self.company, name='Warehouse', code='MAIN', is_default=True)
        self.project = Project.objects.create(company=self.company, name='Project', code='P')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.date = timezone.localdate().isoformat()

    def create_order(self, ownership='PERMANENT', **overrides):
        body = dict(sender='Neighbour Ltd', reference=f'MOVE-{ExternalMoveOrder.objects.count() + 1}', ownership=ownership,
                    warehouse=self.warehouse.pk, expected_date=self.date, return_due_date=self.date,
                    lines=[dict(material=self.material.pk, quantity='10', unit_cost='100')])
        body.update(overrides)
        result = self.client.post('/api/external-move-orders/', body, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        return result.data

    def action(self, order, action, body, status=200):
        result = self.client.post(f'/api/external-move-orders/{order["id"]}/{action}/', body, format='json')
        self.assertEqual(result.status_code, status, result.data)
        return result.data

    def receive(self, order, accepted='10', reference='DEL-001', **extra):
        return self.action(order, 'receive', dict(reference=reference, received_date=self.date,
            lines=[dict(order_line=order['lines'][0]['id'], accepted=accepted)], **extra))

    def post_receipt(self, order, **extra):
        return self.action(order, 'review', dict(receipt_id=order['receipts'][0]['id'], decision='post', reason='Verified delivery document and count.', **extra))

    def stock_action(self, order, action='OWNER_RETURN', quantity='1', status=200, **extra):
        return self.action(order, 'stock-action', dict(line_id=order['lines'][0]['id'], action=action, quantity=quantity,
            reason='Authorized physical material handover.', request_key=str(uuid4()), **extra), status=status)

    def test_permanent_requires_receipt_then_admin_post_and_approved_cost(self):
        self.client.force_authenticate(self.procurement)
        order = self.create_order()
        self.receive_forbidden(order)
        self.client.force_authenticate(self.store)
        order = self.receive(order)
        self.assertEqual(self.material.current_stock, 0)
        self.action(order, 'review', dict(receipt_id=order['receipts'][0]['id'], decision='post', reason='Admin has to approve this.'), status=403)
        self.client.force_authenticate(self.admin)
        order = self.post_receipt(order, costs={str(order['lines'][0]['id']): '120.50'})
        state = valuation_state(company=self.company, material=self.material, warehouse=self.warehouse)
        self.assertEqual(state['quantity'], 10)
        self.assertEqual(state['value'], Decimal('1205'))
        self.assertEqual(order['receipts'][0]['lines'][0]['posted_unit_cost'], '120.500000')
        movement = StockMovement.objects.get()
        self.assertIsNone(movement.purchase_order_id)
        self.assertEqual(movement.transaction_type, 'EXTERNAL_RECEIPT')
        self.assertTrue(Notification.objects.filter(recipient=self.admin, title__icontains='awaiting approval').exists())
        self.assertTrue(FinanceAuditEvent.objects.filter(object_type='ExternalMoveOrder').exists())
        self.action(order, 'review', dict(receipt_id=order['receipts'][0]['id'], decision='post', reason='Repeat approval must fail.'), status=400)
        self.assertEqual(StockMovement.objects.count(), 1)

    def receive_forbidden(self, order):
        self.action(order, 'receive', dict(reference='DEL', received_date=self.date, lines=[dict(order_line=order['lines'][0]['id'], accepted=10)]), status=403)

    def test_partial_and_pending_receipts_reserve_quantities_and_exclude_exceptions(self):
        order = self.create_order()
        order = self.action(order, 'receive', dict(reference='PART-A', received_date=self.date, notes='Two bags damaged on arrival.',
            lines=[dict(order_line=order['lines'][0]['id'], accepted=4, damaged=2)]))
        self.assertEqual(order['lines'][0]['remaining'], '6.00')
        self.action(order, 'receive', dict(reference='OVER', received_date=self.date, lines=[dict(order_line=order['lines'][0]['id'], accepted=7)]), status=400)
        order = self.post_receipt(order)
        self.assertEqual(self.material.current_stock, 4)
        order = self.receive(order, accepted='6', reference='PART-B')
        order = self.post_receipt(order)
        self.assertEqual(order['status'], 'Fully received')
        self.assertEqual(self.material.current_stock, 10)

    def test_duplicate_sender_reference_and_duplicate_receipt_are_blocked(self):
        order = self.create_order(reference=' MOVE 123 ')
        result = self.client.post('/api/external-move-orders/', dict(sender='neighbour ltd', reference='move 123', ownership='PERMANENT', warehouse=self.warehouse.pk, expected_date=self.date, lines=[dict(material=self.material.pk, quantity=1)]), format='json')
        self.assertEqual(result.status_code, 400)
        order = self.receive(order, accepted='2')
        self.action(order, 'receive', dict(reference=' del-001 ', received_date=self.date, lines=[dict(order_line=order['lines'][0]['id'], accepted=2)]), status=400)
        self.assertEqual(ExternalMoveOrder.objects.count(), 1)

    def test_borrowed_issue_project_return_and_owner_return_keep_ownership_separate(self):
        order = self.post_receipt(self.receive(self.create_order('BORROWED')))
        self.assertEqual(self.material.current_stock, 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        order = self.stock_action(order, 'ISSUE', '6', project=self.project.pk)
        self.assertEqual(order['lines'][0]['held'], '4.00')
        self.assertEqual(order['lines'][0]['outstanding'], '10.00')
        self.stock_action(order, quantity='5', status=400)
        self.stock_action(order, 'PROJECT_RETURN', '7', project=self.project.pk, status=400)
        order = self.stock_action(order, 'PROJECT_RETURN', '6', project=self.project.pk)
        order = self.stock_action(order, quantity='10')
        self.assertEqual(order['lines'][0]['held'], '0.00')
        self.assertEqual(order['lines'][0]['outstanding'], '0.00')
        self.assertEqual(self.material.current_stock, 0)

    def test_borrowed_owners_do_not_share_balances_and_return_replay_is_rejected(self):
        order = self.post_receipt(self.receive(self.create_order('BORROWED')))
        other = self.post_receipt(self.receive(self.create_order('BORROWED', sender='Another company')))
        request_key = str(uuid4())
        payload = dict(line_id=order['lines'][0]['id'], action='OWNER_RETURN', quantity=10, reason='All borrowed bags returned.', request_key=request_key)
        self.action(order, 'stock-action', payload)
        self.action(order, 'stock-action', payload, status=400)
        self.stock_action(order, quantity='1', status=400)
        result = self.client.get(f'/api/external-move-orders/{other["id"]}/')
        self.assertEqual(result.data['lines'][0]['held'], '10.00')

    def test_permanent_return_uses_average_valuation(self):
        record_opening_balance(user=self.store, material=self.material, warehouse=self.warehouse, quantity=10, unit_cost=200, date=timezone.localdate(), reason='Approved inventory baseline.')
        order = self.post_receipt(self.receive(self.create_order()))
        self.stock_action(order, quantity='2')
        state = valuation_state(company=self.company, material=self.material, warehouse=self.warehouse)
        self.assertEqual(state['quantity'], 18)
        self.assertEqual(state['value'], 2700)
        self.stock_action(order, 'ISSUE', quantity='1', project=self.project.pk, status=400)

    def test_reversal_preserves_audit_and_stock_history(self):
        for ownership in ['PERMANENT', 'BORROWED']:
            order = self.post_receipt(self.receive(self.create_order(ownership)))
            order = self.action(order, 'reverse', dict(receipt_id=order['receipts'][0]['id'], reason='Incorrect count; physically verified again.'))
            self.assertEqual(order['receipts'][0]['status'], 'REVERSED')
            self.assertEqual(order['lines'][0]['received'], '0.00')
            self.assertEqual(self.material.current_stock, 0)
            self.action(order, 'reverse', dict(receipt_id=order['receipts'][0]['id'], reason='Cannot reverse twice.'), status=400)

    def test_reversal_blocked_after_downstream_use(self):
        order = self.post_receipt(self.receive(self.create_order('BORROWED')))
        order = self.stock_action(order, 'ISSUE', '1', project=self.project.pk)
        self.action(order, 'reverse', dict(receipt_id=order['receipts'][0]['id'], reason='Cannot erase downstream issue.'), status=400)
        self.assertEqual(ExternalStockEvent.objects.filter(action='REVERSE').count(), 0)

    def test_rejection_releases_receipt_allocation_and_close_keeps_return_obligation(self):
        order = self.receive(self.create_order('BORROWED'), accepted='6')
        order = self.action(order, 'review', dict(receipt_id=order['receipts'][0]['id'], decision='reject', reason='Please recount the delivery.'))
        self.assertEqual(order['lines'][0]['remaining'], '10.00')
        order = self.post_receipt(self.receive(order, reference='RECOUNT'))
        order = self.action(order, 'close', dict(reason='All expected deliveries completed.'))
        self.assertTrue(order['closed'])
        self.action(order, 'receive', dict(reference='AFTER-CLOSE', received_date=self.date, lines=[dict(order_line=order['lines'][0]['id'], accepted=1)]), status=400)
        order = self.stock_action(order, quantity='10')
        self.assertEqual(order['lines'][0]['outstanding'], '0.00')

    def test_tenant_role_and_price_boundaries(self):
        order = self.create_order()
        other = Company.objects.create(name='Other tenant')
        outsider = User.objects.create_user(username='outsider', company=other, role='admin')
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.get(f'/api/external-move-orders/{order["id"]}/').status_code, 404)
        self.assertEqual(self.client.get('/api/external-move-orders/').data['count'], 0)
        self.client.force_authenticate(self.engineer)
        self.assertEqual(self.client.get('/api/external-move-orders/').status_code, 403)
        self.client.force_authenticate(self.finance)
        self.assertEqual(self.client.get('/api/external-move-orders/').status_code, 200)
        self.receive_forbidden(order)

    def test_invalid_and_cross_company_inputs_rollback(self):
        foreign = Company.objects.create(name='Foreign materials')
        category = Category.objects.create(company=foreign, name='Foreign')
        material = Material.objects.create(company=foreign, category=category, name='Foreign', code='F', unit='bag')
        foreign_warehouse = Warehouse.objects.create(company=foreign, name='Foreign', code='F')
        bin_location = BinLocation.objects.create(warehouse=foreign_warehouse, code='B')
        valid = dict(sender='Sender', reference='INVALID', ownership='PERMANENT', warehouse=self.warehouse.pk, expected_date=self.date)
        for line in [dict(material=material.pk, quantity=1), dict(material=self.material.pk, quantity=-1), dict(material=self.material.pk, quantity=1, unit_cost=-1), dict(material=self.material.pk, quantity=1, bin_location=bin_location.pk)]:
            response = self.client.post('/api/external-move-orders/', dict(**valid, lines=[line]), format='json')
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ExternalMoveOrder.objects.count(), 0)

    def test_receipt_of_wrong_line_is_rejected_atomically(self):
        order = self.create_order()
        other = self.create_order()
        self.action(order, 'receive', dict(reference='WRONG', received_date=self.date, lines=[dict(order_line=other['lines'][0]['id'], accepted=1)]), status=400)
        self.assertFalse(ExternalMoveOrder.objects.get(pk=order['id']).receipts.exists())

    def test_multi_material_posting_is_atomic_and_reversal_blocks_later_valuations(self):
        order = self.create_order(lines=[dict(material=self.material.pk, quantity=10, unit_cost=100), dict(material=self.other_material.pk, quantity=5, unit_cost=10)])
        order = self.action(order, 'receive', dict(reference='MULTI', received_date=self.date,
            lines=[dict(order_line=line['id'], accepted=line['quantity']) for line in order['lines']]))
        self.action(order, 'review', dict(receipt_id=order['receipts'][0]['id'], decision='post', reason='Verify invalid cost rejection.', costs={str(order['lines'][1]['id']): '-1'}), status=400)
        self.assertFalse(StockMovement.objects.exists())
        order = self.post_receipt(order)
        other = self.post_receipt(self.receive(self.create_order()))
        self.action(order, 'reverse', dict(receipt_id=order['receipts'][0]['id'], reason='Cannot reverse past subsequent receipts.'), status=400)
        self.assertEqual(self.material.current_stock, 20)
        self.assertEqual(self.other_material.current_stock, 5)
        self.assertTrue(other['receipts'])

    def test_register_pagination_filter_and_no_edit_or_delete(self):
        for i in range(6):
            self.create_order('BORROWED' if i == 5 else 'PERMANENT')
        response = self.client.get('/api/external-move-orders/?page_size=5')
        self.assertEqual(response.data['count'], 6)
        self.assertEqual(len(response.data['results']), 5)
        self.assertIsNotNone(response.data['next'])
        response = self.client.get('/api/external-move-orders/?ownership=BORROWED')
        self.assertEqual(response.data['count'], 1)
        order_id = response.data['results'][0]['id']
        self.assertEqual(self.client.patch(f'/api/external-move-orders/{order_id}/', {'sender': 'Changed'}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(f'/api/external-move-orders/{order_id}/').status_code, 405)

    def test_borrowed_due_date_and_admin_reason_are_required(self):
        response = self.client.post('/api/external-move-orders/', dict(sender='Sender', reference='NO-DUE', ownership='BORROWED', warehouse=self.warehouse.pk, expected_date=self.date, lines=[dict(material=self.material.pk, quantity=1)]), format='json')
        self.assertEqual(response.status_code, 400)
        order = self.receive(self.create_order())
        self.action(order, 'review', dict(receipt_id=order['receipts'][0]['id'], decision='post', reason='short'), status=400)
        self.assertFalse(StockMovement.objects.exists())

    def workbook_sheets(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        with ZipFile(BytesIO(response.content)) as book:
            for name in book.namelist():
                if name.endswith('.xml') or name.endswith('.rels'):
                    ET.fromstring(book.read(name))
            return [book.read(name).decode() for name in book.namelist() if name.startswith('xl/worksheets/')]

    def test_move_order_exports_include_approved_values_and_do_not_post_stock(self):
        order = self.create_order()
        order = self.post_receipt(self.receive(order), costs={str(order['lines'][0]['id']): '120.50'})
        before = (StockMovement.objects.count(), ExternalStockEvent.objects.count())
        response = self.client.get(f'/api/external-move-orders/{order["id"]}/download/xlsx/')
        sheets = self.workbook_sheets(response)
        self.assertEqual(len(sheets), 4)
        self.assertIn('120.50', sheets[1])
        self.assertIn('Latest approved value', sheets[1])
        self.assertIn('120.500000', sheets[2])
        self.assertIn('POSTED', sheets[2])
        self.assertIn('Verified delivery document', sheets[2])
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        self.assertTrue(ET.fromstring(sheets[0]).findall('.//s:c[@s="3"]/s:v', ns))
        self.assertIn('private, no-store', response['Cache-Control'])
        pdf = self.client.get(f'/api/external-move-orders/{order["id"]}/download/pdf/')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF-'))
        self.assertEqual(pdf['Content-Disposition'], f'attachment; filename="move-order-MO-{order["id"]}.pdf"')
        self.assertEqual(before, (StockMovement.objects.count(), ExternalStockEvent.objects.count()))

    def test_borrowed_exports_preserve_owed_balances_without_valuation(self):
        order = self.post_receipt(self.receive(self.create_order('BORROWED')))
        order = self.stock_action(order, action='ISSUE', quantity='3', project=self.project.pk)
        sheets = self.workbook_sheets(self.client.get(f'/api/external-move-orders/{order["id"]}/download/xlsx/'))
        self.assertIn('Still owed to sender', sheets[1])
        self.assertIn('<v>7.00</v>', sheets[1])
        self.assertIn('<v>10.00</v>', sheets[1])
        self.assertNotIn('unit value (UGX)', ''.join(sheets))
        self.assertNotIn('Unit values', ''.join(sheets))
        self.assertFalse(StockMovement.objects.exists())

    def test_export_filters_all_pages_and_escapes_user_text(self):
        for index in range(6):
            self.create_order('BORROWED', sender='=HYPERLINK("https://example.invalid") & <Sender>', reference=f'BORROW-{index}')
        self.create_order('PERMANENT', reference='EXCLUDED')
        response = self.client.get('/api/external-move-orders/download/xlsx/?ownership=BORROWED&search=BORROW&page_size=1&page=2')
        sheets = self.workbook_sheets(response)
        for index in range(6):
            self.assertIn(f'BORROW-{index}', sheets[0])
        self.assertNotIn('EXCLUDED', sheets[0])
        self.assertIn('&amp; &lt;Sender&gt;', sheets[0])
        self.assertNotIn('<f>', sheets[0])
        self.assertIn('t="inlineStr"', sheets[0])
        empty = self.client.get('/api/external-move-orders/download/pdf/?pending=true')
        self.assertEqual(empty.status_code, 200)
        self.assertTrue(empty.content.startswith(b'%PDF-'))

    def test_export_access_is_tenant_scoped_and_role_protected(self):
        order = self.create_order()
        other_company = Company.objects.create(name='Foreign export tenant')
        other_admin = User.objects.create_user(username='foreign-export-admin', company=other_company, role='admin')
        for kind in ['pdf', 'xlsx']:
            path = f'/api/external-move-orders/{order["id"]}/download/{kind}/'
            self.client.force_authenticate(self.engineer)
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.get(f'/api/external-move-orders/download/{kind}/').status_code, 403)
            self.client.force_authenticate(other_admin)
            self.assertEqual(self.client.get(path).status_code, 404)
            self.client.force_authenticate(self.finance)
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_pdf_handles_long_names_notes_and_multiple_pages(self):
        order = self.create_order(sender='A & B <Partners> ' * 9, notes='Long transfer note for testing wrapping. ' * 95)
        event = FinanceAuditEvent.objects.get(object_id=str(order['id']), action='external_move_created')
        self.assertEqual(event.metadata['full_reason'], order['notes'])
        self.assertEqual(len(event.message), 500)
        for index in range(4):
            order = self.receive(order, accepted='1', reference=f'PART-{index}', notes='Delivery count & condition verified. ' * 10)
            order = self.post_receipt(order)
        response = self.client.get(f'/api/external-move-orders/{order["id"]}/download/pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertGreater(len(response.content), 4000)

    def test_retired_site_custody_rejects_api_and_service_writes(self):
        order = self.post_receipt(self.receive(self.create_order()))
        original = valuation_state(company=self.company, material=self.material, warehouse=self.warehouse)
        for url in ['dispatch-to-site', 'consume-site-stock', 'return-site-stock', 'site-transfers/999/acknowledge']:
            response = self.client.post(f'/api/stock-movements/{url}/', {}, format='json')
            self.assertEqual(response.status_code, 403, response.data)
            self.assertIn('disabled', str(response.data))
        args = dict(user=self.admin, material=self.material, project=self.project, warehouse=self.warehouse, quantity=1, date=self.date, reason='Attempt disabled operation.')
        for service in [valuation_services.dispatch_to_site, valuation_services.return_site_stock_to_warehouse]:
            with self.assertRaises(PermissionDenied):
                service(**args)
        with self.assertRaises(PermissionDenied):
            valuation_services.consume_site_stock(**{key: value for key, value in args.items() if key != 'warehouse'})
        with self.assertRaises(PermissionDenied):
            valuation_services.acknowledge_site_transfer(user=self.admin, site_transfer=999)
        self.assertEqual(valuation_state(company=self.company, material=self.material, warehouse=self.warehouse), original)
        self.assertEqual(self.client.get('/api/stock-movements/site-transfers/').status_code, 200)
        # External transfer receipts and returns are a separate, still-enabled workflow.
        self.stock_action(order, quantity='1')
