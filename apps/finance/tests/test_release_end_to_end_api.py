from decimal import Decimal
from uuid import uuid4

from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.procurement.models import GoodsReceivedNote, PurchaseOrder, PurchaseRequest
from apps.warehouse import valuation_services
from apps.warehouse.models import StockMovement

from ..factories import FinanceFixtureFactory
from ..ledger_services import ensure_ledger_configuration
from ..models import (
    Account,
    BudgetCategory,
    Currency,
    FinanceSettings,
    FiscalPeriod,
    JournalEntry,
    JournalReversal,
    Payment,
    ProjectBudget,
    SupplierInvoice,
)


class FinanceReleaseEndToEndApiTests(TestCase):
    """Release-level journeys that exercise public APIs across app boundaries."""

    def setUp(self):
        self.fixture = FinanceFixtureFactory('RELEASE')
        self.other = FinanceFixtureFactory('RELEASE-OTHER')
        self.storekeeper = User.objects.create_user(
            username='release_storekeeper', password='password',
            company=self.fixture.company, role=User.ROLE_STOREKEEPER,
        )
        self.second_finance_manager = User.objects.create_user(
            username='release_finance_manager_two', password='password',
            company=self.fixture.company, role=User.ROLE_FINANCE_MANAGER,
        )
        self.fixture.project.site_engineers.add(self.fixture.engineer)
        ensure_ledger_configuration(self.fixture.company)
        self.currency = FinanceSettings.objects.get(company=self.fixture.company).base_currency
        self.cash = Account.objects.get(
            company=self.fixture.company, system_key=Account.SYSTEM_CASH,
        )
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def assert_status(self, response, expected):
        self.assertEqual(response.status_code, expected, response.data)
        return response

    def approved_budget(self, amount='1000000.00'):
        category = BudgetCategory.objects.create(
            company=self.fixture.company, code='MAT', name='Materials',
        )
        self.authenticate(self.fixture.finance_officer)
        created = self.assert_status(self.client.post('/api/v1/finance/budgets/', {
            'project': self.fixture.project.pk,
            'name': 'Approved construction budget',
            'lines': [{'category': category.pk, 'original_amount': amount}],
        }, format='json'), 201)
        budget_id = created.data['id']
        line_id = created.data['lines'][0]['id']
        self.assert_status(self.client.post(f'/api/v1/finance/budgets/{budget_id}/submit/'), 200)
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(
            f'/api/v1/finance/budgets/{budget_id}/approve/', {}, format='json',
        ), 200)
        return budget_id, line_id

    def approved_purchase_order(self, *, quantity='10.00', budget='1000000.00'):
        _, line_id = self.approved_budget(budget)
        self.authenticate(self.fixture.engineer)
        pr = self.assert_status(self.client.post('/api/purchase-requests/', {
            'project': self.fixture.project.pk,
            'title': 'Release journey materials',
            'priority': PurchaseRequest.PRIORITY_NORMAL,
            'items': [{'material': self.fixture.material.pk, 'quantity': quantity}],
        }, format='json'), 201)
        pr_id = pr.data['id']
        self.authenticate(self.fixture.manager)
        self.assert_status(self.client.post(f'/api/purchase-requests/{pr_id}/approve/'), 200)
        self.assert_status(self.client.post(
            f'/api/purchase-requests/{pr_id}/submit-finance/',
            {'budget_line': line_id}, format='json',
        ), 200)
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(
            f'/api/purchase-requests/{pr_id}/finance-approve/', {}, format='json',
        ), 200)
        self.authenticate(self.fixture.procurement)
        po = self.assert_status(self.client.post(
            f'/api/purchase-orders/from-pr/{pr_id}/',
            {'supplier': self.fixture.supplier.pk, 'delivery_destination': 'WAREHOUSE'},
            format='json',
        ), 201)
        po_id = po.data['id']
        self.assert_status(self.client.post(f'/api/purchase-orders/{po_id}/approve/'), 200)
        return pr_id, po_id, po.data['items'][0]['id']

    def receive(self, po_id, po_item_id=None, quantity=None):
        payload = {'receipt_date': str(timezone.localdate())}
        if quantity is not None:
            payload['items'] = [{
                'purchase_order_item': po_item_id,
                'accepted_quantity': str(quantity),
            }]
        self.authenticate(self.storekeeper)
        return self.assert_status(self.client.post(
            f'/api/purchase-orders/{po_id}/receive/', payload, format='json',
        ), 200)

    def posted_invoice(
        self, po_id, po_item_id, *, quantity='10.00', unit_price='35000.00',
        number=None, currency='UGX', exchange_rate='1.000000', approve_exception=False,
    ):
        number = number or f'RELEASE-INV-{uuid4().hex[:8]}'
        self.authenticate(self.fixture.finance_officer)
        created = self.assert_status(self.client.post('/api/v1/finance/supplier-invoices/', {
            'supplier': self.fixture.supplier.pk,
            'purchase_order': po_id,
            'invoice_number': number,
            'invoice_date': str(timezone.localdate()),
            'currency': currency,
            'exchange_rate': exchange_rate,
            'idempotency_key': f'create-{number}',
            'items': [{
                'purchase_order_item': po_item_id,
                'quantity': quantity,
                'unit_price': unit_price,
                'taxes': [],
            }],
        }, format='json'), 201)
        invoice_id = created.data['id']
        self.assert_status(self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/submit/',
        ), 200)
        match = self.assert_status(self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/run-match/',
            {'idempotency_key': f'match-{number}'}, format='json',
        ), 201)
        if approve_exception:
            self.authenticate(self.fixture.finance_manager)
            self.assert_status(self.client.post(
                f'/api/v1/finance/supplier-invoices/{invoice_id}/approve-exception/',
                {'reason': 'Authorized commercial variance.'}, format='json',
            ), 200)
        else:
            self.assertIn(match.data['status'], {'MATCHED', 'WITHIN_TOLERANCE'})
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/approve/',
        ), 200)
        self.assert_status(self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/post/',
            {'idempotency_key': f'post-{number}'}, format='json',
        ), 201)
        return invoice_id, match

    def posted_payment(self, invoice_id, amount, *, key='release-payment', exchange_rate='1.000000', currency=None):
        currency = currency or self.currency
        self.authenticate(self.fixture.finance_officer)
        payment = self.assert_status(self.client.post('/api/v1/finance/payments/', {
            'supplier': self.fixture.supplier.pk,
            'source_account': self.cash.pk,
            'currency': currency.pk,
            'exchange_rate': exchange_rate,
            'amount': amount,
            'payment_date': str(timezone.localdate()),
            'method': Payment.METHOD_BANK,
            'reference': f'REF-{key}',
            'idempotency_key': key,
        }, format='json'), 201)
        payment_id = payment.data['id']
        self.assert_status(self.client.post(
            f'/api/v1/finance/payments/{payment_id}/allocate/',
            {'invoice': invoice_id, 'amount': amount}, format='json',
        ), 201)
        self.assert_status(self.client.post(f'/api/v1/finance/payments/{payment_id}/submit/'), 200)
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(f'/api/v1/finance/payments/{payment_id}/approve/'), 200)
        self.assert_status(self.client.post(
            f'/api/v1/finance/payments/{payment_id}/post/',
            {'idempotency_key': f'post-{key}'}, format='json',
        ), 201)
        return payment_id

    def test_01_purchase_request_through_supplier_payment(self):
        _, po_id, po_item_id = self.approved_purchase_order()
        self.assertEqual(self.receive(po_id).data['status'], PurchaseOrder.STATUS_RECEIVED)
        invoice_id, _ = self.posted_invoice(po_id, po_item_id)
        payment_id = self.posted_payment(invoice_id, '350000.00')
        invoice = SupplierInvoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.status, SupplierInvoice.STATUS_PAID)
        self.assertEqual(Payment.objects.get(pk=payment_id).status, Payment.STATUS_POSTED)

    def test_02_partial_delivery_and_partial_invoice(self):
        _, po_id, po_item_id = self.approved_purchase_order()
        self.assertEqual(self.receive(po_id, po_item_id, '4.00').data['status'], PurchaseOrder.STATUS_PARTIAL)
        first_id, first_match = self.posted_invoice(
            po_id, po_item_id, quantity='4.00', number='PARTIAL-FIRST',
        )
        self.assertEqual(first_match.data['item_results'][0]['accepted_quantity'], '4.00')
        self.receive(po_id, po_item_id, '6.00')
        second_id, second_match = self.posted_invoice(
            po_id, po_item_id, quantity='6.00', number='PARTIAL-SECOND',
        )
        self.assertEqual(second_match.data['item_results'][0]['previously_invoiced_quantity'], '4.00')
        self.assertNotEqual(first_id, second_id)

    def test_03_matching_exception_and_finance_manager_override(self):
        _, po_id, po_item_id = self.approved_purchase_order()
        self.receive(po_id)
        invoice_id, match = self.posted_invoice(
            po_id, po_item_id, unit_price='36000.00', number='MATCH-OVERRIDE',
            approve_exception=True,
        )
        self.assertEqual(match.data['status'], 'EXCEPTION')
        self.assertEqual(SupplierInvoice.objects.get(pk=invoice_id).status, SupplierInvoice.STATUS_POSTED)

    def test_04_existing_warehouse_stock_is_issued_without_supplier(self):
        self.authenticate(self.storekeeper)
        self.assert_status(self.client.post('/api/stock-movements/record-opening-balance/', {
            'material': self.fixture.material.pk, 'quantity': '12.00',
            'unit_cost': '30000.000000', 'date': str(timezone.localdate()),
            'reason': 'Audited opening warehouse stock.',
        }, format='json'), 201)
        self.authenticate(self.fixture.engineer)
        pr = self.assert_status(self.client.post('/api/purchase-requests/', {
            'project': self.fixture.project.pk, 'title': 'Issue existing stock',
            'items': [{'material': self.fixture.material.pk, 'quantity': '5.00'}],
        }, format='json'), 201)
        self.authenticate(self.fixture.manager)
        self.assert_status(self.client.post(f"/api/purchase-requests/{pr.data['id']}/approve/"), 200)
        self.assert_status(self.client.post(
            f"/api/purchase-requests/{pr.data['id']}/submit-finance/",
            {'comments': 'Issue existing warehouse stock to the approved project.'},
            format='json',
        ), 200)
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(
            f"/api/purchase-requests/{pr.data['id']}/finance-approve/",
            {
                'override': True,
                'comments': 'Finance-approved stock release without new supplier purchase.',
            },
            format='json',
        ), 200)
        self.authenticate(self.fixture.admin)
        self.assert_status(self.client.post(f"/api/purchase-requests/{pr.data['id']}/approve-stock-issue/"), 200)
        self.authenticate(self.fixture.procurement)
        self.assert_status(self.client.post(f"/api/purchase-requests/{pr.data['id']}/issue-stock/"), 200)
        self.authenticate(self.storekeeper)
        self.assert_status(self.client.post(f"/api/purchase-requests/{pr.data['id']}/fulfill-stock/"), 200)
        self.assertFalse(PurchaseRequest.objects.get(pk=pr.data['id']).purchase_orders.exists())
        issue = StockMovement.objects.get(purchase_request_id=pr.data['id'])
        self.assertEqual(issue.total_cost, Decimal('150000.00'))

    def test_05_opening_stock_valuation(self):
        self.authenticate(self.storekeeper)
        movement = self.assert_status(self.client.post('/api/stock-movements/record-opening-balance/', {
            'material': self.fixture.material.pk, 'quantity': '8.00',
            'unit_cost': '12500.000000', 'reason': 'Opening count.',
        }, format='json'), 201)
        self.assertEqual(movement.data['total_cost'], '100000.00')
        valuation = self.assert_status(self.client.get(
            f'/api/inventory-valuations/?material={self.fixture.material.pk}',
        ), 200)
        self.assertEqual(valuation.data['results'][0]['current_value'], '100000.00')

    def test_06_landed_cost_allocation(self):
        _, po_id, _ = self.approved_purchase_order()
        self.receive(po_id)
        grn = GoodsReceivedNote.objects.get(purchase_order_id=po_id)
        before = valuation_services.valuation_state(
            company=self.fixture.company, material=self.fixture.material,
            warehouse=valuation_services.get_default_warehouse(self.fixture.company),
        )['value']
        self.authenticate(self.fixture.finance_officer)
        document = self.assert_status(self.client.post('/api/v1/finance/landed-costs/', {
            'number': 'RELEASE-LC-1', 'description': 'Transport to warehouse',
            'allocation_method': 'QUANTITY', 'currency': self.currency.pk,
            'exchange_rate': '1.000000', 'goods_received_notes': [grn.pk],
            'items': [{'cost_type': 'TRANSPORT', 'amount': '50000.00'}],
        }, format='json'), 201)
        document_id = document.data['id']
        self.assert_status(self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/preview/', {'inputs': []}, format='json',
        ), 200)
        self.assert_status(self.client.post(f'/api/v1/finance/landed-costs/{document_id}/submit/'), 200)
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(f'/api/v1/finance/landed-costs/{document_id}/approve/'), 200)
        self.assert_status(self.client.post(
            f'/api/v1/finance/landed-costs/{document_id}/post/',
            {'idempotency_key': 'release-landed-post'}, format='json',
        ), 200)
        after = valuation_services.valuation_state(
            company=self.fixture.company, material=self.fixture.material,
            warehouse=valuation_services.get_default_warehouse(self.fixture.company),
        )['value']
        self.assertEqual(after - before, Decimal('50000.00'))

    def test_07_supplier_return_and_credit_note(self):
        _, po_id, po_item_id = self.approved_purchase_order()
        self.receive(po_id)
        invoice_id, _ = self.posted_invoice(po_id, po_item_id)
        receipt = StockMovement.objects.get(purchase_order_id=po_id, transaction_type='RECEIPT')
        self.authenticate(self.storekeeper)
        self.assert_status(self.client.post('/api/stock-movements/return-stock-to-supplier/', {
            'material': self.fixture.material.pk, 'quantity': '1.00',
            'original_receipt': receipt.pk, 'reason': 'Damaged stock returned.',
        }, format='json'), 201)
        invoice_item = SupplierInvoice.objects.get(pk=invoice_id).items.get()
        self.authenticate(self.fixture.finance_manager)
        credit = self.assert_status(self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/create-credit-note/', {
                'credit_note_number': 'RELEASE-CN-1',
                'credit_note_date': str(timezone.localdate()),
                'reason': 'Supplier accepted damaged return.',
                'idempotency_key': 'release-credit-note',
                'items': [{'invoice_item': invoice_item.pk, 'quantity': '1.00'}],
            }, format='json',
        ), 201)
        self.assertEqual(credit.data['status'], 'POSTED')
        duplicate_line_credit = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/create-credit-note/', {
                'credit_note_number': 'RELEASE-CN-2',
                'credit_note_date': str(timezone.localdate()),
                'reason': 'Attempted duplicate line credit.',
                'idempotency_key': 'release-credit-note-two',
                'items': [{'invoice_item': invoice_item.pk, 'quantity': '10.00'}],
            }, format='json',
        )
        self.assertEqual(duplicate_line_credit.status_code, 400)
        self.assertIn('items', duplicate_line_credit.data)

    def test_08_payment_reversal_restores_invoice_balance(self):
        _, po_id, po_item_id = self.approved_purchase_order()
        self.receive(po_id)
        invoice_id, _ = self.posted_invoice(po_id, po_item_id)
        payment_id = self.posted_payment(invoice_id, '100000.00', key='reversal-payment')
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(f'/api/v1/finance/payments/{payment_id}/reverse/', {
            'reason': 'Incorrect bank account.', 'idempotency_key': 'release-payment-reversal',
        }, format='json'), 201)
        self.assertEqual(SupplierInvoice.objects.get(pk=invoice_id).balance, Decimal('350000.00'))

    def test_09_budget_exhaustion_and_authorized_override(self):
        _, line_id = self.approved_budget('100000.00')
        self.authenticate(self.fixture.engineer)
        pr = self.assert_status(self.client.post('/api/purchase-requests/', {
            'project': self.fixture.project.pk, 'title': 'Over budget request',
            'items': [{'material': self.fixture.material.pk, 'quantity': '10.00'}],
        }, format='json'), 201)
        self.authenticate(self.fixture.manager)
        self.client.post(f"/api/purchase-requests/{pr.data['id']}/approve/")
        self.client.post(f"/api/purchase-requests/{pr.data['id']}/submit-finance/", {
            'budget_line': line_id,
        }, format='json')
        self.authenticate(self.fixture.finance_manager)
        blocked = self.client.post(f"/api/purchase-requests/{pr.data['id']}/finance-approve/", {}, format='json')
        self.assertEqual(blocked.status_code, 400)
        self.authenticate(self.fixture.admin)
        overridden = self.assert_status(self.client.post(
            f"/api/purchase-requests/{pr.data['id']}/finance-approve/",
            {'override': True, 'comments': 'Emergency administrator-approved spend.'}, format='json',
        ), 200)
        self.assertEqual(overridden.data['status'], 'OVERRIDDEN')

    def test_10_two_payment_approvals_cannot_overpay(self):
        _, po_id, po_item_id = self.approved_purchase_order()
        self.receive(po_id)
        invoice_id, _ = self.posted_invoice(po_id, po_item_id)
        payment_ids = []
        self.authenticate(self.fixture.finance_officer)
        for index in range(2):
            payment = self.assert_status(self.client.post('/api/v1/finance/payments/', {
                'supplier': self.fixture.supplier.pk, 'source_account': self.cash.pk,
                'currency': self.currency.pk, 'amount': '250000.00',
                'payment_date': str(timezone.localdate()), 'method': Payment.METHOD_BANK,
                'reference': f'RACE-{index}', 'idempotency_key': f'race-payment-{index}',
            }, format='json'), 201)
            payment_ids.append(payment.data['id'])
            self.client.post(f"/api/v1/finance/payments/{payment.data['id']}/allocate/", {
                'invoice': invoice_id, 'amount': '250000.00',
            }, format='json')
            self.client.post(f"/api/v1/finance/payments/{payment.data['id']}/submit/")
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(f'/api/v1/finance/payments/{payment_ids[0]}/approve/'), 200)
        self.authenticate(self.second_finance_manager)
        self.assertEqual(
            self.client.post(f'/api/v1/finance/payments/{payment_ids[1]}/approve/').status_code,
            400,
        )

    def test_11_cross_company_object_access_is_hidden(self):
        budget_id, _ = self.approved_budget()
        self.authenticate(self.other.finance_manager)
        self.assertEqual(self.client.get(f'/api/v1/finance/budgets/{budget_id}/').status_code, 404)
        self.assertEqual(self.client.post(
            f'/api/v1/finance/budgets/{budget_id}/approve/', {}, format='json',
        ).status_code, 404)

    def test_12_offline_retry_with_same_idempotency_key(self):
        client_uuid = uuid4()
        payload = {
            'record_type': 'payment', 'client_uuid': str(client_uuid),
            'idempotency_key': 'release-offline-retry',
            'data': {
                'supplier': self.fixture.supplier.pk, 'source_account': self.cash.pk,
                'currency': self.currency.pk, 'amount': '1000.00',
                'payment_date': str(timezone.localdate()), 'method': Payment.METHOD_CASH,
                'reference': 'OFFLINE-RETRY',
            },
        }
        self.authenticate(self.fixture.finance_officer)
        first = self.assert_status(self.client.post(
            '/api/v1/finance/sync/drafts/', payload, format='json',
        ), 201)
        second = self.assert_status(self.client.post(
            '/api/v1/finance/sync/drafts/', payload, format='json',
        ), 200)
        self.assertTrue(second.data['replayed'])
        self.assertEqual(first.data['data']['id'], second.data['data']['id'])

    def test_13_closed_period_blocks_posting(self):
        self.authenticate(self.fixture.finance_officer)
        expense = Account.objects.create(
            company=self.fixture.company, code='6999', name='Release expense',
            account_type=Account.TYPE_EXPENSE,
        )
        journal = self.assert_status(self.client.post('/api/v1/finance/journals/', {
            'date': str(timezone.localdate()), 'description': 'Closed-period release test',
            'lines': [
                {'account': expense.pk, 'debit': '100.00', 'credit': '0.00'},
                {'account': self.cash.pk, 'debit': '0.00', 'credit': '100.00'},
            ],
        }, format='json'), 201)
        period = FiscalPeriod.objects.get(pk=journal.data['fiscal_period'])
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(
            f'/api/v1/finance/fiscal-periods/{period.pk}/close/', {}, format='json',
        ), 200)
        blocked = self.client.post(f"/api/v1/finance/journals/{journal.data['id']}/post/")
        self.assertEqual(blocked.status_code, 400)

    def test_14_general_ledger_balance_and_reversal(self):
        self.authenticate(self.fixture.finance_officer)
        expense = Account.objects.create(
            company=self.fixture.company, code='6988', name='Reversible release expense',
            account_type=Account.TYPE_EXPENSE,
        )
        journal = self.assert_status(self.client.post('/api/v1/finance/journals/', {
            'date': str(timezone.localdate()), 'description': 'Balanced release journal',
            'lines': [
                {'account': expense.pk, 'debit': '250.00', 'credit': '0.00'},
                {'account': self.cash.pk, 'debit': '0.00', 'credit': '250.00'},
            ],
        }, format='json'), 201)
        self.authenticate(self.fixture.finance_manager)
        self.assert_status(self.client.post(
            f"/api/v1/finance/journals/{journal.data['id']}/post/",
        ), 200)
        reversal = self.assert_status(self.client.post(
            f"/api/v1/finance/journals/{journal.data['id']}/reverse/", {
                'reason': 'Release reversal test.', 'idempotency_key': 'release-journal-reversal',
            }, format='json',
        ), 201)
        record = JournalReversal.objects.get(pk=reversal.data['id'])
        self.assertEqual(
            record.reversal_journal.lines.aggregate(total=Sum('debit'))['total'],
            record.reversal_journal.lines.aggregate(total=Sum('credit'))['total'],
        )

    def test_foreign_currency_matching_budget_and_fx_posting(self):
        _, po_id, po_item_id = self.approved_purchase_order()
        self.receive(po_id)
        usd = Currency.objects.create(
            company=self.fixture.company, code='USD', name='US Dollar', symbol='$',
        )
        invoice_id, match = self.posted_invoice(
            po_id, po_item_id, unit_price='10.00', number='USD-INVOICE',
            currency='USD', exchange_rate='3500.000000',
        )
        self.assertEqual(match.data['status'], 'MATCHED')
        payment_id = self.posted_payment(
            invoice_id, '100.00', key='usd-payment', exchange_rate='3600.000000', currency=usd,
        )
        invoice_journal = JournalEntry.objects.get(
            source_type=JournalEntry.SOURCE_INVOICE, source_object_id=invoice_id,
        )
        payment_journal = JournalEntry.objects.get(
            source_type=JournalEntry.SOURCE_PAYMENT, source_object_id=payment_id,
        )
        self.assertEqual(invoice_journal.lines.aggregate(total=Sum('debit'))['total'], Decimal('350000.00'))
        self.assertEqual(payment_journal.lines.aggregate(total=Sum('debit'))['total'], Decimal('360000.00'))
        self.assertTrue(payment_journal.lines.filter(account__system_key=Account.SYSTEM_REALIZED_FX).exists())
