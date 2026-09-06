from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.procurement.models import PurchaseOrder, PurchaseOrderItem

from .. import budget_services
from ..configuration_services import ensure_finance_settings
from ..factories import FinanceFixtureFactory
from ..models import BudgetTransaction, FinanceAuditEvent
from ..services import ensure_budget_clearance


class SoftFinanceFeatureTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('feature')
        self.settings = ensure_finance_settings(self.fixture.company)
        self.client = APIClient()

    def test_admin_can_toggle_the_module_and_change_is_audited(self):
        self.client.force_authenticate(self.fixture.admin)
        response = self.client.patch(
            f'/api/v1/finance/settings/{self.settings.pk}/',
            {'soft_finance_enabled': False, 'budget_control_mode': 'off'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.settings.refresh_from_db()
        self.assertFalse(self.settings.soft_finance_enabled)
        self.assertEqual(self.settings.budget_control_mode, 'off')
        self.assertTrue(FinanceAuditEvent.objects.filter(
            company=self.fixture.company,
            action='settings.updated',
            object_type='FinanceSettings',
        ).exists())

    def test_disabled_module_blocks_finance_api_but_exposes_state_to_the_session(self):
        self.settings.soft_finance_enabled = False
        self.settings.save(update_fields=['soft_finance_enabled'])
        self.client.force_authenticate(self.fixture.admin)

        finance = self.client.get('/api/v1/finance/dashboard/')
        me = self.client.get('/api/users/me/')
        settings = self.client.get(f'/api/v1/finance/settings/{self.settings.pk}/')

        self.assertEqual(finance.status_code, 403)
        self.assertIn('disabled', str(finance.data).lower())
        self.assertFalse(me.data['soft_finance_enabled'])
        self.assertEqual(settings.status_code, 200)

    def test_disabled_module_keeps_purchase_order_approval_operational_without_commitment(self):
        request = self.fixture.purchase_request()
        purchase_order = PurchaseOrder.objects.create(
            company=self.fixture.company,
            purchase_request=request,
            project=self.fixture.project,
            supplier=self.fixture.supplier,
            supplier_name=self.fixture.supplier.name,
            number='PO-FEATURE-0001',
            status=PurchaseOrder.STATUS_PENDING,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.fixture.material,
            quantity=Decimal('2.00'),
            unit_price=Decimal('35000.00'),
        )
        self.settings.soft_finance_enabled = False
        self.settings.save(update_fields=['soft_finance_enabled'])

        self.assertIsNone(ensure_budget_clearance(request))
        approved = budget_services.approve_purchase_order(
            purchase_order=purchase_order,
            user=self.fixture.procurement,
        )

        self.assertEqual(approved.status, PurchaseOrder.STATUS_ORDERED)
        self.assertFalse(BudgetTransaction.objects.filter(purchase_order=approved).exists())

    def test_optional_invoice_and_payment_tracking_are_enforced(self):
        self.settings.invoice_tracking_enabled = False
        self.settings.payment_tracking_enabled = False
        self.settings.save(update_fields=['invoice_tracking_enabled', 'payment_tracking_enabled'])
        self.client.force_authenticate(self.fixture.admin)

        invoices = self.client.get('/api/v1/finance/supplier-invoices/')
        payments = self.client.get('/api/v1/finance/payments/')

        self.assertEqual(invoices.status_code, 403)
        self.assertIn('invoice tracking is disabled', str(invoices.data).lower())
        self.assertEqual(payments.status_code, 403)
        self.assertIn('payment tracking is disabled', str(payments.data).lower())
