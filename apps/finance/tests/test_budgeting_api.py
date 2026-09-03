from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.procurement.models import PurchaseOrder, PurchaseRequest
from apps.notifications.models import Notification

from ..factories import FinanceFixtureFactory
from ..models import (
    BudgetApproval,
    BudgetCategory,
    BudgetTransaction,
    FinanceAuditEvent,
    FinanceSettings,
    ProjectBudget,
)


class ProjectBudgetingApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('J')
        self.other = FinanceFixtureFactory('K')
        self.category = BudgetCategory.objects.create(
            company=self.fixture.company, code='MAT', name='Materials',
        )
        self.other_category = BudgetCategory.objects.create(
            company=self.fixture.company, code='LAB', name='Labour',
        )
        self.client = APIClient()

    def _approved_budget(self, first='500000.00', second=None):
        lines = [{
            'category': self.category.id,
            'description': 'Construction materials',
            'original_amount': first,
        }]
        if second is not None:
            lines.append({
                'category': self.other_category.id,
                'description': 'Site labour',
                'original_amount': second,
            })
        self.client.force_authenticate(self.fixture.finance_officer)
        created = self.client.post(
            '/api/v1/finance/budgets/',
            {'project': self.fixture.project.id, 'name': 'Approved project budget', 'lines': lines},
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        budget_id = created.data['id']
        self.assertEqual(self.client.post(f'/api/v1/finance/budgets/{budget_id}/submit/').status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        approved = self.client.post(f'/api/v1/finance/budgets/{budget_id}/approve/', {}, format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        lines_by_category = {line['category']: line['id'] for line in approved.data['lines']}
        line_ids = [lines_by_category[self.category.id]]
        if second is not None:
            line_ids.append(lines_by_category[self.other_category.id])
        return ProjectBudget.objects.get(pk=budget_id), line_ids

    def _finance_approved_pr(self, line_id, quantity='10.00', override=False, comments=''):
        purchase_request = self.fixture.purchase_request(quantity=Decimal(quantity))
        self.client.force_authenticate(self.fixture.manager)
        submitted = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_id, 'comments': 'Technical review complete'},
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.client.force_authenticate(self.fixture.finance_manager)
        approved = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-approve/',
            {'override': override, 'comments': comments},
            format='json',
        )
        return purchase_request, approved

    def _purchase_order(self, purchase_request):
        self.client.force_authenticate(self.fixture.procurement)
        created = self.client.post(
            f'/api/purchase-orders/from-pr/{purchase_request.id}/',
            {'supplier': self.fixture.supplier.id},
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        return PurchaseOrder.objects.get(pk=created.data['id'])

    def test_commitment_converts_to_actual_without_double_counting(self):
        budget, line_ids = self._approved_budget()
        purchase_request, finance_approval = self._finance_approved_pr(line_ids[0])
        self.assertEqual(finance_approval.status_code, 200, finance_approval.data)
        po = self._purchase_order(purchase_request)
        self.client.force_authenticate(self.fixture.procurement)
        approved_po = self.client.post(f'/api/purchase-orders/{po.id}/approve/')
        self.assertEqual(approved_po.status_code, 200, approved_po.data)
        dispatched = self.client.post(f'/api/purchase-orders/{po.id}/confirm-dispatch/')
        self.assertEqual(dispatched.status_code, 200, dispatched.data)
        budget.refresh_from_db()
        self.assertEqual(budget.open_commitments, Decimal('350000.00'))
        self.assertEqual(budget.actual_expenditure, Decimal('0.00'))

        self.client.force_authenticate(self.fixture.storekeeper)
        received = self.client.post(f'/api/purchase-orders/{po.id}/receive/')
        self.assertEqual(received.status_code, 200, received.data)
        po.refresh_from_db()
        po_item = po.items.get()
        self.client.force_authenticate(self.fixture.finance_officer)
        invoice = self.client.post(
            '/api/v1/finance/supplier-invoices/',
            {
                'purchase_order': po.id,
                'supplier': self.fixture.supplier.id,
                'invoice_number': 'INV-BUDGET-1',
                'invoice_date': str(timezone.localdate()),
                'items': [{
                    'purchase_order_item': po_item.id,
                    'quantity': str(po_item.quantity),
                    'unit_price': str(po_item.unit_price),
                    'tax_amount': '0.00',
                }],
            },
            format='json',
        )
        self.assertEqual(invoice.status_code, 201, invoice.data)
        invoice_id = invoice.data['id']
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/submit/').status_code, 200)
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/match/', {}).status_code, 201)
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/approve/').status_code, 200)
        posted = self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/post/')
        self.assertEqual(posted.status_code, 201, posted.data)

        budget.refresh_from_db()
        self.assertEqual(budget.open_commitments, Decimal('0.00'))
        self.assertEqual(budget.actual_expenditure, Decimal('350000.00'))
        self.assertEqual(budget.available_balance, Decimal('150000.00'))
        self.assertEqual(BudgetTransaction.objects.filter(budget=budget).count(), 3)

    def test_budget_exhaustion_requires_commented_manager_override(self):
        budget, line_ids = self._approved_budget(first='300000.00')
        purchase_request = self.fixture.purchase_request(quantity=Decimal('10.00'))
        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_ids[0]}, format='json',
        ).status_code, 200)

        self.client.force_authenticate(self.fixture.finance_manager)
        exhausted = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-approve/',
            {'override': False}, format='json',
        )
        self.assertEqual(exhausted.status_code, 400)
        missing_comment = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-approve/',
            {'override': True}, format='json',
        )
        self.assertEqual(missing_comment.status_code, 400)

        self.client.force_authenticate(self.fixture.finance_officer)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-approve/',
            {'override': True, 'comments': 'Urgent exception'}, format='json',
        ).status_code, 403)

        self.client.force_authenticate(self.fixture.finance_manager)
        overridden = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-approve/',
            {'override': True, 'comments': 'Critical structural works'}, format='json',
        )
        self.assertEqual(overridden.status_code, 200, overridden.data)
        self.assertEqual(overridden.data['status'], BudgetApproval.STATUS_OVERRIDDEN)
        self.assertTrue(FinanceAuditEvent.objects.filter(
            company=self.fixture.company, action='purchase_request.finance_overridden',
        ).exists())

    def test_unbudgeted_request_requires_commented_manager_override(self):
        purchase_request = self.fixture.purchase_request(quantity=Decimal('2.00'))
        self.client.force_authenticate(self.fixture.manager)
        submitted = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'comments': 'No approved project budget exists yet.'},
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.assertIsNone(submitted.data['budget_line'])

        self.client.force_authenticate(self.fixture.finance_manager)
        ordinary = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-approve/', {}, format='json',
        )
        self.assertEqual(ordinary.status_code, 400)
        missing_reason = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-approve/',
            {'override': True},
            format='json',
        )
        self.assertEqual(missing_reason.status_code, 400)
        approved = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-approve/',
            {'override': True, 'comments': 'Authorized unbudgeted emergency purchase.'},
            format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data['status'], BudgetApproval.STATUS_OVERRIDDEN)

    def test_approval_threshold_escalates_from_manager_to_admin(self):
        budget, line_ids = self._approved_budget(first='500000.00')
        settings = FinanceSettings.objects.get(company=self.fixture.company)
        settings.finance_manager_approval_threshold = Decimal('100000.00')
        settings.save()
        purchase_request = self.fixture.purchase_request(quantity=Decimal('10.00'))
        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_ids[0]}, format='json',
        ).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        threshold = self.client.post(f'/api/purchase-requests/{purchase_request.id}/finance-approve/', {})
        self.assertEqual(threshold.status_code, 400)
        self.client.force_authenticate(self.fixture.admin)
        self.assertEqual(
            self.client.post(f'/api/purchase-requests/{purchase_request.id}/finance-approve/', {}).status_code,
            200,
        )

    def test_transfer_preserves_total_and_override_controls_line_exhaustion(self):
        budget, line_ids = self._approved_budget(first='100.00', second='50.00')
        self.client.force_authenticate(self.fixture.finance_manager)
        transferred = self.client.post(
            f'/api/v1/finance/budgets/{budget.id}/transfer/',
            {
                'from_line': line_ids[0], 'to_line': line_ids[1], 'amount': '80.00',
                'comments': 'Reallocate unused materials budget',
            },
            format='json',
        )
        self.assertEqual(transferred.status_code, 201, transferred.data)
        detail = self.client.get(f'/api/v1/finance/budgets/{budget.id}/')
        balances = {line['id']: Decimal(line['available_balance']) for line in detail.data['lines']}
        self.assertEqual(balances[line_ids[0]], Decimal('20.00'))
        self.assertEqual(balances[line_ids[1]], Decimal('130.00'))
        self.assertEqual(Decimal(detail.data['revised_budget']), Decimal('150.00'))

        exhausted = self.client.post(
            f'/api/v1/finance/budgets/{budget.id}/transfer/',
            {
                'from_line': line_ids[0], 'to_line': line_ids[1], 'amount': '30.00',
                'comments': 'Override transfer',
            },
            format='json',
        )
        self.assertEqual(exhausted.status_code, 400)
        overridden = self.client.post(
            f'/api/v1/finance/budgets/{budget.id}/transfer/',
            {
                'from_line': line_ids[0], 'to_line': line_ids[1], 'amount': '30.00',
                'comments': 'Manager-approved temporary deficit', 'override': True,
            },
            format='json',
        )
        self.assertEqual(overridden.status_code, 201, overridden.data)

    def test_budget_creation_submission_and_followup_notifications(self):
        self.client.force_authenticate(self.fixture.finance_officer)
        created = self.client.post(
            '/api/v1/finance/budgets/',
            {
                'project': self.fixture.project.id,
                'name': 'Follow-up budget',
                'lines': [{'category': self.category.id, 'description': 'Foundation works', 'original_amount': '500.00'}],
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        budget_id = created.data['id']

        submitted = self.client.post(f'/api/v1/finance/budgets/{budget_id}/submit/')
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.client.force_authenticate(self.fixture.finance_manager)
        with self.captureOnCommitCallbacks(execute=True):
            approved = self.client.post(
                f'/api/v1/finance/budgets/{budget_id}/approve/',
                {'comments': 'Reviewed and approved.'},
                format='json',
            )
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertTrue(Notification.objects.filter(
            recipient=self.fixture.finance_officer,
            title='Project budget approved',
        ).exists())

    def test_approved_revision_updates_revised_and_available_budget(self):
        budget, line_ids = self._approved_budget(first='500.00')
        self.client.force_authenticate(self.fixture.finance_manager)
        revised = self.client.post(
            f'/api/v1/finance/budgets/{budget.id}/revise/',
            {
                'budget_line': line_ids[0], 'amount': '125.00',
                'comments': 'Approved scope increase',
            },
            format='json',
        )
        self.assertEqual(revised.status_code, 201, revised.data)
        detail = self.client.get(f'/api/v1/finance/budgets/{budget.id}/')
        self.assertEqual(Decimal(detail.data['approved_revisions']), Decimal('125.00'))
        self.assertEqual(Decimal(detail.data['revised_budget']), Decimal('625.00'))
        self.assertEqual(Decimal(detail.data['available_balance']), Decimal('625.00'))
        self.assertEqual(Decimal(detail.data['lines'][0]['approved_revisions']), Decimal('125.00'))

    def test_technical_and_finance_approval_are_required_before_po(self):
        budget, line_ids = self._approved_budget(first='500000.00')
        self.fixture.project.site_engineers.add(self.fixture.engineer)
        self.client.force_authenticate(self.fixture.engineer)
        submitted = self.client.post(
            '/api/purchase-requests/',
            {
                'project': self.fixture.project.id,
                'title': 'Engineer material request',
                'priority': 'NORMAL',
                'justification': 'Required for slab works',
                'items': [{
                    'material': self.fixture.material.id,
                    'quantity': '10.00',
                    'notes': 'Deliver this week',
                }],
            },
            format='json',
        )
        self.assertEqual(submitted.status_code, 201, submitted.data)
        purchase_request = PurchaseRequest.objects.get(pk=submitted.data['id'])

        self.client.force_authenticate(self.fixture.procurement)
        before_technical = self.client.post(
            f'/api/purchase-orders/from-pr/{purchase_request.id}/',
            {'supplier': self.fixture.supplier.id}, format='json',
        )
        self.assertEqual(before_technical.status_code, 400)

        self.client.force_authenticate(self.fixture.manager)
        technical = self.client.post(f'/api/purchase-requests/{purchase_request.id}/approve/')
        self.assertEqual(technical.status_code, 200, technical.data)
        self.client.force_authenticate(self.fixture.procurement)
        before_finance = self.client.post(
            f'/api/purchase-orders/from-pr/{purchase_request.id}/',
            {'supplier': self.fixture.supplier.id}, format='json',
        )
        self.assertEqual(before_finance.status_code, 201, before_finance.data)
        pending_po_id = before_finance.data['id']

        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_ids[0]}, format='json',
        ).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(
            self.client.post(f'/api/purchase-requests/{purchase_request.id}/finance-approve/', {}).status_code,
            200,
        )
        self.client.force_authenticate(self.fixture.procurement)
        after_approvals = self.client.get(f'/api/purchase-orders/{pending_po_id}/')
        self.assertEqual(after_approvals.status_code, 200, after_approvals.data)
        self.client.force_authenticate(self.fixture.storekeeper)
        bypass_receipt = self.client.post(
            f'/api/purchase-orders/{pending_po_id}/receive/',
        )
        self.assertEqual(bypass_receipt.status_code, 400)
        self.assertIn('status', bypass_receipt.data)

    def test_finance_return_hold_and_reject_require_comments(self):
        budget, line_ids = self._approved_budget(first='500000.00')
        purchase_request = self.fixture.purchase_request(quantity=Decimal('1.00'))
        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_ids[0]}, format='json',
        ).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(
            self.client.post(f'/api/purchase-requests/{purchase_request.id}/finance-return/', {}).status_code,
            400,
        )
        returned = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-return/',
            {'comments': 'Clarify site quantities'}, format='json',
        )
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(returned.data['status'], BudgetApproval.STATUS_RETURNED)

        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_ids[0], 'comments': 'Quantities clarified'}, format='json',
        ).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        held = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-hold/',
            {'comments': 'Awaiting funding release'}, format='json',
        )
        self.assertEqual(held.status_code, 200)
        self.assertEqual(held.data['status'], BudgetApproval.STATUS_HOLD)
        self.assertEqual(
            self.client.post(f'/api/purchase-requests/{purchase_request.id}/finance-approve/', {}).status_code,
            200,
        )

        rejected_request = self.fixture.purchase_request(quantity=Decimal('1.00'))
        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{rejected_request.id}/submit-finance/',
            {'budget_line': line_ids[0]}, format='json',
        ).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        rejected = self.client.post(
            f'/api/purchase-requests/{rejected_request.id}/finance-reject/',
            {'comments': 'Not in approved scope'}, format='json',
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data['status'], BudgetApproval.STATUS_REJECTED)

    def test_returned_request_can_be_corrected_by_requester_and_resubmitted(self):
        _, line_ids = self._approved_budget(first='500000.00')
        purchase_request = self.fixture.purchase_request(quantity=Decimal('1.00'))
        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_ids[0]}, format='json',
        ).status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        returned = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/finance-return/',
            {'comments': 'Clarify the material quantity and site justification.'}, format='json',
        )
        self.assertEqual(returned.status_code, 200, returned.data)

        self.client.force_authenticate(self.fixture.engineer)
        corrected = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/correct/',
            {
                'project': purchase_request.project_id,
                'title': 'Corrected materials request',
                'priority': 'HIGH',
                'justification': 'Quantity and scope confirmed with the project manager.',
                'correction_summary': 'Reduced the quantity after site measurement and added the scope justification.',
                'items': [{'material': self.fixture.material.id, 'quantity': '1.00', 'notes': 'Verified site quantity'}],
            }, format='json',
        )
        self.assertEqual(corrected.status_code, 200, corrected.data)
        self.assertEqual(corrected.data['title'], 'Corrected materials request')
        self.assertEqual(corrected.data['status'], PurchaseRequest.STATUS_PENDING)
        self.assertEqual(corrected.data['finance_status'], BudgetApproval.STATUS_RETURNED)
        self.assertIn('Clarify the material quantity', corrected.data['finance_return_reason'])

        self.client.force_authenticate(self.fixture.manager)
        self.assertEqual(self.client.post(f'/api/purchase-requests/{purchase_request.id}/approve/').status_code, 200)
        resubmitted = self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_ids[0], 'comments': 'Corrected request resubmitted for review.'}, format='json',
        )
        self.assertEqual(resubmitted.status_code, 200, resubmitted.data)
        purchase_request.refresh_from_db()
        self.assertEqual(purchase_request.budget_approval.return_reason, 'Clarify the material quantity and site justification.')

    def test_double_purchase_order_approval_cannot_overspend_locked_budget(self):
        self.fixture.material.unit_price = Decimal('1.00')
        self.fixture.material.save(update_fields=['unit_price'])
        budget, line_ids = self._approved_budget(first='400.00')
        first_pr, first_approval = self._finance_approved_pr(line_ids[0], quantity='250.00')
        self.assertEqual(first_approval.status_code, 200, first_approval.data)
        second_pr, second_approval = self._finance_approved_pr(line_ids[0], quantity='250.00')
        self.assertEqual(second_approval.status_code, 200, second_approval.data)
        first_po = self._purchase_order(first_pr)
        second_po = self._purchase_order(second_pr)
        self.client.force_authenticate(self.fixture.procurement)
        self.assertEqual(self.client.post(f'/api/purchase-orders/{first_po.id}/approve/').status_code, 200)
        blocked = self.client.post(f'/api/purchase-orders/{second_po.id}/approve/')
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(BudgetTransaction.objects.filter(
            budget=budget, transaction_type=BudgetTransaction.TYPE_COMMITMENT,
        ).count(), 1)
        self.assertEqual(budget.open_commitments, Decimal('250.00'))

    def test_cancelling_purchase_order_releases_commitment(self):
        budget, line_ids = self._approved_budget()
        purchase_request, approval = self._finance_approved_pr(line_ids[0])
        self.assertEqual(approval.status_code, 200, approval.data)
        po = self._purchase_order(purchase_request)
        self.client.force_authenticate(self.fixture.procurement)
        self.assertEqual(self.client.post(f'/api/purchase-orders/{po.id}/approve/').status_code, 200)
        cancelled = self.client.post(
            f'/api/purchase-orders/{po.id}/cancel/', {'comments': 'Supplier unable to deliver'}, format='json',
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        budget.refresh_from_db()
        self.assertEqual(budget.open_commitments, Decimal('0.00'))
        self.assertEqual(budget.available_balance, Decimal('500000.00'))

    def test_cross_company_budget_and_finance_actions_are_hidden(self):
        budget, line_ids = self._approved_budget()
        self.client.force_authenticate(self.other.finance_viewer)
        self.assertEqual(self.client.get(f'/api/v1/finance/budgets/{budget.id}/').status_code, 404)
        self.client.force_authenticate(self.other.finance_officer)
        invalid = self.client.post(
            '/api/v1/finance/budgets/',
            {
                'project': self.other.project.id,
                'name': 'Invalid cross-company budget',
                'lines': [{'category': self.category.id, 'original_amount': '100.00'}],
            },
            format='json',
        )
        self.assertEqual(invalid.status_code, 400)
        purchase_request = self.fixture.purchase_request()
        self.client.force_authenticate(self.other.manager)
        self.assertEqual(self.client.post(
            f'/api/purchase-requests/{purchase_request.id}/submit-finance/',
            {'budget_line': line_ids[0]}, format='json',
        ).status_code, 404)
