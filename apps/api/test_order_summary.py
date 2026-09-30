from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.finance.factories import FinanceFixtureFactory
from apps.procurement.models import PurchaseOrder, PurchaseOrderItem


class PurchaseOrderRegisterSummaryTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('Summary')
        self.client = APIClient()
        self.client.force_authenticate(self.fixture.admin)

    def order(self, number, **kwargs):
        return PurchaseOrder.objects.create(
            company=self.fixture.company, number=number,
            supplier=self.fixture.supplier,
            **kwargs,
        )

    def test_summary_counts_beyond_one_hundred_and_excludes_cancelled_value(self):
        for index in range(101):
            self.order(f'PO-{index}', status='PENDING')
        order = self.order('PO-VALUED', status='ORDERED')
        cancelled = self.order('PO-CANCELLED', status='CANCELLED')
        for record in [order, cancelled]:
            PurchaseOrderItem.objects.create(purchase_order=record, material=self.fixture.material, quantity=2, unit_price=25)
        other = FinanceFixtureFactory('OtherSummary')
        PurchaseOrder.objects.create(company=other.company, number='PO-OTHER')
        response = self.client.get('/api/purchase-orders/summary/?page_size=5')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 103)
        self.assertEqual(response.data['statuses']['PENDING'], 101)
        self.assertEqual(response.data['awaiting_delivery'], 1)
        self.assertEqual(Decimal(response.data['order_value']), Decimal(50))

    def test_summary_and_list_share_project_and_engineer_visibility(self):
        request = self.fixture.purchase_request()
        self.order('PO-MINE', purchase_request=request, project=self.fixture.project, status='ORDERED')
        self.order('PO-NOT-MINE', status='PENDING')
        self.client.force_authenticate(self.fixture.engineer)
        response = self.client.get('/api/purchase-orders/summary/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertNotIn('order_value', response.data)
        self.assertNotIn('site_value', response.data)
        self.assertEqual(self.client.get('/api/purchase-orders/summary/?status=PENDING').data['count'], 0)

    def test_delivery_sort_uses_revised_date_across_pages(self):
        late = self.order('PO-LATE', expected_delivery_date=date(2026, 9, 1), revised_delivery_date=date(2026, 10, 1), delivery_revision_reason='Supplier revised the delivery date.')
        early = self.order('PO-EARLY', expected_delivery_date=date(2026, 9, 20))
        first = self.client.get('/api/purchase-orders/?ordering=delivery_sort_date,id&page_size=1')
        second = self.client.get('/api/purchase-orders/?ordering=delivery_sort_date,id&page_size=1&page=2')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['results'][0]['id'], early.pk)
        self.assertEqual(second.data['results'][0]['id'], late.pk)
