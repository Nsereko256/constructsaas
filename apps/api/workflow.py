from django.db.models import F, Q

from apps.accounts.models import User
from apps.finance.models import (
    BudgetApproval,
    ExpenseClaim,
    JournalEntry,
    Payment,
    ProjectBudget,
    SupplierInvoice,
    StaffAdvance,
)
from apps.materials.models import Material
from apps.procurement.models import PurchaseOrder, PurchaseRequest, SupplierClaim
from apps.projects.access import accessible_purchase_orders, accessible_purchase_requests


def _count(queryset):
    return queryset.distinct().count()


def workflow_badges_for_user(user):
    """Return only company-scoped queues that the current role can action."""
    company = user.company
    role = user.role
    requests = accessible_purchase_requests(
        user,
        PurchaseRequest.objects.filter(company=company),
    )
    orders = accessible_purchase_orders(
        user,
        PurchaseOrder.objects.filter(company=company),
    )

    request_count = 0
    if role == User.ROLE_ADMIN:
        request_count = _count(requests.filter(
            Q(status=PurchaseRequest.STATUS_PENDING)
            | Q(status=PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED)
            | Q(status=PurchaseRequest.STATUS_APPROVED, purchase_orders__isnull=True)
        ))
    elif role == User.ROLE_PROJECT_MANAGER:
        # Manager action ends at technical approval. Supplier pricing and
        # Finance review are downstream Procurement/Finance actions.
        request_count = _count(requests.filter(status=PurchaseRequest.STATUS_PENDING))
    elif role == User.ROLE_PROCUREMENT_OFFICER:
        request_count = _count(requests.filter(
            status__in=[PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED],
            purchase_orders__isnull=True,
        ))
    elif role == User.ROLE_FINANCE_OFFICER:
        request_count = _count(requests.filter(
            Q(status=PurchaseRequest.STATUS_PO_CREATED, budget_approval__isnull=True)
            | Q(status=PurchaseRequest.STATUS_PO_CREATED, budget_approval__status=BudgetApproval.STATUS_RETURNED)
        ))
    elif role == User.ROLE_FINANCE_MANAGER:
        request_count = _count(requests.filter(
            budget_approval__status__in=[BudgetApproval.STATUS_SUBMITTED, BudgetApproval.STATUS_HOLD],
        ))
    elif role == User.ROLE_STOREKEEPER:
        request_count = requests.filter(
            status=PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED,
        ).count()

    purchase_order_count = 0
    if role in {User.ROLE_PROCUREMENT_OFFICER, User.ROLE_ADMIN}:
        purchase_order_count = orders.filter(
            status__in=[PurchaseOrder.STATUS_DRAFT, PurchaseOrder.STATUS_PENDING],
        ).count()

    delivery_count = 0
    if role == User.ROLE_STOREKEEPER:
        # Storekeepers act on warehouse receipts only. Direct-to-site
        # deliveries belong to the assigned Site Engineer's receipt queue.
        delivery_count = orders.filter(
            delivery_destination=PurchaseOrder.DELIVERY_WAREHOUSE,
            status__in=[PurchaseOrder.STATUS_ORDERED, PurchaseOrder.STATUS_PARTIAL],
        ).count()
    elif role == User.ROLE_SITE_ENGINEER:
        delivery_count = orders.filter(
            delivery_destination=PurchaseOrder.DELIVERY_SITE,
            status=PurchaseOrder.STATUS_DISPATCH_CONFIRMED,
        ).count()
    elif role == User.ROLE_PROCUREMENT_OFFICER:
        delivery_count = orders.filter(
            delivery_destination=PurchaseOrder.DELIVERY_SITE,
            status__in=[PurchaseOrder.STATUS_ORDERED, PurchaseOrder.STATUS_PARTIAL],
        ).count()
    elif role == User.ROLE_ADMIN:
        delivery_count = _count(orders.filter(
            Q(
                delivery_destination=PurchaseOrder.DELIVERY_WAREHOUSE,
                status__in=[PurchaseOrder.STATUS_ORDERED, PurchaseOrder.STATUS_PARTIAL],
            )
            | Q(
                delivery_destination=PurchaseOrder.DELIVERY_SITE,
                status__in=[
                    PurchaseOrder.STATUS_ORDERED,
                    PurchaseOrder.STATUS_PARTIAL,
                    PurchaseOrder.STATUS_DISPATCH_CONFIRMED,
                ],
            )
        ))

    inventory_count = 0
    if role in {User.ROLE_STOREKEEPER, User.ROLE_ADMIN}:
        inventory_count = Material.objects.for_company(company).with_current_stock().filter(
            is_active=True,
            current_stock_value__lte=F('min_stock_level'),
        ).count()

    budgets = ProjectBudget.objects.filter(company=company)
    budget_count = 0
    if role == User.ROLE_FINANCE_OFFICER:
        budget_count = budgets.filter(status=ProjectBudget.STATUS_DRAFT).count()
    elif role == User.ROLE_FINANCE_MANAGER:
        budget_count = budgets.filter(status=ProjectBudget.STATUS_SUBMITTED).count()
    elif role == User.ROLE_ADMIN:
        budget_count = budgets.filter(
            status__in=[ProjectBudget.STATUS_DRAFT, ProjectBudget.STATUS_SUBMITTED],
        ).count()

    invoices = SupplierInvoice.objects.filter(company=company)
    invoice_count = 0
    if role == User.ROLE_FINANCE_OFFICER:
        invoice_count = invoices.filter(
            status__in=[SupplierInvoice.STATUS_DRAFT, SupplierInvoice.STATUS_SUBMITTED],
        ).count()
    elif role == User.ROLE_FINANCE_MANAGER:
        invoice_count = invoices.filter(status__in=[
            SupplierInvoice.STATUS_MATCHED,
            SupplierInvoice.STATUS_MATCH_EXCEPTION,
            SupplierInvoice.STATUS_VERIFIED,
            SupplierInvoice.STATUS_APPROVED,
        ]).count()
    elif role == User.ROLE_ADMIN:
        invoice_count = invoices.filter(status__in=[
            SupplierInvoice.STATUS_DRAFT,
            SupplierInvoice.STATUS_SUBMITTED,
            SupplierInvoice.STATUS_MATCHED,
            SupplierInvoice.STATUS_MATCH_EXCEPTION,
            SupplierInvoice.STATUS_VERIFIED,
            SupplierInvoice.STATUS_APPROVED,
        ]).count()

    payments = Payment.objects.filter(company=company)
    payment_count = 0
    if role == User.ROLE_FINANCE_OFFICER:
        payment_count = payments.filter(status=Payment.STATUS_DRAFT).count()
    elif role == User.ROLE_FINANCE_MANAGER:
        payment_count = payments.filter(
            status__in=[Payment.STATUS_SUBMITTED, Payment.STATUS_APPROVED],
        ).count()
    elif role == User.ROLE_ADMIN:
        payment_count = payments.filter(
            status__in=[Payment.STATUS_DRAFT, Payment.STATUS_SUBMITTED, Payment.STATUS_APPROVED],
        ).count()

    expenses = ExpenseClaim.objects.filter(company=company)
    advances = StaffAdvance.objects.filter(company=company)
    expense_count = 0
    if role == User.ROLE_FINANCE_OFFICER:
        expense_count = (
            expenses.filter(status=ExpenseClaim.STATUS_DRAFT).count()
            + advances.filter(status=StaffAdvance.STATUS_DRAFT).count()
        )
    elif role == User.ROLE_FINANCE_MANAGER:
        expense_count = (
            expenses.filter(status__in=[
                ExpenseClaim.STATUS_SUBMITTED,
                ExpenseClaim.STATUS_REVIEWED,
                ExpenseClaim.STATUS_APPROVED,
            ]).count()
            + advances.filter(status__in=[
                StaffAdvance.STATUS_SUBMITTED,
                StaffAdvance.STATUS_REVIEWED,
                StaffAdvance.STATUS_APPROVED,
            ]).count()
        )
    elif role == User.ROLE_ADMIN:
        expense_count = (
            expenses.filter(status__in=[
                ExpenseClaim.STATUS_DRAFT,
                ExpenseClaim.STATUS_SUBMITTED,
                ExpenseClaim.STATUS_REVIEWED,
                ExpenseClaim.STATUS_APPROVED,
            ]).count()
            + advances.filter(status__in=[
                StaffAdvance.STATUS_DRAFT,
                StaffAdvance.STATUS_SUBMITTED,
                StaffAdvance.STATUS_REVIEWED,
                StaffAdvance.STATUS_APPROVED,
            ]).count()
        )

    ledger_count = 0
    if role in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
        ledger_count = JournalEntry.objects.filter(
            company=company,
            status=JournalEntry.STATUS_DRAFT,
        ).count()

    claim_count = 0
    active_claims = SupplierClaim.objects.filter(company=company).exclude(status__in=[SupplierClaim.STATUS_RESOLVED, SupplierClaim.STATUS_CANCELLED])
    if role in {User.ROLE_PROCUREMENT_OFFICER, User.ROLE_ADMIN}:
        claim_count = active_claims.count()
    elif role == User.ROLE_SITE_ENGINEER:
        claim_count = active_claims.filter(
            purchase_order__delivery_destination=PurchaseOrder.DELIVERY_SITE,
        ).filter(Q(project__site_engineers=user) | Q(reported_by=user)).distinct().count()
    elif role == User.ROLE_STOREKEEPER:
        claim_count = active_claims.filter(status=SupplierClaim.STATUS_REPLACEMENT_PENDING).count()

    return {
        'requests': request_count,
        'purchase_orders': purchase_order_count,
        'deliveries': delivery_count,
        'inventory': inventory_count,
        'budgets': budget_count,
        'supplier_invoices': invoice_count,
        'payments': payment_count,
        'expenses': expense_count,
        'ledger': ledger_count,
        'supplier_claims': claim_count,
    }
