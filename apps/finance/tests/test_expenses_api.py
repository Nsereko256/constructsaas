from decimal import Decimal
from threading import Barrier, Thread

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from ..configuration_services import ensure_finance_settings
from ..factories import FinanceFixtureFactory
from ..models import (
    Account,
    BudgetCategory,
    BudgetLine,
    BudgetTransaction,
    CashAccount,
    ExpenseCategory,
    ExpenseClaim,
    FinanceSettings,
    PettyCashTransaction,
    ProjectBudget,
    StaffAdvance,
)
from ..services import ensure_system_accounts


class ExpenseFinanceApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('EXP')
        self.other = FinanceFixtureFactory('EXP-OTHER')
        self.settings = ensure_finance_settings(self.fixture.company)
        self.currency = self.settings.base_currency
        accounts = ensure_system_accounts(self.fixture.company)
        self.source_account = accounts[Account.SYSTEM_CASH]
        self.cash_ledger = Account.objects.create(
            company=self.fixture.company, code='1010', name='Site Petty Cash',
            account_type=Account.TYPE_ASSET,
        )
        self.expense_ledger = Account.objects.create(
            company=self.fixture.company, code='6100', name='Site Transport',
            account_type=Account.TYPE_EXPENSE,
        )
        self.budget_category = BudgetCategory.objects.create(
            company=self.fixture.company, code='TRAVEL', name='Travel',
        )
        self.expense_category = ExpenseCategory.objects.create(
            company=self.fixture.company, code='TRANSPORT', name='Site transport',
            category_type=ExpenseCategory.TYPE_TRANSPORT,
            expense_account=self.expense_ledger,
            budget_category=self.budget_category,
        )
        self.cash = CashAccount.objects.create(
            company=self.fixture.company, code='PETTY', name='Main Petty Cash',
            account=self.cash_ledger, currency=self.currency,
            opening_balance=Decimal('1000.00'),
        )
        self.budget = ProjectBudget.objects.create(
            company=self.fixture.company, project=self.fixture.project,
            name='Operating budget', created_by=self.fixture.finance_officer,
        )
        self.budget_line = BudgetLine.objects.create(
            company=self.fixture.company, budget=self.budget,
            category=self.budget_category, original_amount=Decimal('5000.00'),
        )
        ProjectBudget.objects.filter(pk=self.budget.pk).update(
            status=ProjectBudget.STATUS_APPROVED,
            approved_by=self.fixture.finance_manager,
            approved_at=timezone.now(),
        )
        self.client = APIClient()
        self.counter = 0

    def claim_payload(self, amount='300.00', key=None, project=None):
        self.counter += 1
        return {
            'claimant': self.fixture.engineer.pk,
            'project': (project or self.fixture.project).pk,
            'purpose': 'Transport materials to site',
            'claim_date': timezone.localdate(),
            'currency': self.currency.pk,
            'exchange_rate': '1.000000',
            'idempotency_key': key or f'claim-{self.counter}',
            'total_amount': '1.00',
            'items': [{
                'category': self.expense_category.pk,
                'expense_date': timezone.localdate(),
                'description': 'Truck hire',
                'amount': amount,
            }],
        }

    def create_claim(self, amount='300.00', key=None, actor=None):
        self.client.force_authenticate(actor or self.fixture.finance_officer)
        response = self.client.post(
            '/api/v1/finance/expense-claims/',
            self.claim_payload(amount=amount, key=key),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['total_amount'], amount)
        return response.data['id']

    def submit_approve_claim(self, claim_id):
        self.client.force_authenticate(self.fixture.finance_officer)
        submitted = self.client.post(
            f'/api/v1/finance/expense-claims/{claim_id}/submit/', {}, format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.client.force_authenticate(self.fixture.finance_manager)
        approved = self.client.post(
            f'/api/v1/finance/expense-claims/{claim_id}/approve/', {}, format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        return approved

    def pay_claim(self, claim_id, key='pay-claim', reference='PV-001'):
        self.client.force_authenticate(self.fixture.finance_manager)
        return self.client.post(
            f'/api/v1/finance/expense-claims/{claim_id}/pay/', {
                'cash_account': self.cash.pk,
                'payment_reference': reference,
                'idempotency_key': key,
            }, format='json',
        )

    def advance_payload(self, amount='500.00', key='advance-1'):
        return {
            'staff': self.fixture.engineer.pk,
            'project': self.fixture.project.pk,
            'purpose': 'Site running costs',
            'advance_date': timezone.localdate(),
            'currency': self.currency.pk,
            'exchange_rate': '1.000000',
            'amount': amount,
            'idempotency_key': key,
        }

    def create_submit_approve_advance(self, amount='500.00', key='advance-1'):
        self.client.force_authenticate(self.fixture.finance_officer)
        created = self.client.post(
            '/api/v1/finance/staff-advances/', self.advance_payload(amount, key), format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        advance_id = created.data['id']
        self.assertEqual(self.client.post(
            f'/api/v1/finance/staff-advances/{advance_id}/submit/', {}, format='json',
        ).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        approved = self.client.post(
            f'/api/v1/finance/staff-advances/{advance_id}/approve/', {}, format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        return advance_id

    def test_expense_totals_are_server_calculated_and_actual_posts_only_on_payment(self):
        claim_id = self.create_claim()
        self.submit_approve_claim(claim_id)
        self.assertFalse(BudgetTransaction.objects.filter(expense_claim_id=claim_id).exists())

        paid = self.pay_claim(claim_id)
        self.assertEqual(paid.status_code, 200, paid.data)
        self.assertEqual(paid.data['status'], ExpenseClaim.STATUS_PAID)
        self.assertEqual(
            BudgetTransaction.objects.get(expense_claim_id=claim_id).amount,
            Decimal('300.00'),
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.current_balance, Decimal('700.00'))
        duplicate = self.pay_claim(claim_id)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(PettyCashTransaction.objects.filter(expense_claim_id=claim_id).count(), 1)

        self.client.force_authenticate(self.fixture.finance_officer)
        immutable = self.client.patch(
            f'/api/v1/finance/expense-claims/{claim_id}/', {'purpose': 'Changed'}, format='json',
        )
        self.assertEqual(immutable.status_code, 400)

    def test_maker_checker_threshold_rejection_and_permissions(self):
        claim_id = self.create_claim()
        self.client.force_authenticate(self.fixture.finance_viewer)
        self.assertEqual(self.client.get('/api/v1/finance/expense-claims/').status_code, 200)
        self.assertEqual(self.client.post(
            '/api/v1/finance/expense-claims/', self.claim_payload(), format='json',
        ).status_code, 403)

        self.client.force_authenticate(self.fixture.finance_officer)
        self.client.post(f'/api/v1/finance/expense-claims/{claim_id}/submit/', {}, format='json')
        self.assertEqual(self.client.post(
            f'/api/v1/finance/expense-claims/{claim_id}/approve/', {}, format='json',
        ).status_code, 403)
        self.client.force_authenticate(self.fixture.finance_manager)
        missing_reason = self.client.post(
            f'/api/v1/finance/expense-claims/{claim_id}/reject/', {'reason': ''}, format='json',
        )
        self.assertEqual(missing_reason.status_code, 400)

        FinanceSettings.objects.filter(pk=self.settings.pk).update(
            finance_manager_approval_threshold=Decimal('100.00'),
        )
        threshold = self.client.post(
            f'/api/v1/finance/expense-claims/{claim_id}/approve/', {}, format='json',
        )
        self.assertEqual(threshold.status_code, 400)
        self.client.force_authenticate(self.fixture.admin)
        approved = self.client.post(
            f'/api/v1/finance/expense-claims/{claim_id}/approve/', {}, format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)

        own_claim = self.create_claim(actor=self.fixture.admin)
        self.client.force_authenticate(self.fixture.admin)
        self.client.post(f'/api/v1/finance/expense-claims/{own_claim}/submit/', {}, format='json')
        self.assertEqual(self.client.post(
            f'/api/v1/finance/expense-claims/{own_claim}/approve/', {}, format='json',
        ).status_code, 400)

    def test_duplicate_reimbursement_is_prevented_and_reversal_restores_balances(self):
        first = self.create_claim(amount='200.00')
        self.submit_approve_claim(first)
        self.assertEqual(self.pay_claim(first, key='pay-first', reference='DUP-REF').status_code, 200)
        second = self.create_claim(amount='100.00')
        self.submit_approve_claim(second)
        duplicate_reference = self.pay_claim(second, key='pay-second', reference='DUP-REF')
        self.assertEqual(duplicate_reference.status_code, 400)

        self.client.force_authenticate(self.fixture.finance_manager)
        reversed_response = self.client.post(
            f'/api/v1/finance/expense-claims/{first}/reverse/', {
                'reason': 'Duplicate receipt was identified.',
                'idempotency_key': 'reverse-first',
            }, format='json',
        )
        self.assertEqual(reversed_response.status_code, 201, reversed_response.data)
        self.assertEqual(CashAccount.objects.get(pk=self.cash.pk).current_balance, Decimal('1000.00'))
        self.assertEqual(
            sum(BudgetTransaction.objects.filter(expense_claim_id=first).values_list('amount', flat=True)),
            Decimal('0.00'),
        )

    def test_staff_advance_retirement_tracks_outstanding_and_expenditure(self):
        advance_id = self.create_submit_approve_advance()
        self.client.force_authenticate(self.fixture.finance_manager)
        paid = self.client.post(
            f'/api/v1/finance/staff-advances/{advance_id}/pay/', {
                'cash_account': self.cash.pk,
                'payment_reference': 'ADV-PV-1',
                'idempotency_key': 'pay-advance-1',
            }, format='json',
        )
        self.assertEqual(paid.status_code, 200, paid.data)
        self.assertEqual(paid.data['outstanding_amount'], '500.00')
        self.assertFalse(BudgetTransaction.objects.filter(advance_retirement__advance_id=advance_id).exists())

        retirement = self.client.post(
            f'/api/v1/finance/staff-advances/{advance_id}/retire/', {
                'expense_category': self.expense_category.pk,
                'amount_spent': '300.00',
                'amount_refunded': '100.00',
                'reason': 'Retire supported site costs.',
                'idempotency_key': 'retire-advance-1',
            }, format='json',
        )
        self.assertEqual(retirement.status_code, 201, retirement.data)
        advance = StaffAdvance.objects.get(pk=advance_id)
        self.assertEqual(advance.outstanding_amount, Decimal('100.00'))
        self.assertEqual(CashAccount.objects.get(pk=self.cash.pk).current_balance, Decimal('600.00'))
        self.assertEqual(
            BudgetTransaction.objects.get(advance_retirement_id=retirement.data['id']).amount,
            Decimal('300.00'),
        )
        excessive = self.client.post(
            f'/api/v1/finance/staff-advances/{advance_id}/retire/', {
                'expense_category': self.expense_category.pk,
                'amount_spent': '101.00', 'amount_refunded': '0.00',
                'reason': 'Too much.', 'idempotency_key': 'retire-too-much',
            }, format='json',
        )
        self.assertEqual(excessive.status_code, 400)
        outstanding = self.client.get('/api/v1/finance/staff-advances/outstanding/')
        self.assertEqual(outstanding.status_code, 200)
        self.assertEqual(outstanding.data[0]['id'], advance_id)
        reversal = self.client.post(
            f"/api/v1/finance/advance-retirements/{retirement.data['id']}/reverse/", {
                'reason': 'Retirement receipts were invalid.',
                'idempotency_key': 'reverse-retirement-1',
            }, format='json',
        )
        self.assertEqual(reversal.status_code, 201, reversal.data)
        advance.refresh_from_db()
        self.assertEqual(advance.outstanding_amount, Decimal('500.00'))
        self.assertEqual(CashAccount.objects.get(pk=self.cash.pk).current_balance, Decimal('500.00'))
        self.assertEqual(
            sum(BudgetTransaction.objects.filter(
                advance_retirement__advance_id=advance_id,
            ).values_list('amount', flat=True)),
            Decimal('0.00'),
        )

    def test_petty_cash_replenishment_balance_voucher_and_reversal(self):
        self.client.force_authenticate(self.fixture.finance_manager)
        replenished = self.client.post(
            f'/api/v1/finance/cash-accounts/{self.cash.pk}/replenish/', {
                'source_account': self.source_account.pk,
                'amount': '500.00', 'exchange_rate': '1.000000',
                'reference': 'BANK-TRANSFER-1', 'reason': 'Weekly replenishment.',
                'idempotency_key': 'replenish-1',
            }, format='json',
        )
        self.assertEqual(replenished.status_code, 201, replenished.data)
        balances = self.client.get('/api/v1/finance/cash-accounts/balances/')
        self.assertEqual(balances.status_code, 200)
        self.assertEqual(balances.data[0]['current_balance'], '1500.00')
        reversed_response = self.client.post(
            f"/api/v1/finance/petty-cash-transactions/{replenished.data['id']}/reverse/", {
                'reason': 'Transfer was recalled.', 'idempotency_key': 'reverse-replenish-1',
            }, format='json',
        )
        self.assertEqual(reversed_response.status_code, 201, reversed_response.data)
        self.assertEqual(CashAccount.objects.get(pk=self.cash.pk).current_balance, Decimal('1000.00'))
        protected = self.client.patch(
            f'/api/v1/finance/cash-accounts/{self.cash.pk}/',
            {'opening_balance': '9999.00'}, format='json',
        )
        self.assertEqual(protected.status_code, 400)

    def test_receipts_vouchers_summaries_and_company_isolation(self):
        claim_id = self.create_claim()
        self.client.force_authenticate(self.fixture.finance_officer)
        receipt = self.client.post('/api/v1/finance/expense-receipts/', {
            'claim': claim_id,
            'file': SimpleUploadedFile('receipt.pdf', b'receipt', content_type='application/pdf'),
        }, format='multipart')
        self.assertEqual(receipt.status_code, 201, receipt.data)
        self.assertNotIn('file', receipt.data)
        self.submit_approve_claim(claim_id)
        self.assertEqual(self.pay_claim(claim_id, key='pay-summary').status_code, 200)
        self.client.force_authenticate(self.fixture.finance_viewer)
        self.assertEqual(
            self.client.get(f'/api/v1/finance/expense-claims/{claim_id}/voucher/').status_code, 200,
        )
        summary = self.client.get('/api/v1/finance/expense-claims/summary/')
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data['total_expenditure'], Decimal('300.00'))

        self.client.force_authenticate(self.other.finance_viewer)
        listing = self.client.get('/api/v1/finance/expense-claims/')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['count'], 0)
        self.assertEqual(
            self.client.get(f'/api/v1/finance/expense-claims/{claim_id}/').status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/finance/expense-receipts/{receipt.data['id']}/download/").status_code,
            404,
        )

        self.client.force_authenticate(self.fixture.finance_officer)
        foreign_project = self.client.post(
            '/api/v1/finance/expense-claims/',
            self.claim_payload(project=self.other.project), format='json',
        )
        self.assertEqual(foreign_project.status_code, 400)

    def test_posted_models_are_immutable(self):
        claim_id = self.create_claim(amount='100.00')
        self.submit_approve_claim(claim_id)
        self.pay_claim(claim_id, key='pay-immutable')
        claim = ExpenseClaim.objects.get(pk=claim_id)
        claim.purpose = 'Mutated'
        with self.assertRaises(DjangoValidationError):
            claim.save()
        transaction_record = PettyCashTransaction.objects.get(expense_claim=claim)
        transaction_record.reason = 'Mutated'
        with self.assertRaises(DjangoValidationError):
            transaction_record.save()


@skipUnlessDBFeature('has_select_for_update')
class ConcurrentPettyCashPaymentTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.fixture = FinanceFixtureFactory('EXP-CONCURRENT')
        settings = ensure_finance_settings(self.fixture.company)
        cash_ledger = Account.objects.create(
            company=self.fixture.company, code='1015', name='Concurrent cash',
            account_type=Account.TYPE_ASSET,
        )
        expense_ledger = Account.objects.create(
            company=self.fixture.company, code='6150', name='Concurrent expense',
            account_type=Account.TYPE_EXPENSE,
        )
        self.category = ExpenseCategory.objects.create(
            company=self.fixture.company, code='FUEL', name='Fuel',
            category_type=ExpenseCategory.TYPE_FUEL, expense_account=expense_ledger,
        )
        self.cash = CashAccount.objects.create(
            company=self.fixture.company, code='CONCURRENT', name='Concurrent petty cash',
            account=cash_ledger, currency=settings.base_currency,
            opening_balance=Decimal('1000.00'),
        )
        self.claims = []
        for index in range(2):
            claim = ExpenseClaim.objects.create(
                company=self.fixture.company, number=f'EXP-C-{index}',
                claimant=self.fixture.engineer, project=self.fixture.project,
                purpose='Concurrent claim', currency=settings.base_currency,
                idempotency_key=f'concurrent-claim-{index}', created_by=self.fixture.finance_officer,
            )
            from ..models import ExpenseItem
            ExpenseItem.objects.create(
                company=self.fixture.company, claim=claim, category=self.category,
                description='Fuel', amount=Decimal('700.00'),
            )
            ExpenseClaim.objects.filter(pk=claim.pk).update(
                total_amount=Decimal('700.00'), base_total_amount=Decimal('700.00'),
                status=ExpenseClaim.STATUS_APPROVED,
            )
            self.claims.append(claim.pk)

    def test_concurrent_payments_cannot_overdraw_petty_cash(self):
        from ..expense_services import pay_expense_claim

        barrier = Barrier(2)
        outcomes = []

        def worker(claim_id, suffix):
            close_old_connections()
            try:
                barrier.wait()
                pay_expense_claim(
                    claim=ExpenseClaim.objects.get(pk=claim_id),
                    user=type(self.fixture.finance_manager).objects.get(pk=self.fixture.finance_manager.pk),
                    cash_account=CashAccount.objects.get(pk=self.cash.pk),
                    payment_reference=f'PV-C-{suffix}', idempotency_key=f'pay-c-{suffix}',
                )
                outcomes.append('paid')
            except Exception:
                outcomes.append('blocked')
            finally:
                close_old_connections()

        threads = [Thread(target=worker, args=(claim_id, index)) for index, claim_id in enumerate(self.claims)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(outcomes), ['blocked', 'paid'])
        self.assertEqual(CashAccount.objects.get(pk=self.cash.pk).current_balance, Decimal('300.00'))
