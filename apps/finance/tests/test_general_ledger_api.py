from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.procurement.models import PurchaseOrder, PurchaseOrderItem
from apps.procurement.services import record_goods_received_note

from ..factories import FinanceFixtureFactory
from ..ledger_services import (
    create_and_post_source_journal,
    ensure_ledger_configuration,
    post_rule_event,
)
from ..models import (
    Account,
    AccountMapping,
    FiscalPeriod,
    JournalEntry,
    JournalLine,
    JournalReversal,
    PostingRule,
)


class GeneralLedgerApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('GL')
        self.other = FinanceFixtureFactory('GL-OTHER')
        ensure_ledger_configuration(self.fixture.company)
        ensure_ledger_configuration(self.other.company)
        self.cash = AccountMapping.objects.get(
            company=self.fixture.company, mapping_key='CASH',
        ).account
        self.expense = Account.objects.create(
            company=self.fixture.company,
            code='6000',
            name='Manual project expense',
            account_type=Account.TYPE_EXPENSE,
        )
        self.client = APIClient()

    def journal_payload(self, debit='250.00', credit='250.00'):
        return {
            'date': timezone.localdate(),
            'description': 'Manual accrual adjustment',
            'source_reference': 'MANUAL-001',
            'lines': [
                {
                    'account': self.expense.pk,
                    'project': self.fixture.project.pk,
                    'description': 'Expense debit',
                    'debit': debit,
                    'credit': '0.00',
                },
                {
                    'account': self.cash.pk,
                    'description': 'Cash credit',
                    'debit': '0.00',
                    'credit': credit,
                },
            ],
        }

    def create_draft(self, *, actor=None, debit='250.00', credit='250.00'):
        self.client.force_authenticate(actor or self.fixture.finance_officer)
        response = self.client.post(
            '/api/v1/finance/journals/',
            self.journal_payload(debit=debit, credit=credit),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], JournalEntry.STATUS_DRAFT)
        return response.data['id']

    def post_draft(self, journal_id, *, actor=None):
        self.client.force_authenticate(actor or self.fixture.finance_manager)
        return self.client.post(
            f'/api/v1/finance/journals/{journal_id}/post/', {}, format='json',
        )

    def test_balanced_draft_can_be_edited_and_posted_but_posted_data_is_immutable(self):
        journal_id = self.create_draft()
        self.client.force_authenticate(self.fixture.finance_officer)
        edited = self.client.patch(
            f'/api/v1/finance/journals/{journal_id}/',
            {'description': 'Edited while draft'},
            format='json',
        )
        self.assertEqual(edited.status_code, 200, edited.data)
        posted = self.post_draft(journal_id)
        self.assertEqual(posted.status_code, 200, posted.data)
        self.assertEqual(posted.data['status'], JournalEntry.STATUS_POSTED)
        self.assertEqual(posted.data['debit_total'], Decimal('250.00'))
        self.assertEqual(posted.data['credit_total'], Decimal('250.00'))
        journal = JournalEntry.objects.get(pk=journal_id)
        self.assertIsNotNone(journal.fiscal_period_id)

        self.client.force_authenticate(self.fixture.finance_officer)
        self.assertEqual(self.client.patch(
            f'/api/v1/finance/journals/{journal_id}/',
            {'description': 'Forbidden mutation'}, format='json',
        ).status_code, 400)
        line = journal.lines.first()
        line.description = 'Forbidden mutation'
        with self.assertRaises(DjangoValidationError):
            line.save()

    def test_unbalanced_journal_cannot_be_posted(self):
        journal_id = self.create_draft(debit='250.00', credit='200.00')
        response = self.post_draft(journal_id)
        self.assertEqual(response.status_code, 400)
        self.assertIn('lines', response.data)
        self.assertEqual(JournalEntry.objects.get(pk=journal_id).status, JournalEntry.STATUS_DRAFT)

    def test_source_posting_is_idempotent_and_rejects_changed_replays(self):
        first = post_rule_event(
            company=self.fixture.company,
            user=self.fixture.admin,
            event_type=PostingRule.EVENT_INVENTORY_ADJUSTMENT,
            entry_date=timezone.localdate(),
            source_type=JournalEntry.SOURCE_STOCK_MOVEMENT,
            source_object_id=9001,
            amount=Decimal('100.00'),
            description='Inventory adjustment 9001',
        )
        repeated = post_rule_event(
            company=self.fixture.company,
            user=self.fixture.admin,
            event_type=PostingRule.EVENT_INVENTORY_ADJUSTMENT,
            entry_date=timezone.localdate(),
            source_type=JournalEntry.SOURCE_STOCK_MOVEMENT,
            source_object_id=9001,
            amount=Decimal('100.00'),
            description='Inventory adjustment 9001',
        )
        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(JournalEntry.objects.filter(
            company=self.fixture.company,
            source_type=JournalEntry.SOURCE_STOCK_MOVEMENT,
            source_object_id=9001,
        ).count(), 1)
        with self.assertRaises(ValidationError):
            post_rule_event(
                company=self.fixture.company,
                user=self.fixture.admin,
                event_type=PostingRule.EVENT_INVENTORY_ADJUSTMENT,
                entry_date=timezone.localdate(),
                source_type=JournalEntry.SOURCE_STOCK_MOVEMENT,
                source_object_id=9001,
                amount=Decimal('101.00'),
                description='Changed replay',
            )

    def test_closed_period_blocks_posting_and_can_be_reopened(self):
        journal_id = self.create_draft()
        self.assertEqual(self.post_draft(journal_id).status_code, 200)
        journal_id = self.create_draft()
        period = FiscalPeriod.objects.get(
            company=self.fixture.company,
            start_date__lte=timezone.localdate(),
            end_date__gte=timezone.localdate(),
        )
        self.client.force_authenticate(self.fixture.finance_manager)
        closed = self.client.post(
            f'/api/v1/finance/fiscal-periods/{period.pk}/close/', {}, format='json',
        )
        self.assertEqual(closed.status_code, 200, closed.data)
        blocked = self.post_draft(journal_id)
        self.assertEqual(blocked.status_code, 400)
        self.assertIn('date', blocked.data)
        reopened = self.client.post(
            f'/api/v1/finance/fiscal-periods/{period.pk}/open/', {}, format='json',
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(self.post_draft(journal_id).status_code, 200)

    def test_posted_journal_reversal_is_linked_balanced_and_idempotent(self):
        journal_id = self.create_draft()
        self.assertEqual(self.post_draft(journal_id).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        response = self.client.post(
            f'/api/v1/finance/journals/{journal_id}/reverse/', {
                'reason': 'The manual accrual was entered in error.',
                'idempotency_key': 'reverse-manual-1',
            }, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        record = JournalReversal.objects.get(pk=response.data['id'])
        self.assertEqual(record.original_journal_id, journal_id)
        self.assertEqual(record.reversal_journal.reversal_of_id, journal_id)
        self.assertEqual(record.original_journal.status, JournalEntry.STATUS_REVERSED)
        self.assertEqual(
            record.reversal_journal.lines.aggregate(total=Sum('debit'))['total'],
            record.reversal_journal.lines.aggregate(total=Sum('credit'))['total'],
        )
        duplicate = self.client.post(
            f'/api/v1/finance/journals/{journal_id}/reverse/', {
                'reason': 'The manual accrual was entered in error.',
                'idempotency_key': 'reverse-manual-1',
            }, format='json',
        )
        self.assertEqual(duplicate.status_code, 201)
        self.assertEqual(JournalReversal.objects.filter(original_journal_id=journal_id).count(), 1)

    def test_account_mappings_drive_postings_and_rules_are_bootstrapped(self):
        self.assertEqual(
            PostingRule.objects.filter(company=self.fixture.company).count(),
            len(PostingRule.EVENT_CHOICES),
        )
        alternate_inventory = Account.objects.create(
            company=self.fixture.company,
            code='1210',
            name='Alternate inventory control',
            account_type=Account.TYPE_ASSET,
        )
        mapping = AccountMapping.objects.get(
            company=self.fixture.company, mapping_key='INVENTORY',
        )
        self.client.force_authenticate(self.fixture.finance_manager)
        response = self.client.patch(
            f'/api/v1/finance/account-mappings/{mapping.pk}/',
            {'account': alternate_inventory.pk}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        journal = post_rule_event(
            company=self.fixture.company,
            user=self.fixture.admin,
            event_type=PostingRule.EVENT_GRN_RECEIPT,
            entry_date=timezone.localdate(),
            source_type=JournalEntry.SOURCE_GRN,
            source_object_id=8123,
            amount=Decimal('500.00'),
            description='Mapped GRN test',
        )
        self.assertEqual(journal.lines.get(debit__gt=0).account_id, alternate_inventory.pk)

    def test_account_ledger_trial_balance_permissions_and_company_isolation(self):
        journal_id = self.create_draft()
        self.client.force_authenticate(self.fixture.finance_officer)
        self.assertEqual(self.client.post(
            f'/api/v1/finance/journals/{journal_id}/post/', {}, format='json',
        ).status_code, 403)
        self.assertEqual(self.post_draft(journal_id).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_viewer)
        ledger = self.client.get(
            f'/api/v1/finance/chart-of-accounts/{self.expense.pk}/ledger/',
        )
        self.assertEqual(ledger.status_code, 200, ledger.data)
        self.assertEqual(ledger.data['count'], 1)
        trial = self.client.get('/api/v1/finance/journals/trial-balance/')
        self.assertEqual(trial.status_code, 200, trial.data)
        self.assertTrue(trial.data['is_balanced'])

        self.client.force_authenticate(self.other.finance_viewer)
        listing = self.client.get('/api/v1/finance/journals/')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['count'], 0)
        self.assertEqual(self.client.get(
            f'/api/v1/finance/journals/{journal_id}/',
        ).status_code, 404)
        self.client.force_authenticate(self.fixture.finance_manager)
        own_mapping = AccountMapping.objects.get(
            company=self.fixture.company, mapping_key='CASH',
        )
        self.assertEqual(self.client.patch(
            f'/api/v1/finance/account-mappings/{own_mapping.pk}/',
            {'account': Account.objects.filter(company=self.other.company).first().pk},
            format='json',
        ).status_code, 400)

    def test_procurement_grn_posts_one_balanced_source_journal(self):
        storekeeper = User.objects.create_user(
            username='gl-storekeeper', password='password', company=self.fixture.company,
            role=User.ROLE_STOREKEEPER,
        )
        po = PurchaseOrder.objects.create(
            company=self.fixture.company,
            project=self.fixture.project,
            number='PO-GL-GRN',
            supplier=self.fixture.supplier,
            status=PurchaseOrder.STATUS_ORDERED,
            delivery_destination=PurchaseOrder.DELIVERY_WAREHOUSE,
        )
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=po,
            material=self.fixture.material,
            quantity=Decimal('2.00'),
            unit_price=Decimal('125.00'),
        )
        _, grn = record_goods_received_note(
            purchase_order=po,
            user=storekeeper,
            receipt_date=timezone.localdate(),
            items=[{
                'purchase_order_item': po_item,
                'accepted_quantity': Decimal('2.00'),
                'rejected_quantity': Decimal('0.00'),
                'damaged_quantity': Decimal('0.00'),
            }],
        )
        journal = JournalEntry.objects.get(
            company=self.fixture.company,
            source_type=JournalEntry.SOURCE_GRN,
            source_object_id=grn.pk,
        )
        self.assertEqual(journal.status, JournalEntry.STATUS_POSTED)
        self.assertEqual(journal.lines.aggregate(total=Sum('debit'))['total'], Decimal('250.00'))
        self.assertEqual(journal.lines.aggregate(total=Sum('credit'))['total'], Decimal('250.00'))
