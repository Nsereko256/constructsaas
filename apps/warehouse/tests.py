from decimal import Decimal
from threading import Barrier, Thread

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import Company, User
from apps.finance.configuration_services import ensure_finance_settings
from apps.finance.models import BudgetApproval, FinanceSettings
from apps.materials.models import Category, Material
from apps.procurement.models import (
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
)
from apps.projects.models import Project

from . import valuation_services
from .models import StockMovement, Warehouse


class ValuationFixture:
    def build_fixture(self, prefix='VAL'):
        self.company = Company.objects.create(name=f'{prefix} Construction', slug=prefix.lower())
        self.storekeeper = User.objects.create_user(
            username=f'{prefix.lower()}-store', password='pass', company=self.company,
            role=User.ROLE_STOREKEEPER,
        )
        self.finance_manager = User.objects.create_user(
            username=f'{prefix.lower()}-finance', password='pass', company=self.company,
            role=User.ROLE_FINANCE_MANAGER,
        )
        self.category = Category.objects.create(company=self.company, name='Cement')
        self.material = Material.objects.create(
            company=self.company, category=self.category, name='Cement', code=f'{prefix}-CEM',
            unit=Material.UNIT_BAG, unit_price=Decimal('999.00'),
        )
        self.project = Project.objects.create(
            company=self.company, name='Site A', code=f'{prefix}-SITE',
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company, name='Main Warehouse', code='MAIN', is_default=True,
        )

    def opening(self, quantity='10.00', unit_cost='100.00'):
        return valuation_services.record_opening_balance(
            user=self.storekeeper, material=self.material, warehouse=self.warehouse,
            quantity=Decimal(quantity), unit_cost=Decimal(unit_cost),
            date=timezone.localdate(), reason='Audited opening count.',
        )

    def approved_issue_request(self, quantity='20.00'):
        request = PurchaseRequest.objects.create(
            company=self.company,
            project=self.project,
            number=f'PR-ISSUE-{PurchaseRequest.objects.filter(company=self.company).count() + 1}',
            title='Finance-cleared warehouse issue',
            status=PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED,
            requested_by=self.storekeeper,
        )
        item = PurchaseRequestItem.objects.create(
            purchase_request=request,
            material=self.material,
            quantity=Decimal(quantity),
        )
        BudgetApproval.objects.create(
            company=self.company,
            purchase_request=request,
            requested_amount=(Decimal(quantity) * self.material.unit_price).quantize(Decimal('0.01')),
            status=BudgetApproval.STATUS_APPROVED,
            created_by=self.finance_manager,
            reviewed_by=self.finance_manager,
            submitted_at=timezone.now(),
            reviewed_at=timezone.now(),
        )
        return request, item

    def receipt_item(self, *, number, quantity, unit_cost):
        po = PurchaseOrder.objects.create(
            company=self.company, project=self.project, number=f'PO-{number}',
            supplier_name='Approved Supplier', status=PurchaseOrder.STATUS_ORDERED,
        )
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=po, material=self.material,
            quantity=Decimal(quantity), unit_price=Decimal(unit_cost),
        )
        grn = GoodsReceivedNote.objects.create(
            company=self.company, purchase_order=po, number=f'GRN-{number}',
            receipt_date=timezone.localdate(), received_by=self.storekeeper,
        )
        return GoodsReceivedNoteItem.objects.create(
            company=self.company, goods_received_note=grn, purchase_order_item=po_item,
            accepted_quantity=Decimal(quantity),
        )


class MovingAverageValuationTests(ValuationFixture, TestCase):
    def setUp(self):
        self.build_fixture()

    def test_weighted_average_receipt_and_historical_issue_cost_are_preserved(self):
        self.opening()
        receipt_item = self.receipt_item(number='001', quantity='10.00', unit_cost='200.00')
        receipt = valuation_services.receive_valued_stock(
            user=self.storekeeper, goods_received_note_item=receipt_item,
            warehouse=self.warehouse,
        )
        self.assertEqual(receipt.unit_cost, Decimal('200.000000'))
        self.assertEqual(receipt.valuation_rate, Decimal('150.000000'))

        request, item = self.approved_issue_request(quantity='4.00')
        issue = valuation_services.issue_stock_to_project(
            user=self.storekeeper, material=self.material, project=self.project,
            warehouse=self.warehouse, quantity=Decimal('4.00'),
            date=timezone.localdate(), reason='Site requisition.',
            purchase_request=request, purchase_request_item=item,
        )
        self.assertEqual(issue.valuation_rate, Decimal('150.000000'))
        self.assertEqual(issue.total_cost, Decimal('600.00'))

        self.material.unit_price = Decimal('5000.00')
        self.material.save(update_fields=['unit_price', 'updated_at'])
        another_item = self.receipt_item(number='002', quantity='2.00', unit_cost='300.00')
        valuation_services.receive_valued_stock(
            user=self.storekeeper, goods_received_note_item=another_item,
            warehouse=self.warehouse,
        )
        issue.refresh_from_db()
        self.assertEqual(issue.valuation_rate, Decimal('150.000000'))
        self.assertEqual(issue.total_cost, Decimal('600.00'))
        state = valuation_services.valuation_state(
            company=self.company, material=self.material, warehouse=self.warehouse,
        )
        self.assertEqual(state['quantity'], Decimal('18.00'))
        self.assertEqual(state['value'], Decimal('3000.00'))
        self.assertEqual(state['average_rate'], Decimal('166.666667'))

    def test_project_return_uses_original_issue_rate(self):
        self.opening(quantity='10.00', unit_cost='100.00')
        request, item = self.approved_issue_request(quantity='4.00')
        issue = valuation_services.issue_stock_to_project(
            user=self.storekeeper, material=self.material, project=self.project,
            warehouse=self.warehouse, quantity=Decimal('4.00'),
            date=timezone.localdate(), reason='Issued.',
            purchase_request=request, purchase_request_item=item,
        )
        receipt_item = self.receipt_item(number='003', quantity='4.00', unit_cost='200.00')
        valuation_services.receive_valued_stock(
            user=self.storekeeper, goods_received_note_item=receipt_item,
            warehouse=self.warehouse,
        )
        returned = valuation_services.return_stock_from_project(
            user=self.storekeeper, original_issue=issue, quantity=Decimal('2.00'),
            date=timezone.localdate(), reason='Unused bags returned.',
        )
        self.assertEqual(returned.unit_cost, Decimal('100.000000'))
        self.assertEqual(returned.total_cost, Decimal('200.00'))
        with self.assertRaises(ValidationError):
            valuation_services.return_stock_from_project(
                user=self.storekeeper, original_issue=issue, quantity=Decimal('3.00'),
                date=timezone.localdate(), reason='Too much.',
            )

    def test_supplier_return_writeoff_and_negative_stock_policy(self):
        self.opening(quantity='10.00', unit_cost='100.00')
        supplier_return = valuation_services.return_stock_to_supplier(
            user=self.storekeeper, material=self.material, warehouse=self.warehouse,
            quantity=Decimal('2.00'), date=timezone.localdate(), reason='Defective batch.',
        )
        writeoff = valuation_services.write_off_damaged_stock(
            user=self.storekeeper, material=self.material, warehouse=self.warehouse,
            quantity=Decimal('1.00'), date=timezone.localdate(), reason='Water damage.',
        )
        self.assertEqual(supplier_return.total_cost, Decimal('200.00'))
        self.assertEqual(writeoff.total_cost, Decimal('100.00'))
        request, item = self.approved_issue_request(quantity='20.00')
        with self.assertRaises(ValidationError):
            valuation_services.issue_stock_to_project(
                user=self.storekeeper, material=self.material, project=self.project,
                warehouse=self.warehouse, quantity=Decimal('20.00'),
                date=timezone.localdate(), reason='Blocked issue.',
                purchase_request=request, purchase_request_item=item,
            )
        settings = ensure_finance_settings(self.company)
        FinanceSettings.objects.filter(pk=settings.pk).update(
            negative_stock_policy=FinanceSettings.NEGATIVE_STOCK_ALLOW,
        )
        allowed = valuation_services.issue_stock_to_project(
            user=self.storekeeper, material=self.material, project=self.project,
            warehouse=self.warehouse, quantity=Decimal('20.00'),
            date=timezone.localdate(), reason='Policy-authorized issue.',
            purchase_request=request, purchase_request_item=item,
        )
        self.assertEqual(allowed.total_cost, Decimal('2000.00'))

    def test_supplier_return_uses_current_weighted_average_not_historical_receipt_cost(self):
        self.opening(quantity='10.00', unit_cost='100.00')
        receipt_item = self.receipt_item(number='AVG-RETURN', quantity='10.00', unit_cost='300.00')
        receipt = valuation_services.receive_valued_stock(
            user=self.storekeeper, goods_received_note_item=receipt_item,
            warehouse=self.warehouse,
        )
        returned = valuation_services.return_stock_to_supplier(
            user=self.storekeeper, material=self.material, warehouse=self.warehouse,
            quantity=Decimal('2.00'), date=timezone.localdate(),
            reason='Supplier return at current moving-average value.',
            original_receipt=receipt,
        )
        self.assertEqual(returned.unit_cost, Decimal('200.000000'))
        self.assertEqual(returned.total_cost, Decimal('400.00'))


class InventoryValuationApiTests(ValuationFixture, TestCase):
    def setUp(self):
        self.build_fixture('API-VAL')
        self.client = APIClient()
        self.opening()

    def test_legacy_api_cannot_bypass_finance_approved_issue_workflow(self):
        self.client.force_authenticate(self.storekeeper)
        response = self.client.post('/api/stock-movements/', {
            'material': self.material.pk, 'warehouse': self.warehouse.pk,
            'project': self.project.pk, 'movement_type': StockMovement.MOVEMENT_OUT,
            'source': StockMovement.SOURCE_SITE, 'quantity': '1.00',
            'unit_price': '1.00', 'date': str(timezone.localdate()),
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('movement_type', response.data)

    def test_valued_issue_action_requires_finance_approved_request(self):
        self.client.force_authenticate(self.storekeeper)
        response = self.client.post('/api/stock-movements/issue-stock-to-project/', {
            'material': self.material.pk,
            'warehouse': self.warehouse.pk,
            'project': self.project.pk,
            'quantity': '1.00',
            'date': str(timezone.localdate()),
            'reason': 'Site issue.',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('purchase_request', response.data)

    def test_manual_valuation_adjustment_requires_finance_authority_and_reason(self):
        url = '/api/stock-movements/adjust-valuation/'
        payload = {
            'material': self.material.pk, 'warehouse': self.warehouse.pk,
            'new_unit_cost': '120.000000', 'date': str(timezone.localdate()),
            'reason': 'Approved count-and-value reconciliation.',
        }
        self.client.force_authenticate(self.storekeeper)
        self.assertEqual(self.client.post(url, payload, format='json').status_code, 403)
        self.client.force_authenticate(self.finance_manager)
        missing_reason = {**payload, 'reason': ''}
        self.assertEqual(self.client.post(url, missing_reason, format='json').status_code, 400)
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['value_effect'], '200.00')
        self.assertEqual(response.data['authorized_by'], self.finance_manager.pk)

    def test_read_only_valuation_cost_history_and_reconciliation_are_isolated(self):
        request, item = self.approved_issue_request(quantity='2.00')
        issue = valuation_services.issue_stock_to_project(
            user=self.storekeeper, material=self.material, project=self.project,
            warehouse=self.warehouse, quantity=Decimal('2.00'),
            date=timezone.localdate(), reason='Site issue.',
            purchase_request=request, purchase_request_item=item,
        )
        other = Company.objects.create(name='Other Valuation Company', slug='other-valuation')
        other_user = User.objects.create_user(
            username='other-valuation-user', company=other, role=User.ROLE_STOREKEEPER,
        )
        other_category = Category.objects.create(company=other, name='Steel')
        other_material = Material.objects.create(
            company=other, category=other_category, name='Steel', code='OTHER-STEEL',
            unit=Material.UNIT_PIECE,
        )
        valuation_services.record_opening_balance(
            user=other_user, material=other_material, quantity=Decimal('50.00'),
            unit_cost=Decimal('500.00'), date=timezone.localdate(), reason='Other opening.',
        )

        self.client.force_authenticate(self.storekeeper)
        valuation = self.client.get('/api/inventory-valuations/')
        history = self.client.get('/api/stock-movements/valuation-history/')
        costs = self.client.get('/api/project-material-costs/')
        self.assertEqual(valuation.status_code, 200)
        self.assertEqual(valuation.data['count'], 1)
        self.assertEqual(valuation.data['results'][0]['current_value'], '800.00')
        self.assertNotIn(other_material.pk, [row['material'] for row in valuation.data['results']])
        self.assertEqual(history.data['count'], 2)
        self.assertEqual(costs.data['results'][0]['net_cost'], '200.00')

        self.client.force_authenticate(self.finance_manager)
        reconciliation = self.client.get('/api/valuation-reconciliation/')
        self.assertEqual(reconciliation.status_code, 200)
        self.assertEqual(reconciliation.data['results'][0]['status'], 'BALANCED')
        self.assertEqual(issue.total_cost, Decimal('200.00'))


@skipUnlessDBFeature('has_select_for_update')
class ConcurrentReceiptValuationTests(ValuationFixture, TransactionTestCase):
    """Executed on PostgreSQL; SQLite cannot exercise row-level material locks."""

    def setUp(self):
        self.build_fixture('CON-VAL')
        self.opening(quantity='10.00', unit_cost='100.00')
        self.items = [
            self.receipt_item(number='R1', quantity='10.00', unit_cost='200.00'),
            self.receipt_item(number='R2', quantity='10.00', unit_cost='300.00'),
        ]

    def test_concurrent_receipts_produce_one_correct_weighted_average(self):
        barrier = Barrier(2)
        outcomes = []

        def receive(item_id):
            close_old_connections()
            try:
                user = User.objects.get(pk=self.storekeeper.pk)
                barrier.wait()
                valuation_services.receive_valued_stock(
                    user=user, goods_received_note_item=item_id, warehouse=self.warehouse.pk,
                )
                outcomes.append('received')
            finally:
                close_old_connections()

        threads = [Thread(target=receive, args=(item.pk,)) for item in self.items]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes, ['received', 'received'])
        state = valuation_services.valuation_state(
            company=self.company, material=self.material, warehouse=self.warehouse,
        )
        self.assertEqual(state['quantity'], Decimal('30.00'))
        self.assertEqual(state['value'], Decimal('6000.00'))
        self.assertEqual(state['average_rate'], Decimal('200.000000'))
