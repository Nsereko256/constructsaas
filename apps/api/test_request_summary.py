from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.finance.factories import FinanceFixtureFactory
from apps.procurement.models import PurchaseRequest, PurchaseRequestItem


class MaterialRequestRegisterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fixture = FinanceFixtureFactory('MRRegister')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.fixture.admin)

    def request(self, number, status='PENDING', **kwargs):
        return PurchaseRequest.objects.create(
            company=self.fixture.company, project=self.fixture.project,
            requested_by=self.fixture.engineer, title='Register QA',
            number=number, status=status, **kwargs,
        )

    def test_counts_and_estimate_cover_more_than_one_hundred_records(self):
        for index in range(101):
            self.request(f'MR-{index}')
        valued = self.request('MR-VALUED', 'STOCK_ISSUE_REQUESTED')
        rejected = self.request('MR-REJECTED', 'REJECTED')
        for request in [valued, rejected]:
            PurchaseRequestItem.objects.create(purchase_request=request, material=self.fixture.material, quantity=2)
        response = self.client.get('/api/purchase-requests/summary/?page_size=5')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 103)
        self.assertEqual(response.data['awaiting_approval'], 101)
        self.assertEqual(response.data['stock_queue'], 1)
        self.assertEqual(Decimal(response.data['estimated_value']), Decimal('70000'))
        queue = self.client.get('/api/purchase-requests/?action_queue=my_requests&page_size=5')
        self.assertEqual(response.data['my_queue'], queue.data['count'])

    def test_queue_order_is_applied_before_pagination_and_also_inside_queue(self):
        self.request('MR-OLD-REJECTED', 'REJECTED')
        first = self.request('MR-FIRST-PENDING')
        second = self.request('MR-SECOND-PENDING')
        for queue in ['', '&action_queue=my_requests']:
            page1 = self.client.get('/api/purchase-requests/?ordering=queue_rank,created_at,id&page_size=1' + queue)
            page2 = self.client.get('/api/purchase-requests/?ordering=queue_rank,created_at,id&page_size=1&page=2' + queue)
            self.assertEqual(page1.status_code, 200, page1.data)
            self.assertEqual(page1.data['results'][0]['id'], first.pk)
            self.assertEqual(page2.data['results'][0]['id'], second.pk)

    def test_stock_tab_matches_count_and_excludes_fulfilled_requests(self):
        for state in ['STOCK_ISSUE_REQUESTED', 'PARTIAL_STOCK_ISSUED', 'STOCK_ISSUED', 'APPROVED']:
            self.request(f'MR-{state}', state)
        summary = self.client.get('/api/purchase-requests/summary/').data
        register = self.client.get('/api/purchase-requests/?register_queue=stock').data
        self.assertEqual(summary['stock_queue'], 2)
        self.assertEqual(summary['stock_queue'], register['count'])
        self.assertEqual(summary['stock_fulfilled'], 1)
        self.assertEqual({row['status'] for row in register['results']}, {'STOCK_ISSUE_REQUESTED', 'PARTIAL_STOCK_ISSUED'})

    def test_summary_preserves_company_scope_and_engineer_price_privacy(self):
        self.request('MR-MINE', 'RETURNED')
        other = FinanceFixtureFactory('OtherMRRegister')
        other.purchase_request()
        PurchaseRequest.objects.create(company=self.fixture.company, number='MR-ANOTHER-REQUESTER', title='Other', requested_by=self.fixture.admin)
        self.client.force_authenticate(self.fixture.engineer)
        response = self.client.get('/api/purchase-requests/summary/')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['my_queue'], 1)
        self.assertNotIn('estimated_value', response.data)
        self.assertEqual(self.client.get('/api/purchase-requests/summary/?search=unmatched').data['count'], 0)

    def test_summary_uses_same_manager_project_scope_as_list(self):
        self.request('MR-ASSIGNED')
        PurchaseRequest.objects.create(company=self.fixture.company, number='MR-NO-PROJECT', title='Unassigned', requested_by=self.fixture.admin)
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.get('/api/purchase-requests/summary/')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['my_queue'], 1)
