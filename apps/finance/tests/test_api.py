from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ..factories import FinanceFixtureFactory
from ..models import ApprovalMatrixRule, BudgetApproval, JournalEntry, Payment, SupplierInvoice


class FinanceApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('A')
        self.other = FinanceFixtureFactory('B')
        self.po, self.po_item = self.fixture.received_purchase_order()
        self.other_po, self.other_po_item = self.other.received_purchase_order()
        self.client = APIClient()

    def _invoice_json(self, fixture, po, po_item, key='api-invoice'):
        return {
            'purchase_order': po.id,
            'supplier': fixture.supplier.id,
            'invoice_number': f'API-{po.number}',
            'invoice_date': str(timezone.localdate()),
            'currency': 'UGX',
            'idempotency_key': key,
            'items': [{
                'purchase_order_item': po_item.id,
                'quantity': str(po_item.quantity),
                'unit_price': str(po_item.unit_price),
                'tax_amount': '0.00',
            }],
        }

    def test_complete_api_workflow_uses_dedicated_actions(self):
        self.client.force_authenticate(self.fixture.finance_officer)
        response = self.client.post(
            '/api/v1/finance/supplier-invoices/',
            self._invoice_json(self.fixture, self.po, self.po_item),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        invoice_id = response.data['id']
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/submit/').status_code, 200)
        self.assertEqual(
            self.client.post(
                f'/api/v1/finance/supplier-invoices/{invoice_id}/match/',
                {'tolerance': '0.00', 'idempotency_key': 'api-match'}, format='json',
            ).status_code,
            201,
        )

        self.client.force_authenticate(self.fixture.admin)
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/approve/').status_code, 200)
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/post/').status_code, 201)
        pay_response = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/pay/',
            {
                'amount': '350000.00', 'payment_date': str(timezone.localdate()),
                'method': Payment.METHOD_BANK, 'idempotency_key': 'api-payment',
            },
            format='json',
        )
        self.assertEqual(pay_response.status_code, 201, pay_response.data)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.filter(
            source_type__in=[JournalEntry.SOURCE_INVOICE, JournalEntry.SOURCE_PAYMENT],
        ).count(), 2)

        patch_response = self.client.patch(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/', {'status': SupplierInvoice.STATUS_DRAFT}, format='json',
        )
        self.assertEqual(patch_response.status_code, 400)
        self.assertIn('status', patch_response.data)

    def test_permissions_are_server_side(self):
        self.client.force_authenticate(self.fixture.engineer)
        self.assertEqual(self.client.get('/api/v1/finance/supplier-invoices/').status_code, 403)

        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.get('/api/v1/finance/supplier-invoices/').status_code, 200)
        self.assertEqual(
            self.client.post(
                '/api/v1/finance/supplier-invoices/',
                self._invoice_json(self.fixture, self.po, self.po_item), format='json',
            ).status_code,
            403,
        )

    def test_cross_company_records_are_hidden_and_relationships_rejected(self):
        self.client.force_authenticate(self.fixture.admin)
        other_response = self.client.post(
            '/api/v1/finance/supplier-invoices/',
            self._invoice_json(self.other, self.other_po, self.other_po_item, key='cross-company'),
            format='json',
        )
        self.assertEqual(other_response.status_code, 400)

        self.client.force_authenticate(self.other.admin)
        create_response = self.client.post(
            '/api/v1/finance/supplier-invoices/',
            self._invoice_json(self.other, self.other_po, self.other_po_item, key='other-invoice'),
            format='json',
        )
        self.assertEqual(create_response.status_code, 201, create_response.data)
        other_id = create_response.data['id']

        self.client.force_authenticate(self.fixture.admin)
        self.assertEqual(
            self.client.get(f'/api/v1/finance/supplier-invoices/{other_id}/').status_code,
            404,
        )
        list_response = self.client.get('/api/v1/finance/supplier-invoices/')
        self.assertEqual(list_response.data['count'], 0)

    def test_budget_actions_gate_purchase_order_creation(self):
        purchase_request = self.fixture.purchase_request()
        self.client.force_authenticate(self.fixture.procurement)
        create = self.client.post(
            '/api/v1/finance/budget-approvals/', {'purchase_request': purchase_request.id}, format='json',
        )
        self.assertEqual(create.status_code, 201, create.data)
        approval_id = create.data['id']
        pending_po = self.client.post(
            f'/api/purchase-orders/from-pr/{purchase_request.id}/',
            {'supplier': self.fixture.supplier.id}, format='json',
        )
        # Procurement may prepare a quoted draft PO before Finance review;
        # approval, dispatch, and receipt remain gated on the budget decision.
        self.assertEqual(pending_po.status_code, 201, pending_po.data)
        self.assertEqual(
            self.client.post(f'/api/v1/finance/budget-approvals/{approval_id}/submit/').status_code,
            200,
        )
        self.client.force_authenticate(self.fixture.admin)
        approved = self.client.post(f'/api/v1/finance/budget-approvals/{approval_id}/approve/')
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data['status'], BudgetApproval.STATUS_APPROVED)

    def test_approval_matrix_rules_are_company_scoped_and_configurable(self):
        self.client.force_authenticate(self.fixture.admin)
        response = self.client.post('/api/v1/finance/approval-matrix-rules/', {
            'document_type': ApprovalMatrixRule.DOCUMENT_INVOICE,
            'stage': ApprovalMatrixRule.STAGE_FINAL,
            'approver_role': 'finance_manager',
            'project': self.fixture.project.pk,
            'minimum_amount': '100.00',
            'maximum_amount': '1000000.00',
            'due_hours': 24,
            'escalation_hours': 48,
            'is_active': True,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['project'], self.fixture.project.pk)
        self.assertEqual(
            self.client.get('/api/v1/finance/approval-matrix-rules/').data['count'], 1,
        )
