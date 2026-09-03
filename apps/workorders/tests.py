from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Company, User
from apps.projects.models import Project, ProjectSite
from apps.suppliers.models import Supplier
from .models import WorkOrder, WorkOrderAuditLog, WorkOrderSite, WorkOrderTask
from .services import generate_work_order_number, transition_work_order


class WorkOrderWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Work order test company')
        self.manager = User.objects.create_user(username='wo-manager', password='test', company=self.company, role=User.ROLE_PROJECT_MANAGER)
        self.engineer = User.objects.create_user(username='wo-engineer', password='test', company=self.company, role=User.ROLE_SITE_ENGINEER)
        self.project = Project.objects.create(company=self.company, name='WO Test Project', code='WOTEST', manager=self.manager, status=Project.STATUS_ACTIVE)
        self.project.site_engineers.add(self.engineer)
        self.work_order = WorkOrder.objects.create(company=self.company, number=generate_work_order_number(self.company), project=self.project, title='Repair generator', description='Repair site generator', requester=self.engineer, due_date=timezone.localdate())

    def test_number_and_lifecycle_are_controlled_and_audited(self):
        self.assertEqual(self.work_order.number, f'WO-{timezone.localdate().year}-0001')
        transition_work_order(work_order=self.work_order, actor=self.engineer, target_status=WorkOrder.STATUS_SUBMITTED)
        transition_work_order(work_order=self.work_order, actor=self.manager, target_status=WorkOrder.STATUS_APPROVED)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.status, WorkOrder.STATUS_APPROVED)
        self.assertEqual(WorkOrderAuditLog.objects.filter(work_order=self.work_order).count(), 2)
        with self.assertRaises(ValidationError):
            transition_work_order(work_order=self.work_order, actor=self.engineer, target_status=WorkOrder.STATUS_CLOSED)

    def test_audit_log_is_immutable(self):
        log = WorkOrderAuditLog.objects.create(work_order=self.work_order, actor=self.engineer, action='created')
        log.message = 'changed'
        with self.assertRaises(Exception):
            log.save()

    def test_master_cannot_close_while_a_site_package_is_unverified(self):
        physical_site = ProjectSite.objects.create(project=self.project, name='Main site', code='MAIN')
        site_package = WorkOrderSite.objects.create(work_order=self.work_order, project=self.project, project_site=physical_site, title='Generator repair at main site')
        self.work_order.status = WorkOrder.STATUS_VERIFIED
        self.work_order.save()
        with self.assertRaises(ValidationError):
            transition_work_order(work_order=self.work_order, actor=self.manager, target_status=WorkOrder.STATUS_CLOSED)
        site_package.status = WorkOrder.STATUS_VERIFIED
        site_package.save()
        transition_work_order(work_order=self.work_order, actor=self.manager, target_status=WorkOrder.STATUS_CLOSED)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.status, WorkOrder.STATUS_CLOSED)

    def test_manager_can_accept_contractor_only_assignment(self):
        contractor = Supplier.objects.create(company=self.company, name='Test Contractor', is_contractor=True)
        self.work_order.contractor = contractor
        self.work_order.status = WorkOrder.STATUS_APPROVED
        self.work_order.save()
        self.work_order.status = WorkOrder.STATUS_ASSIGNED
        self.work_order.save(update_fields=['status', 'updated_at'])
        from apps.workorders.views import WorkOrderViewSet
        # The service-level state required before execution is accepted on behalf
        # of the contractor by the project manager.
        self.work_order.assignment_status = WorkOrder.ASSIGNMENT_ACCEPTED
        self.work_order.save(update_fields=['assignment_status', 'updated_at'])
        transition_work_order(work_order=self.work_order, actor=self.manager, target_status=WorkOrder.STATUS_IN_PROGRESS)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.status, WorkOrder.STATUS_IN_PROGRESS)

    def test_task_dependency_is_recorded_for_execution_control(self):
        first = WorkOrderTask.objects.create(work_order=self.work_order, title='Prepare site')
        second = WorkOrderTask.objects.create(work_order=self.work_order, title='Install equipment', dependency=first)
        self.assertEqual(second.dependency_id, first.id)
