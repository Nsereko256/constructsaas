from decimal import Decimal
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.api.permissions import IsAuthenticatedCompanyUser
from apps.finance.configuration_services import record_finance_audit_event
from apps.notifications.helpers import send_notification
from apps.notifications.models import Notification
from apps.procurement.models import PurchaseRequest, PurchaseRequestItem
from apps.finance.models import SupplierInvoice
from apps.finance.report_exports import xlsx_response
from apps.pdf_exports import pdf_table_response
from apps.procurement.services import generate_pr_number
from apps.projects.access import accessible_projects
from apps.warehouse.models import StockMovement
from .models import WorkOrder, WorkOrderAttachment, WorkOrderAuditLog, WorkOrderChange, WorkOrderSite, WorkOrderTask
from .serializers import WorkOrderAttachmentSerializer, WorkOrderChangeSerializer, WorkOrderMaterialRequestSerializer, WorkOrderSerializer, WorkOrderSiteSerializer, WorkOrderTaskSerializer, WorkOrderTransitionSerializer
from .services import TRANSITIONS, generate_work_order_number, transition_work_order


WRITE_ROLES = {User.ROLE_ADMIN, User.ROLE_PROJECT_MANAGER, User.ROLE_SITE_ENGINEER}
APPROVER_ROLES = {User.ROLE_ADMIN, User.ROLE_PROJECT_MANAGER}
FINANCE_REVIEW_ROLES = {User.ROLE_ADMIN, User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER}


def operational_export_response(*, queryset, kind, title, filename, columns, row_builder, totals):
    rows = [row_builder(record) for record in queryset]
    if kind == 'xlsx':
        return xlsx_response({'title': title, 'columns': [{'key': key, 'label': label} for key, label in columns], 'rows': rows, 'totals': totals(rows)}, filename)
    return pdf_table_response(title=title, filename=filename, columns=columns, rows=rows, totals=totals(rows), subtitle='Company-scoped operational export using the active filters.')


class WorkOrderViewSet(viewsets.ModelViewSet):
    serializer_class = WorkOrderSerializer
    permission_classes = [IsAuthenticatedCompanyUser]
    filterset_fields = ['project', 'site', 'status', 'priority', 'contractor', 'responsible_person']
    search_fields = ['number', 'title', 'description', 'work_category']
    ordering_fields = ['number', 'due_date', 'priority', 'status', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        qs = WorkOrder.objects.filter(company=user.company).select_related('project', 'site', 'requester', 'responsible_person', 'contractor').prefetch_related('tasks', 'attachments', 'audit_logs', 'responsible_team')
        if user.role in {User.ROLE_PROJECT_MANAGER, User.ROLE_SITE_ENGINEER}:
            projects = accessible_projects(user, user.company.projects.all())
            qs = qs.filter(Q(project__in=projects) | Q(site_packages__project__in=projects))
        if user.role == User.ROLE_FINANCE_VIEWER:
            qs = qs.exclude(status=WorkOrder.STATUS_DRAFT)
        if self.request.query_params.get('project_site'):
            site_id = self.request.query_params['project_site']
            qs = qs.filter(Q(site_packages__project_site_id=site_id) | Q(site__project_site_id=site_id))
        return qs.distinct()

    def perform_create(self, serializer):
        if self.request.user.role not in WRITE_ROLES:
            raise PermissionDenied('Your role cannot create work orders.')
        work_order = serializer.save(company=self.request.user.company, requester=self.request.user, number=generate_work_order_number(self.request.user.company))
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=self.request.user, action='created', message='Work order created.')
        record_finance_audit_event(company=work_order.company, actor=self.request.user, action='work_order.created', object_type='WorkOrder', object_id=work_order.pk, metadata={'number': work_order.number})

    def perform_update(self, serializer):
        wo = self.get_object()
        if wo.status not in {WorkOrder.STATUS_DRAFT, WorkOrder.STATUS_REJECTED} and self.request.user.role not in APPROVER_ROLES:
            raise PermissionDenied('Only draft or returned work orders can be edited.')
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        raise ValidationError({'detail': 'Work orders are retained for audit. Cancel an unneeded work order instead.'})

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None): return self._transition(request, self.get_object(), WorkOrder.STATUS_SUBMITTED)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        work_order = self.get_object()
        if not work_order.project_id:
            raise ValidationError({'project': 'Assign a project to this legacy work order before approving it.'})
        return self._transition(request, work_order, WorkOrder.STATUS_APPROVED, approval=True)

    @action(detail=True, methods=['post'], url_path='submit-finance-review')
    def submit_finance_review(self, request, pk=None):
        work_order = self.get_object()
        if request.user.role not in APPROVER_ROLES:
            raise PermissionDenied('Only a project manager or admin can send work to Finance.')
        if work_order.status != WorkOrder.STATUS_APPROVED:
            raise ValidationError({'status': 'Finance review can be requested after technical approval.'})
        recipients = User.objects.filter(
            company=work_order.company,
            role__in=[User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN],
            is_active=True,
        ).exclude(pk=request.user.pk)
        for recipient in recipients:
            send_notification(
                recipient,
                Notification.TYPE_SYSTEM,
                Notification.LEVEL_INFO,
                f'{work_order.number}: finance review requested',
                f'{work_order.title} is technically approved and awaiting Finance budget confirmation.',
                f'/work-orders/{work_order.pk}',
            )
        WorkOrderAuditLog.objects.create(
            work_order=work_order,
            actor=request.user,
            action='finance_review_requested',
            message='Finance review requested.' if recipients.exists() else 'Finance review requested, but no active Finance recipient was found.',
        )
        return Response(self.get_serializer(work_order).data)
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        if request.user.role not in APPROVER_ROLES: raise PermissionDenied('Only a project manager or admin can assign work.')
        wo = self.get_object()
        if not (request.data.get('responsible_person') or request.data.get('contractor') or request.data.get('responsible_team')):
            raise ValidationError({'assignment': 'Select a responsible person, team, or contractor.'})
        serializer = self.get_serializer(wo, data=request.data, partial=True); serializer.is_valid(raise_exception=True); serializer.save(assignment_status=WorkOrder.ASSIGNMENT_PENDING, assignment_response='', assignment_responded_at=None)
        WorkOrderAuditLog.objects.create(work_order=wo, actor=request.user, action='assigned', message='Assignment issued and awaiting acceptance.')
        for user in {user for user in [wo.responsible_person, *wo.responsible_team.all()] if user and user.is_active}:
            send_notification(user, Notification.TYPE_SYSTEM, Notification.LEVEL_INFO, f'{wo.number}: assignment awaiting acceptance', 'Accept or decline the assignment and record any mobilisation constraint.', f'/work-orders/{wo.pk}')
        return self._transition(request, wo, WorkOrder.STATUS_ASSIGNED, approval=True)

    @action(detail=True, methods=['post'], url_path='accept-assignment')
    def accept_assignment(self, request, pk=None):
        work_order = self.get_object()
        assigned_ids = {work_order.responsible_person_id, *work_order.responsible_team.values_list('id', flat=True)}
        contractor_only = bool(work_order.contractor_id and not assigned_ids - {None})
        if contractor_only:
            if request.user.role not in APPROVER_ROLES:
                raise PermissionDenied('A project manager or admin must accept contractor-only work on behalf of the contractor.')
        elif request.user.role not in WRITE_ROLES or request.user.id not in assigned_ids:
            raise PermissionDenied('Only an assigned internal team member can accept this work order.')
        if work_order.status != WorkOrder.STATUS_ASSIGNED:
            raise ValidationError({'status': 'Only an assigned work order can be accepted.'})
        response = str(request.data.get('response', '')).strip()
        work_order.assignment_status = WorkOrder.ASSIGNMENT_ACCEPTED
        work_order.assignment_response = response
        work_order.assignment_responded_at = timezone.now()
        work_order.save(update_fields=['assignment_status', 'assignment_response', 'assignment_responded_at', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='assignment_accepted', message=response or 'Assignment accepted.')
        return Response(self.get_serializer(work_order).data)

    @action(detail=True, methods=['post'], url_path='decline-assignment')
    def decline_assignment(self, request, pk=None):
        work_order = self.get_object()
        if request.user.role not in WRITE_ROLES or request.user.id not in {work_order.responsible_person_id, *work_order.responsible_team.values_list('id', flat=True)}:
            raise PermissionDenied('Only an assigned internal team member can decline this work order.')
        response = str(request.data.get('response', '')).strip()
        if not response:
            raise ValidationError({'response': 'Explain why the assignment cannot be accepted.'})
        work_order.assignment_status = WorkOrder.ASSIGNMENT_DECLINED
        work_order.assignment_response = response
        work_order.assignment_responded_at = timezone.now()
        work_order.save(update_fields=['assignment_status', 'assignment_response', 'assignment_responded_at', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='assignment_declined', message=response)
        return Response(self.get_serializer(work_order).data)

    @action(detail=True, methods=['post'], url_path='finance-review')
    def finance_review(self, request, pk=None):
        work_order = self.get_object()
        if request.user.role not in FINANCE_REVIEW_ROLES:
            raise PermissionDenied('Only Finance Manager or Admin can confirm work-order budget availability.')
        if work_order.status not in {WorkOrder.STATUS_APPROVED, WorkOrder.STATUS_ON_HOLD}:
            raise ValidationError({'status': 'Finance review is available after technical approval and before assignment.'})
        notes = str(request.data.get('notes', '')).strip()
        approved_cost = request.data.get('approved_cost', work_order.estimated_cost)
        try:
            approved_cost = Decimal(str(approved_cost))
        except Exception:
            raise ValidationError({'approved_cost': 'Enter a valid approved cost.'})
        if approved_cost < 0:
            raise ValidationError({'approved_cost': 'Approved cost cannot be negative.'})
        work_order.finance_reviewed_by = request.user
        work_order.finance_reviewed_at = timezone.now()
        work_order.finance_review_notes = notes
        work_order.approved_cost = approved_cost
        work_order.save(update_fields=['finance_reviewed_by', 'finance_reviewed_at', 'finance_review_notes', 'approved_cost', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='finance_reviewed', message=notes or 'Budget availability confirmed.', metadata={'approved_cost': str(approved_cost)})
        return Response(self.get_serializer(work_order).data)
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None): return self._transition(request, self.get_object(), WorkOrder.STATUS_IN_PROGRESS)
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None): return self._transition(request, self.get_object(), WorkOrder.STATUS_COMPLETED)
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None): return self._transition(request, self.get_object(), WorkOrder.STATUS_VERIFIED, approval=True)
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None): return self._transition(request, self.get_object(), WorkOrder.STATUS_CLOSED, approval=True)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None): return self._transition(request, self.get_object(), WorkOrder.STATUS_REJECTED, approval=True, reason=True)
    @action(detail=True, methods=['post'])
    def hold(self, request, pk=None): return self._transition(request, self.get_object(), WorkOrder.STATUS_ON_HOLD, approval=True, reason=True)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        work_order = self.get_object()
        open_pos = work_order.purchase_requests.exclude(purchase_orders__status=PurchaseRequest.STATUS_REJECTED).filter(purchase_orders__isnull=False).exclude(purchase_orders__status='CANCELLED').values_list('purchase_orders__number', flat=True)
        if open_pos and not request.data.get('confirm_procurement_impact'):
            raise ValidationError({'procurement': f"Open purchase orders require explicit procurement treatment before cancellation: {', '.join(open_pos)}.", 'confirm_procurement_impact': 'Confirm you have cancelled or closed supplier commitments.'})
        return self._transition(request, work_order, WorkOrder.STATUS_CANCELLED, reason=True)

    @action(detail=True, methods=['post'], url_path='reopen')
    def reopen(self, request, pk=None):
        work_order = self.get_object()
        if request.user.role not in APPROVER_ROLES:
            raise PermissionDenied('Only a project manager or admin can reopen verified work.')
        reason = str(request.data.get('reason', '')).strip()
        if not reason:
            raise ValidationError({'reason': 'Explain why verified work must be reopened.'})
        if work_order.status not in {WorkOrder.STATUS_COMPLETED, WorkOrder.STATUS_VERIFIED, WorkOrder.STATUS_CLOSED}:
            raise ValidationError({'status': 'Only completed, verified, or closed work can be reopened.'})
        before = work_order.status; work_order.status = WorkOrder.STATUS_IN_PROGRESS; work_order.save(update_fields=['status', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='reopened', from_status=before, to_status=work_order.status, message=reason)
        return Response(self.get_serializer(work_order).data)

    @action(detail=True, methods=['post'], url_path='emergency-retrospective-review')
    def emergency_retrospective_review(self, request, pk=None):
        work_order = self.get_object()
        if request.user.role not in FINANCE_REVIEW_ROLES or not work_order.is_emergency:
            raise PermissionDenied('Only Finance Manager or Admin can retrospectively review emergency work.')
        notes = str(request.data.get('notes', '')).strip()
        if not notes:
            raise ValidationError({'notes': 'Record the retrospective approval decision and justification.'})
        work_order.emergency_retrospectively_approved_by = request.user; work_order.emergency_retrospectively_approved_at = timezone.now(); work_order.emergency_retrospective_notes = notes; work_order.save(update_fields=['emergency_retrospectively_approved_by', 'emergency_retrospectively_approved_at', 'emergency_retrospective_notes', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='emergency_retrospective_reviewed', message=notes)
        return Response(self.get_serializer(work_order).data)

    def _transition(self, request, work_order, target, approval=False, reason=False):
        if approval and request.user.role not in APPROVER_ROLES: raise PermissionDenied('Only a project manager or admin can perform this action.')
        if not approval and request.user.role not in WRITE_ROLES: raise PermissionDenied('Your role cannot perform this action.')
        if target in {WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_COMPLETED} and request.user.role == User.ROLE_SITE_ENGINEER:
            assigned_ids = set(work_order.responsible_team.values_list('id', flat=True))
            if work_order.responsible_person_id:
                assigned_ids.add(work_order.responsible_person_id)
            if request.user.id not in assigned_ids:
                raise PermissionDenied('Only the assigned engineer, project manager, or admin can update execution status.')
        payload = WorkOrderTransitionSerializer(data=request.data); payload.is_valid(raise_exception=True)
        comments = payload.validated_data.get('comments', '')
        if reason and not comments.strip(): raise ValidationError({'comments': 'A reason is required.'})
        hold_owner = None
        if target == WorkOrder.STATUS_ON_HOLD:
            owner_id = request.data.get('hold_owner')
            if not owner_id or not request.data.get('hold_recovery_date'):
                raise ValidationError({'hold': 'Select a hold owner and recovery date so the hold can be followed up.'})
            hold_owner = User.objects.filter(pk=owner_id, company=work_order.company, is_active=True).first()
            if hold_owner is None:
                raise ValidationError({'hold_owner': 'Select an active company user.'})
        updated = transition_work_order(work_order=work_order, actor=request.user, target_status=target, comments=comments)
        if target == WorkOrder.STATUS_ON_HOLD:
            updated.hold_owner = hold_owner
            updated.hold_recovery_date = request.data.get('hold_recovery_date')
            updated.revised_due_date = request.data.get('revised_due_date') or updated.revised_due_date
            updated.save(update_fields=['hold_owner', 'hold_recovery_date', 'revised_due_date', 'updated_at'])
            WorkOrderAuditLog.objects.create(work_order=updated, actor=request.user, action='hold_follow_up_set', message=f'Hold owned by {hold_owner.get_full_name() or hold_owner.username} until {updated.hold_recovery_date}.')
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=['get', 'post'], url_path='changes')
    def changes(self, request, pk=None):
        work_order = self.get_object()
        if request.method == 'GET':
            return Response(WorkOrderChangeSerializer(work_order.changes.all(), many=True).data)
        if request.user.role not in WRITE_ROLES:
            raise PermissionDenied('Your role cannot request a work-order change.')
        serializer = WorkOrderChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change = serializer.save(work_order=work_order, requested_by=request.user, status=WorkOrderChange.STATUS_SUBMITTED)
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='scope_change_requested', message=change.reason, metadata={'change': change.pk})
        return Response(WorkOrderChangeSerializer(change).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='changes/(?P<change_id>[^/.]+)/approve')
    @transaction.atomic
    def approve_change(self, request, pk=None, change_id=None):
        work_order = self.get_object()
        if request.user.role not in APPROVER_ROLES:
            raise PermissionDenied('Only a project manager or admin can approve a scope change.')
        change = work_order.changes.select_for_update().filter(pk=change_id).first()
        if change is None or change.status != WorkOrderChange.STATUS_SUBMITTED:
            raise ValidationError({'change': 'Select a submitted scope change.'})
        cost_increase = change.proposed_estimated_cost is not None and change.proposed_estimated_cost > work_order.approved_cost
        if cost_increase and request.data.get('finance_confirmed') is not True:
            raise ValidationError({'finance_confirmed': 'Confirm Finance approval for a cost increase before applying this change.'})
        if change.proposed_scope:
            work_order.description = change.proposed_scope
        if change.proposed_due_date:
            work_order.due_date = change.proposed_due_date
            work_order.revised_due_date = change.proposed_due_date
        if change.proposed_estimated_cost is not None:
            work_order.estimated_cost = change.proposed_estimated_cost
            if cost_increase:
                work_order.approved_cost = change.proposed_estimated_cost
        if change.proposed_contractor_id:
            work_order.contractor = change.proposed_contractor
        work_order.scope_version += 1
        work_order.save()
        change.status = WorkOrderChange.STATUS_APPROVED
        change.reviewed_by = request.user
        change.review_notes = str(request.data.get('review_notes', '')).strip()
        change.reviewed_at = timezone.now()
        change.save(update_fields=['status', 'reviewed_by', 'review_notes', 'reviewed_at', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='scope_change_approved', message=change.reason, metadata={'change': change.pk, 'scope_version': work_order.scope_version})
        return Response(WorkOrderChangeSerializer(change).data)

    @action(detail=True, methods=['post'], url_path='changes/(?P<change_id>[^/.]+)/reject')
    def reject_change(self, request, pk=None, change_id=None):
        work_order = self.get_object()
        if request.user.role not in APPROVER_ROLES:
            raise PermissionDenied('Only a project manager or admin can reject a scope change.')
        change = work_order.changes.filter(pk=change_id, status=WorkOrderChange.STATUS_SUBMITTED).first()
        notes = str(request.data.get('review_notes', '')).strip()
        if change is None:
            raise ValidationError({'change': 'Select a submitted scope change.'})
        if not notes:
            raise ValidationError({'review_notes': 'Explain why this change was rejected.'})
        change.status = WorkOrderChange.STATUS_REJECTED
        change.reviewed_by = request.user
        change.review_notes = notes
        change.reviewed_at = timezone.now()
        change.save(update_fields=['status', 'reviewed_by', 'review_notes', 'reviewed_at', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='scope_change_rejected', message=notes, metadata={'change': change.pk})
        return Response(WorkOrderChangeSerializer(change).data)

    @action(detail=True, methods=['post'], url_path='material-requests')
    def material_requests(self, request, pk=None):
        wo = self.get_object()
        if request.user.role not in WRITE_ROLES: raise PermissionDenied('Your role cannot create a material request.')
        if wo.status not in {WorkOrder.STATUS_APPROVED, WorkOrder.STATUS_ASSIGNED, WorkOrder.STATUS_IN_PROGRESS}: raise ValidationError({'status': 'Materials can be requested only after work order approval.'})
        payload = WorkOrderMaterialRequestSerializer(data=request.data); payload.is_valid(raise_exception=True)
        site_package = None
        if payload.validated_data.get('site_package'):
            site_package = wo.site_packages.filter(pk=payload.validated_data['site_package']).first()
            if site_package is None:
                raise ValidationError({'site_package': 'Select a site package belonging to this work order.'})
        elif wo.site_packages.exists():
            raise ValidationError({'site_package': 'Select the site package receiving these materials.'})
        pr = PurchaseRequest.objects.create(company=wo.company, project=site_package.project if site_package else wo.project, work_order=wo, work_order_site=site_package, number=generate_pr_number(wo.company), title=payload.validated_data.get('title') or f'Materials for {wo.number}', priority=payload.validated_data['priority'], justification=payload.validated_data.get('justification') or wo.title, requested_by=request.user)
        for item in payload.validated_data['items']:
            PurchaseRequestItem.objects.create(purchase_request=pr, material_id=item['material'], quantity=item['quantity'], notes=item.get('notes', ''))
        WorkOrderAuditLog.objects.create(work_order=wo, actor=request.user, action='material_request_created', message=f'Created material request {pr.number}.', metadata={'purchase_request': pr.pk})
        return Response({'id': pr.pk, 'number': pr.number, 'status': pr.status}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='sites')
    def sites(self, request, pk=None):
        wo = self.get_object()
        if request.user.role not in APPROVER_ROLES:
            raise PermissionDenied('Only a project manager or admin can add work order sites.')
        serializer = WorkOrderSiteSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        if serializer.validated_data['project'].pk != wo.project_id:
            raise ValidationError({'project': 'Every site package must belong to the work order project.'})
        site_package = serializer.save(work_order=wo, contractor=serializer.validated_data.get('contractor') or wo.contractor)
        WorkOrderAuditLog.objects.create(work_order=wo, actor=request.user, action='site_package_created', message=f'Added {site_package.project.name} / {site_package.project_site.name}.', metadata={'site_package': site_package.pk})
        return Response(WorkOrderSiteSerializer(site_package).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='tasks')
    def tasks(self, request, pk=None):
        wo = self.get_object()
        if request.user.role not in WRITE_ROLES: raise PermissionDenied('Your role cannot add tasks.')
        serializer = WorkOrderTaskSerializer(data=request.data); serializer.is_valid(raise_exception=True); task = serializer.save(work_order=wo)
        if task.dependency_id and task.dependency.work_order_id != wo.id:
            task.delete()
            raise ValidationError({'dependency': 'Dependency must belong to this work order.'})
        if task.dependency_id == task.id:
            task.delete()
            raise ValidationError({'dependency': 'A task cannot depend on itself.'})
        WorkOrderAuditLog.objects.create(work_order=wo, actor=request.user, action='task_created', message=task.title)
        return Response(WorkOrderTaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='tasks/(?P<task_id>[^/.]+)')
    def update_task(self, request, pk=None, task_id=None):
        work_order = self.get_object()
        task = work_order.tasks.filter(pk=task_id).first()
        if task is None:
            raise ValidationError({'task': 'Task does not belong to this work order.'})
        if request.user.role not in WRITE_ROLES:
            raise PermissionDenied('Your role cannot update work-order tasks.')
        if request.user.role == User.ROLE_SITE_ENGINEER and task.assignee_id and task.assignee_id != request.user.id:
            raise PermissionDenied('Only the assigned engineer, project manager, or admin can update this task.')
        serializer = WorkOrderTaskSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data.get('status', task.status)
        requested_progress = serializer.validated_data.get('completion_percent', task.completion_percent)
        if (requested_status in {WorkOrderTask.STATUS_IN_PROGRESS, WorkOrderTask.STATUS_COMPLETED} or requested_progress > 0) and task.dependency_id:
            dependency = task.dependency
            if dependency.status != WorkOrderTask.STATUS_COMPLETED:
                raise ValidationError({'dependency': f'Complete dependency "{dependency.title}" before starting this task.'})
        updated = serializer.save()
        if updated.completion_percent == 100 or updated.status == WorkOrderTask.STATUS_COMPLETED:
            updated.status = WorkOrderTask.STATUS_COMPLETED
            updated.completion_percent = 100
            updated.completed_at = timezone.now()
            updated.save(update_fields=['status', 'completion_percent', 'completed_at', 'updated_at'])
        elif task.status == WorkOrderTask.STATUS_COMPLETED:
            updated.completed_at = None
            updated.save(update_fields=['completed_at', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=work_order, actor=request.user, action='task_updated', message=updated.title, metadata={'task': updated.pk, 'status': updated.status, 'completion_percent': updated.completion_percent})
        return Response(WorkOrderTaskSerializer(updated).data)

    @action(detail=True, methods=['post'], url_path='attachments')
    def attachments(self, request, pk=None):
        if request.user.role not in WRITE_ROLES:
            raise PermissionDenied('Your role cannot attach work-order documents.')
        wo = self.get_object(); serializer = WorkOrderAttachmentSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        attachment = serializer.save(work_order=wo, uploaded_by=request.user, name=request.data.get('name') or request.FILES['file'].name)
        WorkOrderAuditLog.objects.create(work_order=wo, actor=request.user, action='attachment_added', message=attachment.name, metadata={'attachment': attachment.pk})
        return Response(WorkOrderAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def metrics(self, request):
        qs = self.get_queryset(); today = timezone.localdate()
        material_cost = sum(((wo.stock_movements.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')) + (wo.site_packages.aggregate(total=Sum('stock_movements__total_cost'))['total'] or Decimal('0'))) for wo in qs)
        service_cost = SupplierInvoice.objects.filter(Q(work_order__in=qs) | Q(work_order_site__work_order__in=qs), status__in=[SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID]).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        return Response({'open': qs.exclude(status__in=[WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED, WorkOrder.STATUS_COMPLETED]).count(), 'in_progress': qs.filter(status=WorkOrder.STATUS_IN_PROGRESS).count(), 'overdue': qs.filter(due_date__lt=today).exclude(status__in=[WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED]).count(), 'completed': qs.filter(status__in=[WorkOrder.STATUS_COMPLETED, WorkOrder.STATUS_VERIFIED, WorkOrder.STATUS_CLOSED]).count(), 'estimated_cost': str(qs.aggregate(total=Sum('estimated_cost'))['total'] or Decimal('0')), 'actual_cost': str(material_cost + service_cost)})

    @action(detail=False, methods=['get'], url_path='action-queue')
    def action_queue(self, request):
        qs = self.get_queryset()
        user = request.user
        today = timezone.localdate()
        if user.role in APPROVER_ROLES:
            actionable = qs.filter(
                Q(status__in=[WorkOrder.STATUS_SUBMITTED, WorkOrder.STATUS_COMPLETED, WorkOrder.STATUS_VERIFIED])
                | Q(status=WorkOrder.STATUS_ASSIGNED, assignment_status=WorkOrder.ASSIGNMENT_PENDING, contractor__isnull=False)
            )
        elif user.role in FINANCE_REVIEW_ROLES:
            actionable = qs.filter(status=WorkOrder.STATUS_APPROVED, estimated_cost__gt=0, finance_reviewed_at__isnull=True)
        else:
            actionable = qs.filter(Q(responsible_person=user) | Q(responsible_team=user), status__in=[WorkOrder.STATUS_ASSIGNED, WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_ON_HOLD])
        return Response({
            'requires_action': self.get_serializer(actionable.distinct()[:30], many=True).data,
            'overdue': self.get_serializer(qs.filter(due_date__lt=today).exclude(status__in=[WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED])[:30], many=True).data,
            'held': self.get_serializer(qs.filter(status=WorkOrder.STATUS_ON_HOLD)[:30], many=True).data,
        })

    @action(detail=False, methods=['get'], url_path='material-availability')
    def material_availability(self, request):
        material_id = request.query_params.get('material')
        if not material_id:
            raise ValidationError({'material': 'Select a material.'})
        movements = StockMovement.objects.filter(company=request.user.company, material_id=material_id)
        warehouse_id = request.query_params.get('warehouse')
        if warehouse_id:
            movements = movements.filter(warehouse_id=warehouse_id)
        rows = movements.values('warehouse_id', 'warehouse__name').annotate(on_hand=Sum('quantity_effect')).order_by('warehouse__name')
        return Response({'material': int(material_id), 'locations': [{'warehouse': row['warehouse_id'], 'warehouse_name': row['warehouse__name'], 'on_hand': str(row['on_hand'] or 0)} for row in rows]})

    @action(detail=False, methods=['get'], url_path='schedule')
    def schedule(self, request):
        sites = WorkOrderSite.objects.filter(work_order__in=self.get_queryset()).select_related('work_order', 'project', 'project_site', 'responsible_person', 'contractor').exclude(status__in=[WorkOrder.STATUS_CANCELLED, WorkOrder.STATUS_CLOSED])
        return Response([{'id': site.id, 'work_order': site.work_order.number, 'project': site.project.name, 'site': site.project_site.name, 'scope': site.title or site.work_order.title, 'start': site.estimated_start_date, 'due': site.revised_due_date or site.due_date, 'status': site.status, 'progress': site.progress_percent, 'responsible': (site.responsible_person.get_full_name() or site.responsible_person.username) if site.responsible_person else '', 'contractor': site.contractor.name if site.contractor else ''} for site in sites.order_by('estimated_start_date', 'due_date')])

    @action(detail=False, methods=['get'], url_path='contractor-performance')
    def contractor_performance(self, request):
        if request.user.role not in {User.ROLE_ADMIN, User.ROLE_PROJECT_MANAGER, User.ROLE_PROCUREMENT_OFFICER, User.ROLE_FINANCE_MANAGER, User.ROLE_FINANCE_VIEWER}:
            raise PermissionDenied('Your role cannot view contractor performance.')
        from apps.suppliers.models import Supplier
        rows = []
        for contractor in Supplier.objects.filter(company=request.user.company, is_contractor=True, is_active=True):
            work = self.get_queryset().filter(contractor=contractor)
            closed = work.filter(status=WorkOrder.STATUS_CLOSED)
            overdue = work.filter(due_date__lt=timezone.localdate()).exclude(status__in=[WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED])
            rows.append({'id': contractor.id, 'name': contractor.name, 'specialty': contractor.contractor_specialty, 'rating': contractor.rating, 'open_work_orders': work.exclude(status__in=[WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED]).count(), 'closed_work_orders': closed.count(), 'overdue_work_orders': overdue.count(), 'compliance_expiry_date': contractor.compliance_expiry_date, 'insurance_expiry_date': contractor.contractor_insurance_expiry_date, 'safety_expiry_date': contractor.contractor_safety_clearance_expiry_date, 'mobilisation_days': contractor.contractor_mobilisation_days})
        return Response(rows)

    @action(detail=False, methods=['get'], url_path='operations-report')
    def operations_report(self, request):
        qs = self.get_queryset(); today = timezone.localdate(); completed = qs.filter(status__in=[WorkOrder.STATUS_COMPLETED, WorkOrder.STATUS_VERIFIED, WorkOrder.STATUS_CLOSED])
        total = qs.count()
        site_qs = WorkOrderSite.objects.filter(work_order__in=qs)
        return Response({'work_orders': total, 'overdue': qs.filter(due_date__lt=today).exclude(status__in=[WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED]).count(), 'on_hold': qs.filter(status=WorkOrder.STATUS_ON_HOLD).count(), 'completed': completed.count(), 'completion_rate': round((completed.count() / total * 100) if total else 0, 1), 'site_packages': site_qs.count(), 'site_average_progress': round(float(site_qs.aggregate(value=Sum('progress_percent'))['value'] or 0) / site_qs.count(), 1) if site_qs.exists() else 0, 'scope_changes_pending': WorkOrderChange.objects.filter(work_order__in=qs, status=WorkOrderChange.STATUS_SUBMITTED).count(), 'emergency_pending_review': qs.filter(is_emergency=True, emergency_retrospectively_approved_at__isnull=True).count()})

    @action(detail=False, methods=['post'], url_path='escalate-overdue')
    def escalate_overdue(self, request):
        if request.user.role not in APPROVER_ROLES:
            raise PermissionDenied('Only a project manager or admin can run overdue escalation.')
        overdue = self.get_queryset().filter(due_date__lt=timezone.localdate()).exclude(status__in=[WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED])
        for wo in overdue:
            recipients = [wo.responsible_person, wo.project.manager if wo.project_id else None]
            for recipient in {person for person in recipients if person and person.is_active}:
                send_notification(recipient, Notification.TYPE_SYSTEM, Notification.LEVEL_WARNING, f'{wo.number}: overdue work', f'Work order is overdue; update the recovery plan or place it on hold with an owner.', f'/work-orders/{wo.pk}')
            WorkOrderAuditLog.objects.create(work_order=wo, actor=request.user, action='overdue_escalated', message='Overdue escalation issued.')
        return Response({'escalated': overdue.count()})

    @action(detail=False, methods=['get'], url_path='invoices')
    def invoices(self, request):
        work_orders = self.get_queryset()
        invoices = SupplierInvoice.objects.filter(
            Q(work_order__in=work_orders) | Q(work_order_site__work_order__in=work_orders),
        ).select_related('supplier', 'work_order', 'work_order_site', 'work_order_site__project_site').order_by('-created_at').distinct()
        return Response([{
            'id': invoice.id,
            'work_order': invoice.work_order.number if invoice.work_order_id else invoice.work_order_site.work_order.number,
            'site': invoice.work_order_site.project_site.name if invoice.work_order_site_id else '',
            'internal_number': invoice.internal_number,
            'invoice_number': invoice.invoice_number,
            'supplier': invoice.supplier.name,
            'total_amount': str(invoice.total_amount),
            'currency': invoice.currency,
            'status': invoice.status,
            'due_date': invoice.due_date,
        } for invoice in invoices])

    @action(detail=True, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download_detail(self, request, pk=None, kind=None):
        work_order = self.get_object()
        rows = [{
            'work_order': work_order.number,
            'project': work_order.project.name if work_order.project_id else '-',
            'site': site.project_site.name if site.project_site_id else '-',
            'scope': site.title or work_order.title,
            'status': site.get_status_display(),
            'progress': f'{site.progress_percent}%',
            'estimated': site.estimated_cost,
            'actual': site.total_actual_cost,
            'due': site.revised_due_date or site.due_date or '-',
        } for site in work_order.site_packages.select_related('project_site').all()]
        if not rows:
            rows = [{'work_order': work_order.number, 'project': work_order.project.name if work_order.project_id else '-', 'site': work_order.site.name if work_order.site_id else '-', 'scope': work_order.title, 'status': work_order.get_status_display(), 'progress': '-', 'estimated': work_order.estimated_cost, 'actual': WorkOrderSerializer(work_order).get_actual_cost(work_order), 'due': work_order.revised_due_date or work_order.due_date or '-'}]
        return operational_export_response(
            queryset=rows, kind=kind, title=f'Work order - {work_order.number}', filename=work_order.number,
            columns=[('work_order', 'Work order'), ('project', 'Project'), ('site', 'Site'), ('scope', 'Scope'), ('status', 'Status'), ('progress', 'Progress'), ('estimated', 'Estimated cost'), ('actual', 'Actual cost'), ('due', 'Due date')],
            row_builder=lambda item: item, totals=lambda ignored: {'Work order': work_order.number, 'Sites': len(rows), 'Status': work_order.get_status_display()},
        ) if kind == 'pdf' else xlsx_response({'title': f'Work order - {work_order.number}', 'columns': [{'key': key, 'label': label} for key, label in [('work_order', 'Work order'), ('project', 'Project'), ('site', 'Site'), ('scope', 'Scope'), ('status', 'Status'), ('progress', 'Progress'), ('estimated', 'Estimated cost'), ('actual', 'Actual cost'), ('due', 'Due date')]], 'rows': rows, 'totals': {'Work order': work_order.number, 'Sites': len(rows), 'Status': work_order.get_status_display()}}, work_order.number)

    @action(detail=False, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, kind=None):
        qs = self.filter_queryset(self.get_queryset())
        return operational_export_response(queryset=qs, kind=kind, title='Work orders register', filename='work-orders-register', columns=[('number','Work order'),('project','Project'),('title','Scope'),('status','Status'),('priority','Priority'),('due','Due date'),('estimated','Estimated cost'),('actual','Actual cost')], row_builder=lambda wo: {'number':wo.number,'project':wo.project.name if wo.project_id else '-','title':wo.title,'status':wo.get_status_display(),'priority':wo.get_priority_display(),'due':wo.due_date or '-','estimated':wo.estimated_cost,'actual':WorkOrderSerializer(wo).get_actual_cost(wo)}, totals=lambda rows: {'Work orders':len(rows),'Open':sum(1 for row in rows if row['status'] not in {'Closed','Cancelled'}),'Estimated cost':sum((Decimal(str(row['estimated'])) for row in rows),Decimal('0'))})


class WorkOrderSiteViewSet(viewsets.ModelViewSet):
    serializer_class = WorkOrderSiteSerializer
    permission_classes = [IsAuthenticatedCompanyUser]
    filterset_fields = ['work_order', 'project', 'project_site', 'site', 'status', 'contractor', 'responsible_person']
    ordering = ['due_date', 'id']

    def get_queryset(self):
        qs = WorkOrderSite.objects.filter(work_order__company=self.request.user.company).select_related('work_order', 'project', 'project_site', 'site', 'responsible_person', 'contractor').prefetch_related('tasks')
        if self.request.user.role in {User.ROLE_PROJECT_MANAGER, User.ROLE_SITE_ENGINEER}:
            qs = qs.filter(project__in=accessible_projects(self.request.user, self.request.user.company.projects.all()))
        return qs

    def create(self, request, *args, **kwargs):
        raise PermissionDenied('Add site packages from their master work order.')

    def perform_update(self, serializer):
        if self.request.user.role not in WRITE_ROLES:
            raise PermissionDenied('Your role cannot edit site packages.')
        if serializer.instance.status not in {WorkOrder.STATUS_DRAFT, WorkOrder.STATUS_REJECTED}:
            raise PermissionDenied('Only draft or returned site packages can be edited. Use the controlled workflow for active work.')
        serializer.save()

    @action(detail=True, methods=['post'], url_path='progress')
    def progress(self, request, pk=None):
        site_package = self.get_object()
        if request.user.role not in WRITE_ROLES:
            raise PermissionDenied('Your role cannot update site progress.')
        if request.user.role == User.ROLE_SITE_ENGINEER and site_package.responsible_person_id and site_package.responsible_person_id != request.user.id:
            raise PermissionDenied('Only the assigned engineer, project manager, or admin can update this site package.')
        if site_package.status not in {WorkOrder.STATUS_ASSIGNED, WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_ON_HOLD}:
            raise ValidationError({'status': 'Start or assign this site package before reporting progress.'})
        try:
            progress_percent = int(request.data.get('progress_percent'))
        except (TypeError, ValueError):
            raise ValidationError({'progress_percent': 'Enter a whole percentage from 0 to 100.'})
        if not 0 <= progress_percent <= 100:
            raise ValidationError({'progress_percent': 'Progress must be from 0 to 100.'})
        notes = str(request.data.get('progress_notes', '')).strip()
        if not notes:
            raise ValidationError({'progress_notes': 'Describe work completed, blockers, or the next step.'})
        before = site_package.progress_percent
        site_package.progress_percent = progress_percent
        site_package.progress_notes = notes
        site_package.progress_updated_at = timezone.now()
        if progress_percent and site_package.status == WorkOrder.STATUS_ASSIGNED:
            site_package.status = WorkOrder.STATUS_IN_PROGRESS
        site_package.save()
        WorkOrderAuditLog.objects.create(work_order=site_package.work_order, actor=request.user, action='site_progress_updated', message=notes, metadata={'site_package': site_package.pk, 'from_percent': before, 'to_percent': progress_percent})
        return Response(self.get_serializer(site_package).data)

    @action(detail=False, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, kind=None):
        qs = self.filter_queryset(self.get_queryset())
        return operational_export_response(queryset=qs, kind=kind, title='Work-order site progress', filename='work-order-site-progress', columns=[('work_order','Work order'),('project','Project'),('site','Physical site'),('scope','Scope'),('status','Status'),('progress','Progress'),('updated','Last update'),('notes','Latest update')], row_builder=lambda site: {'work_order':site.work_order.number,'project':site.project.name,'site':site.project_site.name,'scope':site.title or site.work_order.title,'status':site.get_status_display(),'progress':f'{site.progress_percent}%','updated':site.progress_updated_at.strftime('%Y-%m-%d %H:%M') if site.progress_updated_at else '-','notes':site.progress_notes or '-'}, totals=lambda rows: {'Site packages':len(rows),'In progress':sum(1 for row in rows if row['status']=='In Progress'),'Average completion':f"{(sum(int(str(row['progress']).rstrip('%')) for row in rows)/len(rows)):.1f}%" if rows else '0%'})

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        site_package = self.get_object()
        target = request.data.get('status')
        if target not in dict(WorkOrder.STATUS_CHOICES):
            raise ValidationError({'status': 'Select a valid site-package status.'})
        if target not in TRANSITIONS.get(site_package.status, set()):
            raise ValidationError({'status': f'{site_package.get_status_display()} cannot move to {target.replace("_", " ").title()}.'})
        if target in {WorkOrder.STATUS_APPROVED, WorkOrder.STATUS_ASSIGNED, WorkOrder.STATUS_VERIFIED, WorkOrder.STATUS_CLOSED} and request.user.role not in APPROVER_ROLES:
            raise PermissionDenied('Only a project manager or admin can verify site work.')
        comments = str(request.data.get('comments', '')).strip()
        if target in {WorkOrder.STATUS_REJECTED, WorkOrder.STATUS_ON_HOLD, WorkOrder.STATUS_CANCELLED} and not comments:
            raise ValidationError({'comments': 'A reason is required for this action.'})
        if target == WorkOrder.STATUS_CLOSED and site_package.status != WorkOrder.STATUS_VERIFIED:
            raise ValidationError({'status': 'Verify the site package before closing it.'})
        if target == WorkOrder.STATUS_COMPLETED:
            if site_package.progress_percent < 100:
                raise ValidationError({'progress_percent': 'Record 100% site progress before marking work complete.'})
            if site_package.tasks.exclude(status=WorkOrderTask.STATUS_COMPLETED).exists():
                raise ValidationError({'tasks': 'Complete every site task before completing the site package.'})
            required = ['materials_reconciled', 'quality_checked', 'safety_checked', 'client_signed_off']
            missing = [field.replace('_', ' ') for field in required if not getattr(site_package, field)]
            if missing:
                raise ValidationError({'closeout': f"Complete the close-out checklist first: {', '.join(missing)}."})
        before = site_package.status
        site_package.status = target
        if target == WorkOrder.STATUS_COMPLETED:
            site_package.actual_completion_date = timezone.localdate()
        site_package.save()
        WorkOrderAuditLog.objects.create(work_order=site_package.work_order, actor=request.user, action='site_status_changed', from_status=before, to_status=target, message=comments, metadata={'site_package': site_package.pk})
        recipients = [site_package.responsible_person, site_package.work_order.requester]
        if site_package.project.manager_id:
            recipients.append(site_package.project.manager)
        for user in {user for user in recipients if user and user.is_active and user.company_id == site_package.work_order.company_id}:
            send_notification(user, Notification.TYPE_SYSTEM, Notification.LEVEL_WARNING if target in {WorkOrder.STATUS_REJECTED, WorkOrder.STATUS_ON_HOLD} else Notification.LEVEL_SUCCESS, f'{site_package.work_order.number} · {site_package.project_site.name}', comments or f'Site work changed to {site_package.get_status_display()}.', f'/work-orders/{site_package.work_order_id}')
        return Response(self.get_serializer(site_package).data)

    @action(detail=True, methods=['post'], url_path='closeout')
    def closeout(self, request, pk=None):
        site_package = self.get_object()
        if request.user.role not in WRITE_ROLES:
            raise PermissionDenied('Your role cannot complete a site close-out checklist.')
        fields = ['materials_reconciled', 'quality_checked', 'safety_checked', 'client_signed_off']
        for field in fields:
            setattr(site_package, field, bool(request.data.get(field)))
        site_package.closeout_notes = str(request.data.get('closeout_notes', '')).strip()
        if not site_package.closeout_notes:
            raise ValidationError({'closeout_notes': 'Summarise the handover, quality result, and any remaining observations.'})
        site_package.save(update_fields=[*fields, 'closeout_notes', 'updated_at'])
        WorkOrderAuditLog.objects.create(work_order=site_package.work_order, actor=request.user, action='site_closeout_checklist_updated', message=site_package.closeout_notes, metadata={'site_package': site_package.pk})
        return Response(self.get_serializer(site_package).data)
