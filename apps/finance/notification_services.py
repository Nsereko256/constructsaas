from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.helpers import send_notification
from apps.notifications.models import Notification

from .models import FinanceSettings, StaffAdvance, SupplierInvoice


FINANCE_REVIEW_ROLES = {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}
FINANCE_OPERATIONS_ROLES = {
    User.ROLE_FINANCE_OFFICER,
    User.ROLE_FINANCE_MANAGER,
    User.ROLE_ADMIN,
}


def notify_roles(*, company, roles, notification_type, level, title, message, link='', exclude_user_ids=None):
    exclude_user_ids = set(exclude_user_ids or [])
    recipients = User.objects.filter(
        company=company, role__in=roles, is_active=True,
    ).exclude(pk__in=exclude_user_ids)
    return [
        send_notification(user, notification_type, level, title, message, link)
        for user in recipients
    ]


def notify_unique(user, notification_type, level, title, message, link):
    duplicate = Notification.objects.for_company(user.company).filter(
        recipient=user, notification_type=notification_type, link=link, is_read=False,
    ).exists()
    if duplicate:
        return None
    return send_notification(user, notification_type, level, title, message, link)


def budget_approval_required(approval):
    link = f'/api/v1/finance/budget-approvals/{approval.pk}/'
    notifications = notify_roles(
        company=approval.company,
        roles=FINANCE_REVIEW_ROLES,
        notification_type=Notification.TYPE_BUDGET_APPROVAL_REQUIRED,
        level=Notification.LEVEL_WARNING,
        title='Budget approval required',
        message=(
            f'{approval.purchase_request.number} requires budget approval for '
            f'{approval.requested_amount}.'
        ),
        link=link,
    )
    settings = FinanceSettings.objects.filter(company=approval.company).first()
    if settings and settings.finance_manager_approval_threshold > 0:
        if approval.requested_amount >= settings.finance_manager_approval_threshold:
            notifications.extend(notify_roles(
                company=approval.company,
                roles=FINANCE_REVIEW_ROLES,
                notification_type=Notification.TYPE_BUDGET_THRESHOLD_REACHED,
                level=Notification.LEVEL_DANGER,
                title='Finance approval threshold reached',
                message=(
                    f'{approval.purchase_request.number} is {approval.requested_amount}, meeting the '
                    f'Finance Manager threshold of {settings.finance_manager_approval_threshold}.'
                ),
                link=link,
            ))
    return notifications


def project_budget_approval_required(budget):
    return notify_roles(
        company=budget.company,
        roles=FINANCE_REVIEW_ROLES,
        notification_type=Notification.TYPE_BUDGET_APPROVAL_REQUIRED,
        level=Notification.LEVEL_WARNING,
        title='Project budget approval required',
        message=f'{budget.project.code} budget {budget.name} is ready for approval.',
        link=f'/finance/budgets?search={budget.project.code}',
        exclude_user_ids={budget.created_by_id},
    )


def project_budget_decided(budget, *, approved, comments=''):
    """Tell the budget owner what happened so rejected/submitted work can be followed up."""
    decision = 'approved' if approved else 'rejected'
    level = Notification.LEVEL_SUCCESS if approved else Notification.LEVEL_WARNING
    message = f'{budget.project.code} budget {budget.name} was {decision}.'
    if comments:
        message = f'{message} Comments: {comments}'
    return send_notification(
        budget.created_by,
        Notification.TYPE_SYSTEM,
        level,
        f'Project budget {decision}',
        message,
        f'/finance/budgets?search={budget.project.code}',
    )


def purchase_order_exceeding_budget(approval):
    return notify_roles(
        company=approval.company,
        roles=FINANCE_REVIEW_ROLES,
        notification_type=Notification.TYPE_PO_EXCEEDING_BUDGET,
        level=Notification.LEVEL_DANGER,
        title='Budget override authorized',
        message=(
            f'{approval.purchase_request.number} exceeded its available budget and was approved '
            f'with an override for {approval.requested_amount}.'
        ),
        link=f'/api/purchase-requests/{approval.purchase_request_id}/',
    )


def purchase_request_returned_for_correction(approval):
    request = approval.purchase_request
    recipients = [request.requested_by_id]
    if request.project_id and request.project.manager_id:
        recipients.append(request.project.manager_id)
    users = User.objects.filter(company=approval.company, pk__in=recipients, is_active=True)
    return [
        send_notification(
            user, Notification.TYPE_SYSTEM, Notification.LEVEL_WARNING,
            f'Finance correction required: {request.number}',
            f'Finance returned {request.number} for correction. Reason: {approval.return_reason}',
            f'/procurement/requests?search={request.number}',
        )
        for user in users
    ]


def invoice_submitted(invoice):
    return notify_roles(
        company=invoice.company,
        roles=FINANCE_REVIEW_ROLES,
        notification_type=Notification.TYPE_INVOICE_SUBMITTED,
        level=Notification.LEVEL_INFO,
        title='Supplier invoice submitted',
        message=f'{invoice.internal_number} from {invoice.supplier.name} is ready for finance review.',
        link=f'/api/v1/finance/supplier-invoices/{invoice.pk}/',
    )


def invoice_matching_exception(invoice, explanation=''):
    return notify_roles(
        company=invoice.company,
        roles=FINANCE_REVIEW_ROLES,
        notification_type=Notification.TYPE_INVOICE_MATCH_EXCEPTION,
        level=Notification.LEVEL_DANGER,
        title='Invoice matching exception',
        message=f'{invoice.internal_number} has a matching exception. {explanation}'.strip(),
        link=f'/api/v1/finance/supplier-invoices/{invoice.pk}/match-results/',
    )


def payment_awaiting_approval(payment):
    return notify_roles(
        company=payment.company,
        roles=FINANCE_REVIEW_ROLES,
        notification_type=Notification.TYPE_PAYMENT_AWAITING_APPROVAL,
        level=Notification.LEVEL_WARNING,
        title='Payment awaiting approval',
        message=f'Payment {payment.number} for {payment.amount} requires approval.',
        link=f'/api/v1/finance/payments/{payment.pk}/',
        exclude_user_ids={payment.created_by_id},
    )


def payment_decided(payment, approved):
    notification_type = Notification.TYPE_PAYMENT_APPROVED if approved else Notification.TYPE_PAYMENT_REJECTED
    level = Notification.LEVEL_SUCCESS if approved else Notification.LEVEL_DANGER
    decision = 'approved' if approved else 'rejected'
    return send_notification(
        payment.created_by,
        notification_type,
        level,
        f'Payment {decision}',
        f'Payment {payment.number} was {decision}.',
        f'/api/v1/finance/payments/{payment.pk}/',
    )


def valuation_adjusted(movement):
    return notify_roles(
        company=movement.company,
        roles=FINANCE_REVIEW_ROLES,
        notification_type=Notification.TYPE_VALUATION_ADJUSTMENT,
        level=Notification.LEVEL_WARNING,
        title='Inventory valuation adjusted',
        message=(
            f'{movement.material.code} valuation was adjusted by '
            f'{movement.authorized_by.username if movement.authorized_by else "an authorized user"}.'
        ),
        link=f'/api/stock-movements/{movement.pk}/',
    )


def journal_posting_failed(journal, message):
    return notify_roles(
        company=journal.company,
        roles=FINANCE_REVIEW_ROLES,
        notification_type=Notification.TYPE_JOURNAL_POSTING_FAILURE,
        level=Notification.LEVEL_DANGER,
        title='Journal posting failed',
        message=f'Journal {journal.number} could not be posted: {message}',
        link=f'/api/v1/finance/journals/{journal.pk}/',
    )


def check_finance_deadlines_for_company(company, *, as_of=None, due_soon_days=7):
    as_of = as_of or timezone.localdate()
    due_soon_end = as_of + timedelta(days=due_soon_days)
    recipients = list(User.objects.filter(
        company=company, role__in=FINANCE_OPERATIONS_ROLES, is_active=True,
    ))
    created = []
    invoices = SupplierInvoice.objects.for_company(company).filter(
        status__in=[
            SupplierInvoice.STATUS_POSTED,
            SupplierInvoice.STATUS_PARTIALLY_PAID,
        ],
        due_date__isnull=False,
        due_date__lte=due_soon_end,
    )
    for invoice in invoices:
        from .payment_services import invoice_balance

        if invoice_balance(invoice) <= 0:
            continue
        overdue = invoice.due_date < as_of
        notification_type = (
            Notification.TYPE_INVOICE_OVERDUE if overdue else Notification.TYPE_INVOICE_DUE_SOON
        )
        level = Notification.LEVEL_DANGER if overdue else Notification.LEVEL_WARNING
        title = 'Supplier invoice overdue' if overdue else 'Supplier invoice due soon'
        link = f'/api/v1/finance/supplier-invoices/{invoice.pk}/'
        for recipient in recipients:
            notification = notify_unique(
                recipient, notification_type, level, title,
                f'{invoice.internal_number} is due on {invoice.due_date}.', link,
            )
            if notification:
                created.append(notification)

    advances = StaffAdvance.objects.for_company(company).filter(
        status__in=[StaffAdvance.STATUS_PAID, StaffAdvance.STATUS_RETIRED],
        due_date__lt=as_of,
    ).select_related('staff')
    for advance in advances:
        if advance.outstanding_amount <= 0:
            continue
        link = f'/api/v1/finance/staff-advances/{advance.pk}/'
        advance_recipients = recipients + ([advance.staff] if advance.staff not in recipients else [])
        for recipient in advance_recipients:
            notification = notify_unique(
                recipient,
                Notification.TYPE_STAFF_ADVANCE_OVERDUE,
                Notification.LEVEL_DANGER,
                'Staff advance overdue',
                f'{advance.number} for {advance.staff.username} was due on {advance.due_date}.',
                link,
            )
            if notification:
                created.append(notification)
    return created
