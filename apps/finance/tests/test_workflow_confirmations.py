from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.accounts.models import Company, User
from apps.finance.confirmation_services import confirm_confirmation, return_confirmation, submit_confirmation
from apps.finance.models import WorkflowConfirmation


class WorkflowConfirmationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Controlled Workflow Co', slug='controlled-workflow')
        self.other_company = Company.objects.create(name='Other Controlled Co', slug='other-controlled')
        self.preparer = User.objects.create_user(
            username='workflow-preparer', password='pass', company=self.company,
            role=User.ROLE_PROCUREMENT_OFFICER,
        )
        self.finance = User.objects.create_user(
            username='workflow-finance', password='pass', company=self.company,
            role=User.ROLE_FINANCE_OFFICER,
        )
        self.manager = User.objects.create_user(
            username='workflow-manager', password='pass', company=self.company,
            role=User.ROLE_FINANCE_MANAGER,
        )
        self.other_user = User.objects.create_user(
            username='other-workflow-user', password='pass', company=self.other_company,
            role=User.ROLE_FINANCE_MANAGER,
        )
        self.client = APIClient()

    def task(self, *, submitted_by=None, required_role=User.ROLE_FINANCE_OFFICER):
        return submit_confirmation(
            company=self.company,
            document_type=WorkflowConfirmation.DOCUMENT_PURCHASE_ORDER,
            object_id='42',
            object_label='PO-0042',
            stage=WorkflowConfirmation.STAGE_FINANCE,
            required_role=required_role,
            submitted_by=submitted_by or self.preparer,
            action_url='/procurement/purchase-orders/42',
            snapshot={'total': '250000.00', 'supplier': 'Controlled Supplies'},
        )

    def test_finance_manager_can_cover_finance_officer_task_and_snapshot_is_immutable(self):
        task = self.task()
        confirmed = confirm_confirmation(task=task, user=self.manager, confirmation_data={'decision': 'approved'})
        self.assertEqual(confirmed.status, WorkflowConfirmation.STATUS_CONFIRMED)
        self.assertEqual(confirmed.confirmed_by, self.manager)
        confirmed.submitted_snapshot = {'total': '1.00'}
        with self.assertRaises(DjangoValidationError):
            confirmed.save()

    def test_preparer_cannot_confirm_own_submission(self):
        task = self.task(submitted_by=self.finance)
        with self.assertRaises(PermissionDenied):
            confirm_confirmation(task=task, user=self.finance)
        task.refresh_from_db()
        self.assertEqual(task.status, WorkflowConfirmation.STATUS_PENDING)

    def test_return_requires_responsible_role_and_reason(self):
        task = self.task()
        with self.assertRaises(PermissionDenied):
            return_confirmation(task=task, user=self.preparer, reason='Fix supplier')
        returned = return_confirmation(task=task, user=self.finance, reason='Fix supplier evidence')
        self.assertEqual(returned.status, WorkflowConfirmation.STATUS_RETURNED)
        self.assertEqual(returned.return_reason, 'Fix supplier evidence')

    def test_queue_is_company_scoped_and_manager_sees_officer_tasks(self):
        self.task()
        submit_confirmation(
            company=self.other_company,
            document_type=WorkflowConfirmation.DOCUMENT_PAYMENT,
            object_id='99', object_label='PAY-0099', stage=WorkflowConfirmation.STAGE_FINANCE,
            required_role=User.ROLE_FINANCE_MANAGER, submitted_by=self.other_user,
        )
        self.client.force_authenticate(self.manager)
        response = self.client.get('/api/v1/finance/workflow-confirmations/?status=PENDING')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['object_label'], 'PO-0042')
        self.assertTrue(response.data['results'][0]['is_my_action'])
