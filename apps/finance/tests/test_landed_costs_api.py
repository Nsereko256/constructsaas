from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.materials.models import Material
from apps.procurement.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
)
from apps.procurement.services import record_goods_received_note
from apps.warehouse import valuation_services
from apps.warehouse.models import StockMovement

from ..factories import FinanceFixtureFactory
from ..models import BudgetApproval, FinanceSettings, LandedCostAllocation, LandedCostDocument


class LandedCostApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('LC')
        self.other = FinanceFixtureFactory('LC-OTHER')
        self.storekeeper = User.objects.create_user(
            username='landed-storekeeper', password='password', company=self.fixture.company,
            role=User.ROLE_STOREKEEPER,
        )
        self.second_material = Material.objects.create(
            company=self.fixture.company, category=self.fixture.category,
            name='Steel', code='LC-STEEL', unit=Material.UNIT_PIECE,
        )
        self.po = PurchaseOrder.objects.create(
            company=self.fixture.company, project=self.fixture.project,
            number='PO-LC-001', supplier=self.fixture.supplier,
            status=PurchaseOrder.STATUS_ORDERED,
        )
        self.first_po_item = PurchaseOrderItem.objects.create(
            purchase_order=self.po, material=self.fixture.material,
            quantity=Decimal('10.00'), unit_price=Decimal('100.00'),
        )
        self.second_po_item = PurchaseOrderItem.objects.create(
            purchase_order=self.po, material=self.second_material,
            quantity=Decimal('20.00'), unit_price=Decimal('200.00'),
        )
        _, self.grn = record_goods_received_note(
            purchase_order=self.po, user=self.storekeeper, receipt_date=timezone.localdate(),
            items=[
                {'purchase_order_item': self.first_po_item, 'accepted_quantity': Decimal('10.00')},
                {'purchase_order_item': self.second_po_item, 'accepted_quantity': Decimal('20.00')},
            ],
        )
        self.grn_items = list(self.grn.items.order_by('pk'))
        self.currency = FinanceSettings.objects.get(company=self.fixture.company).base_currency
        self.client = APIClient()
        self.counter = 0

    def create_document(self, method, *, actor=None, amount='300.00'):
        self.counter += 1
        self.client.force_authenticate(actor or self.fixture.finance_officer)
        response = self.client.post('/api/v1/finance/landed-costs/', {
            'number': f'LC-{self.counter:03d}', 'description': 'Receipt logistics costs',
            'allocation_method': method, 'currency': self.currency.pk,
            'exchange_rate': '1.000000', 'goods_received_notes': [self.grn.pk],
            'items': [
                {'cost_type': 'TRANSPORT', 'description': 'Transport', 'amount': amount},
            ],
            # Calculated totals supplied by clients must be ignored.
            'total_amount': '1.00', 'base_total_amount': '1.00',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['total_amount'], amount)
        return response.data['id']

    def preview(self, document_id, inputs=None, *, actor=None):
        self.client.force_authenticate(actor or self.fixture.finance_officer)
        response = self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/preview/',
            {'inputs': inputs or []}, format='json',
        )
        return response

    def submit_approve_post(self, document_id, key='post-landed-cost'):
        self.client.force_authenticate(self.fixture.finance_officer)
        submit = self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/submit/', {}, format='json',
        )
        self.assertEqual(submit.status_code, 200, submit.data)
        self.client.force_authenticate(self.fixture.finance_manager)
        approve = self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/approve/', {}, format='json',
        )
        self.assertEqual(approve.status_code, 200, approve.data)
        post = self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/post/',
            {'idempotency_key': key}, format='json',
        )
        self.assertEqual(post.status_code, 200, post.data)
        return post

    def allocation_amounts(self, response):
        return [row['allocated_amount'] for row in response.data['allocations']]

    def test_all_preview_methods_return_exact_item_level_allocations(self):
        cases = [
            (LandedCostDocument.ALLOCATION_QUANTITY, [], ['100.00', '200.00']),
            (LandedCostDocument.ALLOCATION_VALUE, [], ['60.00', '240.00']),
            (LandedCostDocument.ALLOCATION_EQUAL, [], ['150.00', '150.00']),
            (LandedCostDocument.ALLOCATION_WEIGHT, [
                {'goods_received_note_item': self.grn_items[0].pk, 'weight_per_unit': '2.000000'},
                {'goods_received_note_item': self.grn_items[1].pk, 'weight_per_unit': '1.000000'},
            ], ['150.00', '150.00']),
            (LandedCostDocument.ALLOCATION_MANUAL, [
                {'goods_received_note_item': self.grn_items[0].pk, 'manual_amount': '75.00'},
                {'goods_received_note_item': self.grn_items[1].pk, 'manual_amount': '225.00'},
            ], ['75.00', '225.00']),
        ]
        for method, inputs, expected in cases:
            with self.subTest(method=method):
                document_id = self.create_document(method)
                response = self.preview(document_id, inputs)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.allocation_amounts(response), expected)
                self.assertEqual(
                    sum((Decimal(value) for value in self.allocation_amounts(response)), Decimal('0')),
                    Decimal('300.00'),
                )

    def test_manual_preview_must_equal_approved_total(self):
        document_id = self.create_document(LandedCostDocument.ALLOCATION_MANUAL)
        response = self.preview(document_id, [
            {'goods_received_note_item': self.grn_items[0].pk, 'manual_amount': '10.00'},
            {'goods_received_note_item': self.grn_items[1].pk, 'manual_amount': '20.00'},
        ])
        self.assertEqual(response.status_code, 400)
        self.assertIn('inputs', response.data)

    def test_post_adds_inventory_value_and_preserves_historical_issue_cost(self):
        first_receipt = self.grn_items[0].stock_movement
        request = self.fixture.purchase_request(
            status=PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED,
            quantity=Decimal('1.00'),
        )
        item = request.items.get()
        BudgetApproval.objects.create(
            company=self.fixture.company,
            purchase_request=request,
            requested_amount=Decimal('35000.00'),
            status=BudgetApproval.STATUS_APPROVED,
            created_by=self.fixture.finance_officer,
            reviewed_by=self.fixture.finance_manager,
            submitted_at=timezone.now(),
            reviewed_at=timezone.now(),
        )
        issue = valuation_services.issue_stock_to_project(
            user=self.storekeeper, material=self.fixture.material,
            project=self.fixture.project, warehouse=first_receipt.warehouse,
            quantity=Decimal('1.00'), date=timezone.localdate(), reason='Pre-cost issue.',
            purchase_request=request, purchase_request_item=item,
        )
        document_id = self.create_document(LandedCostDocument.ALLOCATION_QUANTITY)
        self.assertEqual(self.preview(document_id).status_code, 200)
        movement_count = StockMovement.objects.count()
        post = self.submit_approve_post(document_id)
        self.assertEqual(post.data['status'], LandedCostDocument.STATUS_POSTED)
        self.assertEqual(StockMovement.objects.count(), movement_count + 2)

        first_state = valuation_services.valuation_state(
            company=self.fixture.company, material=self.fixture.material,
            warehouse=first_receipt.warehouse,
        )
        second_state = valuation_services.valuation_state(
            company=self.fixture.company, material=self.second_material,
            warehouse=self.grn_items[1].stock_movement.warehouse,
        )
        self.assertEqual(first_state['quantity'], Decimal('9.00'))
        self.assertEqual(first_state['value'], Decimal('1000.00'))
        self.assertEqual(first_state['average_rate'], Decimal('111.111111'))
        self.assertEqual(second_state['value'], Decimal('4200.00'))
        self.assertEqual(second_state['average_rate'], Decimal('210.000000'))
        issue.refresh_from_db()
        self.assertEqual(issue.valuation_rate, Decimal('100.000000'))
        self.assertEqual(issue.total_cost, Decimal('100.00'))

        self.client.force_authenticate(self.fixture.finance_manager)
        duplicate = self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/post/',
            {'idempotency_key': 'post-landed-cost'}, format='json',
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(StockMovement.objects.count(), movement_count + 2)
        another_key = self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/post/',
            {'idempotency_key': 'post-landed-cost-again'}, format='json',
        )
        self.assertEqual(another_key.status_code, 400)

    def test_reversal_restores_inventory_value_and_creates_immutable_records(self):
        document_id = self.create_document(LandedCostDocument.ALLOCATION_QUANTITY)
        self.preview(document_id)
        self.submit_approve_post(document_id, key='post-for-reversal')
        self.client.force_authenticate(self.fixture.finance_manager)
        response = self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/reverse/', {
                'reason': 'Carrier invoice was cancelled.',
                'idempotency_key': 'reverse-landed-cost',
            }, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], LandedCostDocument.STATUS_POSTED)
        self.assertEqual(response.data['reversal_of'], document_id)
        original = LandedCostDocument.objects.get(pk=document_id)
        self.assertEqual(original.status, LandedCostDocument.STATUS_REVERSED)
        self.assertEqual(original.allocations.filter(status='POSTED').count(), 2)
        self.assertEqual(response.data['allocations'][0]['status'], 'POSTED')

        state = valuation_services.valuation_state(
            company=self.fixture.company, material=self.fixture.material,
            warehouse=self.grn_items[0].stock_movement.warehouse,
        )
        self.assertEqual(state['value'], Decimal('1000.00'))
        allocation = LandedCostAllocation.objects.filter(document=original).first()
        allocation.allocated_amount = Decimal('999.00')
        with self.assertRaises(DjangoValidationError):
            allocation.save()
        patch = self.client.patch(
            f'/api/v1/finance/landed-costs/{document_id}/', {'description': 'Mutated'}, format='json',
        )
        self.assertEqual(patch.status_code, 400)

    def test_permissions_maker_checker_and_company_isolation(self):
        document_id = self.create_document(LandedCostDocument.ALLOCATION_EQUAL)
        self.preview(document_id)

        self.client.force_authenticate(self.fixture.finance_viewer)
        self.assertEqual(self.client.get('/api/v1/finance/landed-costs/').status_code, 200)
        self.assertEqual(self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/submit/', {}, format='json',
        ).status_code, 403)

        self.client.force_authenticate(self.fixture.finance_officer)
        self.client.post(f'/api/v1/finance/landed-costs/{document_id}/submit/', {}, format='json')
        self.assertEqual(self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/approve/', {}, format='json',
        ).status_code, 403)

        self.client.force_authenticate(self.other.finance_manager)
        self.assertEqual(self.client.get(
            f'/api/v1/finance/landed-costs/{document_id}/',
        ).status_code, 404)

        admin_document = self.create_document(
            LandedCostDocument.ALLOCATION_EQUAL, actor=self.fixture.admin,
        )
        self.preview(admin_document, actor=self.fixture.admin)
        self.client.post(
            f'/api/v1/finance/landed-costs/{admin_document}/submit/', {}, format='json',
        )
        self.assertEqual(self.client.post(
            f'/api/v1/finance/landed-costs/{admin_document}/approve/', {}, format='json',
        ).status_code, 400)
