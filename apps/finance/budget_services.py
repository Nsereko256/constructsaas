from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.procurement.models import PurchaseOrder, PurchaseRequest

from .configuration_services import ensure_finance_settings, record_finance_audit_event
from .models import (
    BudgetApproval,
    BudgetLine,
    BudgetRevision,
    BudgetTransaction,
    BudgetTransfer,
    FinanceSettings,
    ProjectBudget,
)
from .services import base_money, ensure_budget_clearance, money, purchase_request_estimated_total


ZERO = Decimal('0.00')


def _save(instance, **kwargs):
    try:
        instance.save(**kwargs)
    except DjangoValidationError as exc:
        detail = getattr(exc, 'message_dict', None) or {'non_field_errors': exc.messages}
        raise ValidationError(detail) from exc
    except IntegrityError as exc:
        raise ValidationError({'non_field_errors': ['The operation conflicts with an existing budget record.']}) from exc
    return instance


def _sum(queryset):
    return money(queryset.aggregate(total=Sum('amount'))['total'] or ZERO)


def budget_line_summary(line):
    revision_total = _sum(line.revisions.filter(status=BudgetRevision.STATUS_APPROVED))
    transfer_total = _sum(line.transactions.filter(transaction_type__in=[
        BudgetTransaction.TYPE_TRANSFER_IN,
        BudgetTransaction.TYPE_TRANSFER_OUT,
    ]))
    commitments = _sum(line.transactions.filter(transaction_type__in=[
        BudgetTransaction.TYPE_COMMITMENT,
        BudgetTransaction.TYPE_COMMITMENT_RELEASE,
    ]))
    actual = _sum(line.transactions.filter(transaction_type__in=[
        BudgetTransaction.TYPE_ACTUAL,
        BudgetTransaction.TYPE_ACTUAL_REVERSAL,
    ]))
    revised = money(line.original_amount + revision_total + transfer_total)
    return {
        'original_budget': money(line.original_amount),
        'approved_revisions': revision_total,
        'transfer_adjustment': transfer_total,
        'revised_budget': revised,
        'open_commitments': commitments,
        'actual_expenditure': actual,
        'available_balance': money(revised - commitments - actual),
    }


def project_budget_summary(budget):
    original = money(sum((line.original_amount for line in budget.lines.all()), ZERO))
    revisions = _sum(budget.revisions.filter(status=BudgetRevision.STATUS_APPROVED))
    commitments = _sum(budget.transactions.filter(transaction_type__in=[
        BudgetTransaction.TYPE_COMMITMENT,
        BudgetTransaction.TYPE_COMMITMENT_RELEASE,
    ]))
    actual = _sum(budget.transactions.filter(transaction_type__in=[
        BudgetTransaction.TYPE_ACTUAL,
        BudgetTransaction.TYPE_ACTUAL_REVERSAL,
    ]))
    revised = money(original + revisions)
    return {
        'original_budget': original,
        'approved_revisions': revisions,
        'revised_budget': revised,
        'open_commitments': commitments,
        'actual_expenditure': actual,
        'available_balance': money(revised - commitments - actual),
    }


def approved_budget_for_project(project):
    """Return the approved finance budget for a project, if one exists."""
    if not project or not getattr(project, 'pk', None):
        return None
    return ProjectBudget.objects.filter(
        company_id=project.company_id,
        project_id=project.pk,
        status=ProjectBudget.STATUS_APPROVED,
    ).prefetch_related('lines__category', 'revisions', 'transactions').first()


def project_budget_snapshot(project, *, legacy_actual=ZERO):
    """Return the budget figures used by project-facing screens.

    Once a Finance ProjectBudget is approved it is the source of truth. The
    legacy project budget is retained only for projects that have not yet been
    onboarded into the Finance budget workflow.
    """
    budget = approved_budget_for_project(project)
    if budget:
        summary = project_budget_summary(budget)
        return {
            'source': 'finance',
            'budget_id': budget.pk,
            **summary,
        }
    legacy_budget = money(getattr(project, 'budget', ZERO))
    legacy_actual = money(legacy_actual)
    return {
        'source': 'legacy',
        'budget_id': None,
        'original_budget': legacy_budget,
        'approved_revisions': ZERO,
        'revised_budget': legacy_budget,
        'open_commitments': ZERO,
        'actual_expenditure': legacy_actual,
        'available_balance': money(legacy_budget - legacy_actual),
    }


def _settings(company):
    # Companies created before the finance signal was installed (or restored
    # from an older database) may not have a settings row yet.  Approval is a
    # core workflow, so initialize the safe defaults instead of returning a
    # server error from `.get()`.
    settings = ensure_finance_settings(company)
    return FinanceSettings.objects.select_for_update().get(pk=settings.pk)


def _check_maker_checker(settings, maker_id, checker):
    if settings.maker_checker_enforced and maker_id == checker.id:
        raise ValidationError({'non_field_errors': ['Maker-checker policy requires a different reviewing user.']})


def _check_manager_threshold(settings, user, amount):
    threshold = settings.finance_manager_approval_threshold
    if (
        user.role == User.ROLE_FINANCE_MANAGER
        and threshold > ZERO
        and abs(money(amount)) > threshold
    ):
        raise ValidationError({
            'amount': [f'The amount exceeds the Finance Manager approval threshold of {threshold}.'],
        })


def _transaction(*, company, budget, line, transaction_type, amount, user, description, key, **relations):
    existing = BudgetTransaction.objects.filter(company=company, idempotency_key=key).first()
    if existing:
        return existing
    return _save(BudgetTransaction(
        company=company,
        budget=budget,
        budget_line=line,
        transaction_type=transaction_type,
        amount=money(amount),
        description=description,
        idempotency_key=key,
        created_by=user,
        **relations,
    ))


@transaction.atomic
def record_stock_movement_actual(*, movement, user, reversal=False):
    """Record the value of project stock issues in the approved project budget."""
    if not movement.project_id:
        return None
    budget = ProjectBudget.objects.select_for_update().filter(
        company=movement.company,
        project_id=movement.project_id,
        status=ProjectBudget.STATUS_APPROVED,
    ).first()
    if budget is None:
        # Projects still being onboarded to the Finance budget workflow use
        # the legacy project material-cost calculation. Stock issue must not
        # be blocked solely because that migration has not happened yet.
        return None

    line = None
    purchase_request = getattr(movement, 'purchase_request', None)
    approval = getattr(purchase_request, 'budget_approval', None) if purchase_request else None
    candidate = getattr(approval, 'budget_line', None) if approval else None
    if candidate and candidate.budget_id == budget.pk:
        line = candidate
    lines = list(budget.lines.select_related('category').all())
    if line is None:
        line = next((item for item in lines if item.category.code == 'MATERIALS'), None)
    if line is None:
        line = next((item for item in lines if 'material' in item.category.name.lower()), None)
    if line is None and len(lines) == 1:
        line = lines[0]
    if line is None:
        raise ValidationError({'project': ['Add a Materials budget line before issuing project stock.']})

    amount = money(movement.total_cost)
    if reversal:
        amount = -amount
    return _transaction(
        company=movement.company,
        budget=budget,
        line=line,
        transaction_type=BudgetTransaction.TYPE_ACTUAL_REVERSAL if reversal else BudgetTransaction.TYPE_ACTUAL,
        amount=amount,
        user=user,
        description=(
            f'Material return from project: {movement.material.name} ({movement.quantity})'
            if reversal else f'Material issued to project: {movement.material.name} ({movement.quantity})'
        ),
        key=f'stock-movement:{movement.pk}:{"reversal" if reversal else "actual"}',
        stock_movement=movement,
    )


@transaction.atomic
def create_project_budget(*, user, project, name, lines, client_uuid=None):
    if project.company_id != user.company_id:
        raise ValidationError({'project': ['Project must belong to your company.']})
    if not lines:
        raise ValidationError({'lines': ['At least one budget line is required.']})
    budget = _save(ProjectBudget(
        company=user.company,
        project=project,
        name=name,
        client_uuid=client_uuid,
        created_by=user,
    ))
    seen = set()
    for index, values in enumerate(lines):
        category = values['category']
        if category.company_id != user.company_id:
            raise ValidationError({'lines': [{index: {'category': ['Category must belong to your company.']}}]})
        if category.pk in seen:
            raise ValidationError({'lines': [{index: {'category': ['Each category may appear only once.']}}]})
        seen.add(category.pk)
        _save(BudgetLine(
            company=user.company,
            budget=budget,
            category=category,
            description=values.get('description', ''),
            original_amount=money(values['original_amount']),
        ))
    record_finance_audit_event(
        company=user.company, actor=user, action='budget.created', object_type='ProjectBudget',
        object_id=budget.pk, metadata=project_budget_summary(budget),
    )
    return budget


@transaction.atomic
def submit_project_budget(*, budget, user):
    locked = ProjectBudget.objects.select_for_update().prefetch_related('lines').get(
        pk=budget.pk, company=user.company,
    )
    if locked.status != ProjectBudget.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft budgets can be submitted.']})
    if not locked.lines.exists():
        raise ValidationError({'lines': ['At least one budget line is required.']})
    locked.status = ProjectBudget.STATUS_SUBMITTED
    locked.submitted_at = timezone.now()
    _save(locked, update_fields=['status', 'submitted_at', 'updated_at'])
    record_finance_audit_event(
        company=user.company, actor=user, action='budget.submitted', object_type='ProjectBudget',
        object_id=locked.pk, metadata=project_budget_summary(locked),
    )
    from .notification_services import project_budget_approval_required

    transaction.on_commit(lambda: project_budget_approval_required(locked))
    return locked


@transaction.atomic
def approve_project_budget(*, budget, user, comments=''):
    locked = ProjectBudget.objects.select_for_update().prefetch_related('lines').get(
        pk=budget.pk, company=user.company,
    )
    if locked.status != ProjectBudget.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted budgets can be approved.']})
    settings = _settings(user.company)
    _check_maker_checker(settings, locked.created_by_id, user)
    total = project_budget_summary(locked)['revised_budget']
    _check_manager_threshold(settings, user, total)
    locked.status = ProjectBudget.STATUS_APPROVED
    locked.approved_by = user
    locked.approved_at = timezone.now()
    _save(locked, update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    record_finance_audit_event(
        company=user.company, actor=user, action='budget.approved', object_type='ProjectBudget',
        object_id=locked.pk, message=comments, metadata={'amount': total},
    )
    from .notification_services import project_budget_decided

    transaction.on_commit(lambda: project_budget_decided(locked, approved=True, comments=comments))
    return locked


@transaction.atomic
def reject_project_budget(*, budget, user, comments):
    locked = ProjectBudget.objects.select_for_update().get(pk=budget.pk, company=user.company)
    if locked.status != ProjectBudget.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted budgets can be rejected.']})
    comments = comments.strip()
    if not comments:
        raise ValidationError({'comments': ['Rejection comments are required.']})
    settings = _settings(user.company)
    _check_maker_checker(settings, locked.created_by_id, user)
    locked.status = ProjectBudget.STATUS_REJECTED
    _save(locked, update_fields=['status', 'updated_at'])
    record_finance_audit_event(
        company=user.company, actor=user, action='budget.rejected', object_type='ProjectBudget',
        object_id=locked.pk, message=comments,
    )
    from .notification_services import project_budget_decided

    transaction.on_commit(lambda: project_budget_decided(locked, approved=False, comments=comments))
    return locked


@transaction.atomic
def revise_project_budget(*, budget, user, budget_line, amount, comments, override=False):
    locked = ProjectBudget.objects.select_for_update().get(pk=budget.pk, company=user.company)
    line = BudgetLine.objects.select_for_update().get(pk=budget_line.pk, budget=locked, company=user.company)
    if locked.status != ProjectBudget.STATUS_APPROVED:
        raise ValidationError({'status': ['Only approved budgets can be revised.']})
    amount = money(amount)
    if amount == ZERO:
        raise ValidationError({'amount': ['Revision amount cannot be zero.']})
    comments = comments.strip()
    if not comments:
        raise ValidationError({'comments': ['Revision comments are required.']})
    settings = _settings(user.company)
    _check_manager_threshold(settings, user, amount)
    resulting_available = money(budget_line_summary(line)['available_balance'] + amount)
    if resulting_available < ZERO and not override:
        raise ValidationError({'override': ['This revision exhausts the budget line; a manager override is required.']})
    if override and user.role not in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
        raise ValidationError({'override': ['Only a Finance Manager can authorize a budget override.']})
    revision = _save(BudgetRevision(
        company=user.company, budget=locked, budget_line=line, amount=amount,
        comments=comments, approved_by=user,
    ))
    _transaction(
        company=user.company, budget=locked, line=line, transaction_type=BudgetTransaction.TYPE_REVISION,
        amount=amount, user=user, description=comments, key=f'revision:{revision.pk}', revision=revision,
    )
    record_finance_audit_event(
        company=user.company, actor=user, action='budget.revised', object_type='BudgetRevision',
        object_id=revision.pk, message=comments,
        metadata={'budget': locked.pk, 'budget_line': line.pk, 'amount': amount, 'override': override},
    )
    return revision


@transaction.atomic
def transfer_project_budget(*, budget, user, from_line, to_line, amount, comments, override=False):
    locked = ProjectBudget.objects.select_for_update().get(pk=budget.pk, company=user.company)
    lines = BudgetLine.objects.select_for_update().filter(
        budget=locked, company=user.company, pk__in=[from_line.pk, to_line.pk],
    ).in_bulk()
    if len(lines) != 2:
        raise ValidationError({'lines': ['Both transfer lines must belong to this budget.']})
    source = lines[from_line.pk]
    destination = lines[to_line.pk]
    if locked.status != ProjectBudget.STATUS_APPROVED:
        raise ValidationError({'status': ['Only approved budgets can be transferred.']})
    amount = money(amount)
    if amount <= ZERO:
        raise ValidationError({'amount': ['Transfer amount must be greater than zero.']})
    comments = comments.strip()
    if not comments:
        raise ValidationError({'comments': ['Transfer comments are required.']})
    settings = _settings(user.company)
    _check_manager_threshold(settings, user, amount)
    if amount > budget_line_summary(source)['available_balance'] and not override:
        raise ValidationError({'override': ['The source line has insufficient balance; a manager override is required.']})
    if override and user.role not in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
        raise ValidationError({'override': ['Only a Finance Manager can authorize a budget override.']})
    transfer = _save(BudgetTransfer(
        company=user.company, budget=locked, from_line=source, to_line=destination,
        amount=amount, comments=comments, authorized_by=user,
    ))
    _transaction(
        company=user.company, budget=locked, line=source, transaction_type=BudgetTransaction.TYPE_TRANSFER_OUT,
        amount=-amount, user=user, description=comments, key=f'transfer:{transfer.pk}:out', transfer=transfer,
    )
    _transaction(
        company=user.company, budget=locked, line=destination, transaction_type=BudgetTransaction.TYPE_TRANSFER_IN,
        amount=amount, user=user, description=comments, key=f'transfer:{transfer.pk}:in', transfer=transfer,
    )
    record_finance_audit_event(
        company=user.company, actor=user, action='budget.transferred', object_type='BudgetTransfer',
        object_id=transfer.pk, message=comments,
        metadata={'from_line': source.pk, 'to_line': destination.pk, 'amount': amount, 'override': override},
    )
    return transfer


@transaction.atomic
def submit_purchase_request_to_finance(*, purchase_request, user, budget_line=None, comments=''):
    request = PurchaseRequest.objects.select_for_update().prefetch_related('items__material').get(
        pk=purchase_request.pk, company=user.company,
    )
    if request.status not in {PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_PO_CREATED}:
        raise ValidationError({'status': ['Manager approval is required before finance submission.']})
    if request.status == PurchaseRequest.STATUS_PO_CREATED and not request.purchase_orders.exists():
        raise ValidationError({'status': ['A purchase order with supplier pricing is required before finance review.']})
    line = None
    if budget_line is not None:
        line = BudgetLine.objects.select_for_update().select_related('budget').get(
            pk=budget_line.pk, company=user.company,
        )
        if line.budget.status != ProjectBudget.STATUS_APPROVED or line.budget.project_id != request.project_id:
            raise ValidationError({'budget_line': ['Select an approved budget line for the purchase request project.']})
    elif request.project_id and ProjectBudget.objects.filter(
        company=user.company,
        project_id=request.project_id,
        status=ProjectBudget.STATUS_APPROVED,
    ).exists():
        raise ValidationError({'budget_line': ['Select an approved budget line for the purchase request project.']})
    amount = purchase_request_estimated_total(request)
    approval = BudgetApproval.objects.select_for_update().filter(purchase_request=request).first()
    if approval and approval.status in {
        BudgetApproval.STATUS_APPROVED, BudgetApproval.STATUS_REJECTED, BudgetApproval.STATUS_OVERRIDDEN,
    }:
        raise ValidationError({'status': ['This financial review is already final.']})
    if approval is None:
        approval = BudgetApproval(
            company=user.company, purchase_request=request, created_by=user, requested_amount=amount,
        )
    approval.project_budget = line.budget if line else None
    approval.budget_line = line
    approval.requested_amount = amount
    approval.status = BudgetApproval.STATUS_SUBMITTED
    approval.review_reason = comments.strip()
    approval.submitted_at = timezone.now()
    approval.reviewed_by = None
    approval.reviewed_at = None
    _save(approval)
    record_finance_audit_event(
        company=user.company, actor=user, action='purchase_request.finance_submitted',
        object_type='PurchaseRequest', object_id=request.pk, message=comments,
        metadata={
            'approval': approval.pk,
            'budget_line': line.pk if line else None,
            'amount': amount,
            'unbudgeted': line is None,
        },
    )
    from .notification_services import budget_approval_required

    transaction.on_commit(lambda: budget_approval_required(approval))
    return approval


@transaction.atomic
def review_purchase_request_finance(
    *, purchase_request, user, decision, comments='', override=False,
):
    request = PurchaseRequest.objects.select_for_update().get(pk=purchase_request.pk, company=user.company)
    # Do not join nullable budget relations while taking the row lock.  PostgreSQL
    # rejects FOR UPDATE when the query includes an outer join to a nullable side.
    # The related records are fetched separately below only when a budget line
    # is actually attached.
    approval = BudgetApproval.objects.select_for_update().get(
        purchase_request=request, company=user.company,
    )
    allowed = {BudgetApproval.STATUS_SUBMITTED, BudgetApproval.STATUS_HOLD}
    if approval.status not in allowed:
        raise ValidationError({'status': ['Only submitted or held financial reviews can be actioned.']})
    comments = comments.strip()
    if override:
        if user.role not in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
            raise ValidationError({'override': ['Only a Finance Manager can authorize a budget override.']})
        if not comments:
            raise ValidationError({'comments': ['Override comments are required.']})
    if decision in {
        BudgetApproval.STATUS_REJECTED, BudgetApproval.STATUS_RETURNED, BudgetApproval.STATUS_HOLD,
    } and not comments:
        raise ValidationError({'comments': ['Comments are required for this action.']})
    settings = _settings(user.company)
    _check_maker_checker(settings, approval.created_by_id, user)
    _check_manager_threshold(settings, user, approval.requested_amount)
    line = None
    if approval.budget_line_id:
        line = BudgetLine.objects.select_for_update().get(pk=approval.budget_line_id, company=user.company)
    requires_override = line is None or approval.requested_amount > budget_line_summary(line)['available_balance']
    if decision == BudgetApproval.STATUS_APPROVED and requires_override:
        if not override:
            message = (
                'An unbudgeted request requires Finance Manager override.'
                if line is None
                else 'Insufficient budget; Finance Manager override is required.'
            )
            raise ValidationError({'override': [message]})
        decision = BudgetApproval.STATUS_OVERRIDDEN
    approval.status = decision
    approval.review_reason = comments
    if decision == BudgetApproval.STATUS_RETURNED:
        approval.return_reason = comments
    approval.reviewed_by = user
    approval.reviewed_at = timezone.now()
    _save(approval)
    record_finance_audit_event(
        company=user.company, actor=user, action=f'purchase_request.finance_{decision.lower()}',
        object_type='PurchaseRequest', object_id=request.pk, message=comments,
        metadata={'approval': approval.pk, 'amount': approval.requested_amount, 'override': override},
    )
    if decision == BudgetApproval.STATUS_OVERRIDDEN:
        from .notification_services import purchase_order_exceeding_budget

        # Notification delivery is auxiliary.  Keep the approval committed
        # even if a deployment has a broken channel layer or another failure
        # while Django is running commit callbacks.
        transaction.on_commit(lambda: _safe_budget_override_notification(approval), robust=True)
    elif decision == BudgetApproval.STATUS_RETURNED:
        from .notification_services import purchase_request_returned_for_correction

        transaction.on_commit(lambda: purchase_request_returned_for_correction(approval))
    return approval


def _safe_budget_override_notification(approval):
    """Keep optional follow-up notifications from failing a completed approval."""
    try:
        from .notification_services import purchase_order_exceeding_budget

        purchase_order_exceeding_budget(approval)
    except Exception:
        # The approval and its audit record are already committed. Notification
        # delivery is auxiliary and must never turn that successful action into
        # a server error.
        return


def _po_total(po):
    return money(sum((item.quantity * item.unit_price for item in po.items.all()), ZERO))


@transaction.atomic
def recommit_purchase_order_after_amendment(*, purchase_order, user, amendment):
    """Replace the open commitment after a Finance-approved PO amendment.

    The transaction history is retained as a release plus a fresh commitment;
    budget availability is checked before the new commitment is posted.
    """
    po = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk, company=user.company)
    approval = BudgetApproval.objects.select_for_update().filter(
        purchase_request_id=po.purchase_request_id, company=user.company,
    ).select_related('project_budget', 'budget_line').first()
    if not approval or not approval.budget_line_id:
        return po
    budget = ProjectBudget.objects.select_for_update().get(pk=approval.project_budget_id, company=user.company)
    line = BudgetLine.objects.select_for_update().get(pk=approval.budget_line_id, company=user.company)
    open_amount = _sum(BudgetTransaction.objects.filter(
        purchase_order=po,
        transaction_type__in=[BudgetTransaction.TYPE_COMMITMENT, BudgetTransaction.TYPE_COMMITMENT_RELEASE],
    ))
    # Draft/pending POs have not created a commitment yet. Finance may approve
    # their commercial amendment, but the normal PO approval step must perform
    # the first budget check and commitment exactly once.
    if open_amount <= ZERO and po.status in {PurchaseOrder.STATUS_DRAFT, PurchaseOrder.STATUS_PENDING}:
        return po
    new_amount = _po_total(po)
    available_after_release = money(budget_line_summary(line)['available_balance'] + open_amount)
    if new_amount > available_after_release and approval.status != BudgetApproval.STATUS_OVERRIDDEN:
        raise ValidationError({'items': ['The amended purchase order exceeds the available budget balance.']})
    if open_amount:
        _transaction(
            company=user.company, budget=budget, line=line,
            transaction_type=BudgetTransaction.TYPE_COMMITMENT_RELEASE, amount=-open_amount, user=user,
            description=f'Amendment v{amendment.version} releases the prior commitment for {po.number}',
            key=f'purchase-order:{po.pk}:amendment:{amendment.version}:release', purchase_order=po,
        )
    _transaction(
        company=user.company, budget=budget, line=line,
        transaction_type=BudgetTransaction.TYPE_COMMITMENT, amount=new_amount, user=user,
        description=f'Amendment v{amendment.version} commitment for {po.number}',
        key=f'purchase-order:{po.pk}:amendment:{amendment.version}:commitment', purchase_order=po,
    )
    record_finance_audit_event(
        company=user.company, actor=user, action='purchase_order.amendment_committed',
        object_type='PurchaseOrder', object_id=po.pk,
        metadata={'amendment_id': amendment.pk, 'version': amendment.version, 'prior_commitment': open_amount, 'new_commitment': new_amount},
    )
    return po


def ensure_purchase_order_committed(purchase_order):
    approval = BudgetApproval.objects.filter(
        company=purchase_order.company,
        purchase_request_id=purchase_order.purchase_request_id,
        project_budget__isnull=False,
    ).first()
    if not approval:
        return
    if not BudgetTransaction.objects.filter(
        company=purchase_order.company,
        purchase_order=purchase_order,
        transaction_type=BudgetTransaction.TYPE_COMMITMENT,
    ).exists():
        raise ValidationError({
            'status': ['Approve this budget-controlled purchase order before dispatch or receipt.'],
        })


@transaction.atomic
def approve_purchase_order(*, purchase_order, user):
    from apps.procurement.amendments import PurchaseOrderAmendment
    po = PurchaseOrder.objects.select_for_update().prefetch_related('items').get(
        pk=purchase_order.pk, company=user.company,
    )
    if po.status not in {PurchaseOrder.STATUS_DRAFT, PurchaseOrder.STATUS_PENDING}:
        raise ValidationError({'status': ['Only draft or pending purchase orders can be approved.']})
    if not po.purchase_request_id:
        raise ValidationError({
            'purchase_request': ['A finance-approved purchase request is required before approving a purchase order.'],
        })
    if po.amendments.filter(
        amendment_type=PurchaseOrderAmendment.TYPE_PRE_APPROVAL_EDIT,
        status=PurchaseOrderAmendment.STATUS_SUBMITTED,
    ).exists():
        raise ValidationError({'status': ['Finance must confirm the edited PO before it can be approved.']})
    ensure_budget_clearance(po.purchase_request)
    approval = BudgetApproval.objects.select_for_update().filter(
        purchase_request_id=po.purchase_request_id,
        company=user.company,
    ).first()
    if approval and approval.project_budget_id:
        if approval.status not in {BudgetApproval.STATUS_APPROVED, BudgetApproval.STATUS_OVERRIDDEN}:
            raise ValidationError({'purchase_request': ['The linked request has not passed finance approval.']})
        budget = ProjectBudget.objects.select_for_update().get(pk=approval.project_budget_id, company=user.company)
        line = BudgetLine.objects.select_for_update().get(pk=approval.budget_line_id, company=user.company)
        amount = _po_total(po)
        if amount > budget_line_summary(line)['available_balance'] and approval.status != BudgetApproval.STATUS_OVERRIDDEN:
            raise ValidationError({'amount': ['The purchase order exceeds the available budget balance.']})
        _transaction(
            company=user.company, budget=budget, line=line,
            transaction_type=BudgetTransaction.TYPE_COMMITMENT, amount=amount, user=user,
            description=f'Commitment for {po.number}', key=f'purchase-order:{po.pk}:commitment',
            purchase_order=po,
        )
    po.status = PurchaseOrder.STATUS_ORDERED
    po.save(update_fields=['status', 'updated_at'])
    record_finance_audit_event(
        company=user.company, actor=user, action='purchase_order.approved', object_type='PurchaseOrder',
        object_id=po.pk, metadata={'amount': _po_total(po)},
    )
    return po


@transaction.atomic
def cancel_purchase_order(*, purchase_order, user, comments):
    po = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk, company=user.company)
    if po.status in {PurchaseOrder.STATUS_RECEIVED, PurchaseOrder.STATUS_CANCELLED}:
        raise ValidationError({'status': ['Received or cancelled purchase orders cannot be cancelled.']})
    comments = comments.strip()
    if not comments:
        raise ValidationError({'comments': ['Cancellation comments are required.']})
    approval = BudgetApproval.objects.filter(
        purchase_request_id=po.purchase_request_id, company=user.company,
    ).first()
    if approval and approval.budget_line_id:
        budget = ProjectBudget.objects.select_for_update().get(pk=approval.project_budget_id, company=user.company)
        line = BudgetLine.objects.select_for_update().get(pk=approval.budget_line_id, company=user.company)
        open_amount = _sum(BudgetTransaction.objects.filter(
            purchase_order=po,
            transaction_type__in=[BudgetTransaction.TYPE_COMMITMENT, BudgetTransaction.TYPE_COMMITMENT_RELEASE],
        ))
        if open_amount > ZERO:
            _transaction(
                company=user.company, budget=budget, line=line,
                transaction_type=BudgetTransaction.TYPE_COMMITMENT_RELEASE, amount=-open_amount, user=user,
                description=f'Cancel {po.number}: {comments}', key=f'purchase-order:{po.pk}:cancel-release',
                purchase_order=po,
            )
    po.status = PurchaseOrder.STATUS_CANCELLED
    po.save(update_fields=['status', 'updated_at'])
    record_finance_audit_event(
        company=user.company, actor=user, action='purchase_order.cancelled', object_type='PurchaseOrder',
        object_id=po.pk, message=comments,
    )
    return po


@transaction.atomic
def convert_invoice_commitment_to_actual(*, invoice, user):
    po = invoice.purchase_order
    # Direct work-order invoices have no purchase-order commitment to convert.
    if po is None:
        return
    # Do not join nullable budget relations while locking. PostgreSQL rejects
    # FOR UPDATE queries that include nullable-side outer joins.
    approval = BudgetApproval.objects.select_for_update().filter(
        purchase_request_id=po.purchase_request_id, company=invoice.company,
    ).first()
    if not approval or not approval.budget_line_id:
        return
    budget = ProjectBudget.objects.select_for_update().get(pk=approval.project_budget_id, company=invoice.company)
    line = BudgetLine.objects.select_for_update().get(pk=approval.budget_line_id, company=invoice.company)
    if BudgetTransaction.objects.filter(
        company=invoice.company, idempotency_key=f'invoice:{invoice.pk}:actual',
    ).exists():
        return
    open_amount = _sum(BudgetTransaction.objects.filter(
        purchase_order=po,
        transaction_type__in=[BudgetTransaction.TYPE_COMMITMENT, BudgetTransaction.TYPE_COMMITMENT_RELEASE],
    ))
    invoice_base_total = base_money(invoice.total_amount, invoice.exchange_rate)
    release = min(open_amount, invoice_base_total)
    final_available = money(budget_line_summary(line)['available_balance'] + release - invoice_base_total)
    if final_available < ZERO and approval.status != BudgetApproval.STATUS_OVERRIDDEN:
        raise ValidationError({'total_amount': ['Posting this invoice would exceed the approved budget.']})
    if release > ZERO:
        _transaction(
            company=invoice.company, budget=budget, line=line,
            transaction_type=BudgetTransaction.TYPE_COMMITMENT_RELEASE, amount=-release, user=user,
            description=f'Commitment converted by {invoice.internal_number}',
            key=f'invoice:{invoice.pk}:commitment-release', purchase_order=po, supplier_invoice=invoice,
        )
    _transaction(
        company=invoice.company, budget=budget, line=line,
        transaction_type=BudgetTransaction.TYPE_ACTUAL, amount=invoice_base_total, user=user,
        description=f'Actual expenditure from {invoice.internal_number}',
        key=f'invoice:{invoice.pk}:actual', purchase_order=po, supplier_invoice=invoice,
    )
    record_finance_audit_event(
        company=invoice.company, actor=user, action='invoice.budget_posted', object_type='SupplierInvoice',
        object_id=invoice.pk, metadata={
            'commitment_released': release,
            'actual': invoice_base_total,
            'transaction_currency_total': invoice.total_amount,
            'exchange_rate': invoice.exchange_rate,
        },
    )


@transaction.atomic
def reverse_invoice_actual(*, invoice, user):
    actual = BudgetTransaction.objects.select_for_update().filter(
        company=invoice.company, idempotency_key=f'invoice:{invoice.pk}:actual',
    ).first()
    if not actual or BudgetTransaction.objects.filter(
        company=invoice.company, idempotency_key=f'invoice:{invoice.pk}:actual-reversal',
    ).exists():
        return
    budget = ProjectBudget.objects.select_for_update().get(pk=actual.budget_id, company=invoice.company)
    line = BudgetLine.objects.select_for_update().get(pk=actual.budget_line_id, company=invoice.company)
    _transaction(
        company=invoice.company, budget=budget, line=line,
        transaction_type=BudgetTransaction.TYPE_ACTUAL_REVERSAL, amount=-actual.amount, user=user,
        description=f'Reverse actual from {invoice.internal_number}',
        key=f'invoice:{invoice.pk}:actual-reversal', purchase_order=invoice.purchase_order,
        supplier_invoice=invoice,
    )
    released = BudgetTransaction.objects.filter(
        company=invoice.company, idempotency_key=f'invoice:{invoice.pk}:commitment-release',
    ).first()
    if released and invoice.purchase_order.status != PurchaseOrder.STATUS_CANCELLED:
        _transaction(
            company=invoice.company, budget=budget, line=line,
            transaction_type=BudgetTransaction.TYPE_COMMITMENT, amount=-released.amount, user=user,
            description=f'Restore commitment after reversing {invoice.internal_number}',
            key=f'invoice:{invoice.pk}:commitment-restore', purchase_order=invoice.purchase_order,
            supplier_invoice=invoice,
        )
    record_finance_audit_event(
        company=invoice.company, actor=user, action='invoice.budget_reversed', object_type='SupplierInvoice',
        object_id=invoice.pk, metadata={'actual_reversed': actual.amount},
    )


@transaction.atomic
def apply_credit_note_to_actual(*, credit_note, user):
    invoice = credit_note.invoice
    actual = BudgetTransaction.objects.select_for_update().filter(
        company=invoice.company, idempotency_key=f'invoice:{invoice.pk}:actual',
    ).first()
    key = f'credit-note:{credit_note.pk}:actual-reversal'
    if not actual or BudgetTransaction.objects.filter(company=invoice.company, idempotency_key=key).exists():
        return
    budget = ProjectBudget.objects.select_for_update().get(pk=actual.budget_id, company=invoice.company)
    line = BudgetLine.objects.select_for_update().get(pk=actual.budget_line_id, company=invoice.company)
    credit_base_total = base_money(credit_note.total_amount, credit_note.exchange_rate)
    remaining_actual = _sum(BudgetTransaction.objects.filter(
        company=invoice.company,
        supplier_invoice=invoice,
        transaction_type__in=[BudgetTransaction.TYPE_ACTUAL, BudgetTransaction.TYPE_ACTUAL_REVERSAL],
    ))
    credit_base_total = min(credit_base_total, remaining_actual)
    if credit_base_total <= ZERO:
        return
    _transaction(
        company=invoice.company, budget=budget, line=line,
        transaction_type=BudgetTransaction.TYPE_ACTUAL_REVERSAL, amount=-credit_base_total,
        user=user, description=f'Credit note {credit_note.credit_note_number} against {invoice.internal_number}',
        key=key, purchase_order=invoice.purchase_order, supplier_invoice=invoice,
    )
    record_finance_audit_event(
        company=invoice.company, actor=user, action='credit_note.budget_posted',
        object_type='SupplierCreditNote', object_id=credit_note.pk,
        metadata={
            'actual_reversed': credit_base_total,
            'transaction_currency_total': credit_note.total_amount,
            'exchange_rate': credit_note.exchange_rate,
            'invoice_id': invoice.pk,
        },
    )
