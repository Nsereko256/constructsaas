from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.accounts.models import User

from .models import ApprovalMatrixRule, FinanceSettings


ZERO = Decimal('0')


def matching_roles(*, company, document_type, amount, project=None, budget_category=None):
    """Return configured approver roles, or None when legacy defaults apply."""
    amount = Decimal(amount or ZERO)
    rules = ApprovalMatrixRule.objects.filter(
        company=company, document_type=document_type, stage=ApprovalMatrixRule.STAGE_FINAL,
        is_active=True, minimum_amount__lte=amount,
    ).filter(Q(maximum_amount__isnull=True) | Q(maximum_amount__gte=amount))
    if project is not None:
        rules = rules.filter(Q(project__isnull=True) | Q(project=project))
    if budget_category is not None:
        rules = rules.filter(Q(budget_category__isnull=True) | Q(budget_category=budget_category))
    if not rules.exists():
        return None
    return set(rules.values_list('approver_role', flat=True))


def require_approver(*, user, company, document_type, amount, project=None, budget_category=None):
    """Enforce the configured matrix, with threshold fallback for old tenants."""
    roles = matching_roles(
        company=company, document_type=document_type, amount=amount,
        project=project, budget_category=budget_category,
    )
    if roles is not None:
        if user.role not in roles and user.role != User.ROLE_ADMIN:
            raise ValidationError({'approver': ['This approval is routed to the configured approval role.']})
        return

    settings = FinanceSettings.objects.get(company=company)
    amount = Decimal(amount or ZERO)
    if (
        user.role == User.ROLE_FINANCE_OFFICER
        and settings.finance_officer_approval_threshold > ZERO
        and amount > settings.finance_officer_approval_threshold
    ):
        raise ValidationError({
            'approver': [
                f'This amount exceeds the Finance Officer approval threshold of '
                f'{settings.finance_officer_approval_threshold}; Finance Manager approval is required.'
            ]
        })
    if (
        user.role == User.ROLE_FINANCE_MANAGER
        and settings.finance_manager_approval_threshold > ZERO
        and amount > settings.finance_manager_approval_threshold
    ):
        raise ValidationError({
            'approver': [
                f'This amount exceeds the Finance Manager approval threshold of '
                f'{settings.finance_manager_approval_threshold}; Admin approval is required.'
            ]
        })
