from collections import defaultdict
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.procurement.models import GoodsReceivedNote, PurchaseOrder, PurchaseOrderItem, SupplierClaim
from apps.projects.models import Project, ProjectSite
from apps.workorders.models import WorkOrderSite
from apps.warehouse.models import StockMovement
from apps.materials.models import Material

from .models import (
    Account,
    AdvanceRetirement,
    BudgetApproval,
    BudgetLine,
    BudgetRevision,
    BudgetTransaction,
    CashAccount,
    ExpenseClaim,
    FinanceAuditEvent,
    FinanceSettings,
    InvoiceMatchRun,
    JournalEntry,
    JournalLine,
    Payment,
    PaymentAllocation,
    PettyCashTransaction,
    ProjectBudget,
    StaffAdvance,
    SupplierCreditNote,
    SupplierInvoice,
)
from .selectors import (
    pending_expense_claims,
    pending_staff_advances,
    submitted_budget_approvals,
    submitted_payments,
)
from . import budget_services


ZERO = Decimal('0.00')
MONEY_FIELD = DecimalField(max_digits=20, decimal_places=2)


def _money(value):
    return (value or ZERO).quantize(Decimal('0.01'))


def _rate(value):
    return (value or ZERO).quantize(Decimal('0.000001'))


def _date_filter(queryset, field, filters):
    if filters.get('date_from'):
        queryset = queryset.filter(**{f'{field}__gte': filters['date_from']})
    if filters.get('date_to'):
        queryset = queryset.filter(**{f'{field}__lte': filters['date_to']})
    return queryset


def _columns(*items):
    return [{'key': key, 'label': label} for key, label in items]


def _report(title, columns, rows, totals):
    return {'title': title, 'columns': columns, 'rows': rows, 'totals': totals}


def _apply_ordering(report, filters):
    ordering = filters.get('ordering')
    if not ordering:
        return report
    descending = ordering.startswith('-')
    key = ordering.lstrip('-')
    allowed = {column['key'] for column in report['columns']}
    if key in allowed:
        report['rows'].sort(
            key=lambda row: (row.get(key) is None, row.get(key)),
            reverse=descending,
        )
    return report


def _budget_rows(company, filters):
    budgets = ProjectBudget.objects.for_company(company).select_related('project')
    if filters.get('project'):
        budgets = budgets.filter(project_id=filters['project'])
    if filters.get('project_site'):
        budgets = budgets.filter(project__sites__id=filters['project_site'])
    if filters.get('status'):
        budgets = budgets.filter(status=filters['status'].upper())
    budgets = _date_filter(budgets, 'created_at__date', filters)
    budget_ids = list(budgets.values_list('id', flat=True))

    originals = dict(BudgetLine.objects.for_company(company).filter(budget_id__in=budget_ids).values_list(
        'budget_id',
    ).annotate(total=Coalesce(Sum('original_amount'), ZERO, output_field=MONEY_FIELD)))
    revisions = dict(BudgetRevision.objects.for_company(company).filter(
        budget_id__in=budget_ids, status=BudgetRevision.STATUS_APPROVED,
    ).values_list('budget_id').annotate(total=Coalesce(Sum('amount'), ZERO, output_field=MONEY_FIELD)))
    transaction_totals = defaultdict(lambda: defaultdict(lambda: ZERO))
    for item in BudgetTransaction.objects.for_company(company).filter(budget_id__in=budget_ids).values(
        'budget_id', 'transaction_type',
    ).annotate(total=Sum('amount')):
        transaction_totals[item['budget_id']][item['transaction_type']] = item['total'] or ZERO

    rows = []
    for budget in budgets:
        original = _money(originals.get(budget.id))
        revised = _money(original + revisions.get(budget.id, ZERO))
        transactions = transaction_totals[budget.id]
        commitment = _money(
            transactions[BudgetTransaction.TYPE_COMMITMENT]
            + transactions[BudgetTransaction.TYPE_COMMITMENT_RELEASE]
        )
        actual = _money(
            transactions[BudgetTransaction.TYPE_ACTUAL]
            + transactions[BudgetTransaction.TYPE_ACTUAL_REVERSAL]
        )
        rows.append({
            'id': budget.id,
            'url': f'/api/v1/finance/budgets/{budget.id}/',
            'project_id': budget.project_id,
            'project_url': f'/api/projects/{budget.project_id}/',
            'project_code': budget.project.code,
            'project_name': budget.project.name,
            'status': budget.status,
            'original_budget': original,
            'approved_revisions': _money(revisions.get(budget.id)),
            'revised_budget': revised,
            'open_commitments': commitment,
            'actual_expenditure': actual,
            'available_balance': _money(revised - commitment - actual),
        })
    return rows


def _site_balance_rows(company, filters):
    """Compare planned and realized operating costs for each physical site."""
    sites = ProjectSite.objects.filter(project__company=company, is_active=True).select_related('project')
    if filters.get('project'):
        sites = sites.filter(project_id=filters['project'])
    if filters.get('project_site'):
        sites = sites.filter(pk=filters['project_site'])
    rows = []
    for site in sites:
        packages = WorkOrderSite.objects.filter(project_site=site)
        planned = packages.aggregate(total=Sum('estimated_cost'))['total'] or ZERO
        actual = packages.aggregate(total=Sum('actual_cost'))['total'] or ZERO
        issued = StockMovement.objects.filter(work_order_site__project_site=site).aggregate(total=Sum('total_cost'))['total'] or ZERO
        invoiced = SupplierInvoice.objects.filter(
            work_order_site__project_site=site,
            status__in=[SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID],
        ).aggregate(total=Sum('total_amount'))['total'] or ZERO
        committed = PurchaseOrderItem.objects.filter(
            purchase_order__purchase_request__work_order_site__project_site=site,
        ).exclude(purchase_order__status=PurchaseOrder.STATUS_CANCELLED).aggregate(
            total=Sum(F('quantity') * F('unit_price'), output_field=MONEY_FIELD),
        )['total'] or ZERO
        planned = _money(planned)
        actual = _money(actual + issued + invoiced)
        committed = _money(committed)
        forecast = _money(max(actual, committed))
        rows.append({
            'id': site.id, 'project_code': site.project.code, 'project_name': site.project.name,
            'site_code': site.code, 'site_name': site.name, 'work_order_count': packages.count(),
            'planned_cost': planned, 'committed_cost': committed, 'actual_cost': actual,
            'forecast_cost': forecast, 'variance': _money(forecast - planned),
        })
    return rows


def budget_vs_actual(company, filters):
    rows = _budget_rows(company, filters)
    totals = {
        'original_budget': _money(sum((row['original_budget'] for row in rows), ZERO)),
        'revised_budget': _money(sum((row['revised_budget'] for row in rows), ZERO)),
        'open_commitments': _money(sum((row['open_commitments'] for row in rows), ZERO)),
        'actual_expenditure': _money(sum((row['actual_expenditure'] for row in rows), ZERO)),
        'available_balance': _money(sum((row['available_balance'] for row in rows), ZERO)),
    }
    return _apply_ordering(_report('Budget versus actual', _columns(
        ('id', 'Budget ID'), ('project_code', 'Project code'), ('project_name', 'Project'),
        ('status', 'Status'), ('original_budget', 'Original budget'),
        ('approved_revisions', 'Approved revisions'), ('revised_budget', 'Revised budget'),
        ('open_commitments', 'Open commitments'), ('actual_expenditure', 'Actual expenditure'),
        ('available_balance', 'Available balance'), ('url', 'Budget URL'),
        ('project_url', 'Project URL'),
    ), rows, totals), filters)


def project_cost_summary(company, filters):
    projects = Project.objects.filter(company=company).order_by('code')
    if filters.get('project'):
        projects = projects.filter(pk=filters['project'])
    lines = JournalLine.objects.for_company(company).filter(
        entry__status__in=[JournalEntry.STATUS_POSTED, JournalEntry.STATUS_REVERSED],
        account__account_type=Account.TYPE_EXPENSE,
        project__isnull=False,
    )
    lines = _date_filter(lines, 'entry__date', filters)
    costs = {item['project_id']: _money(item['total']) for item in lines.values('project_id').annotate(
        total=Sum(F('debit') - F('credit'), output_field=MONEY_FIELD),
    )}
    rows = []
    for project in projects:
        snapshot = budget_services.project_budget_snapshot(
            project,
            legacy_actual=costs.get(project.id, ZERO),
        )
        rows.append({
            'project_id': project.id,
            'project_url': f'/api/projects/{project.id}/',
            'project_code': project.code,
            'project_name': project.name,
            'budget': _money(snapshot['revised_budget']),
            'actual_cost': costs.get(project.id, ZERO),
            'remaining_budget': _money(snapshot['available_balance']),
            'open_commitments': _money(snapshot['open_commitments']),
            'actual_expenditure': _money(snapshot['actual_expenditure']),
            'budget_source': snapshot['source'],
        })
    return _apply_ordering(_report('Project cost summary', _columns(
        ('project_id', 'Project ID'), ('project_code', 'Project code'), ('project_name', 'Project'),
        ('budget', 'Project budget'), ('actual_cost', 'Actual cost'),
        ('remaining_budget', 'Remaining budget'), ('open_commitments', 'Open commitments'),
        ('actual_expenditure', 'Actual expenditure'), ('budget_source', 'Budget source'),
        ('project_url', 'Project URL'),
    ), rows, {
        'actual_cost': _money(sum((row['actual_cost'] for row in rows), ZERO)),
        'remaining_budget': _money(sum((row['remaining_budget'] for row in rows), ZERO)),
        'open_commitments': _money(sum((row['open_commitments'] for row in rows), ZERO)),
        'actual_expenditure': _money(sum((row['actual_expenditure'] for row in rows), ZERO)),
    }), filters)


def material_cost_by_project(company, filters):
    movements = StockMovement.objects.filter(
        company=company,
        project__isnull=False,
        transaction_type__in=[StockMovement.TRANSACTION_PROJECT_ISSUE, StockMovement.TRANSACTION_PROJECT_RETURN],
    )
    if filters.get('project'):
        movements = movements.filter(project_id=filters['project'])
    if filters.get('warehouse'):
        movements = movements.filter(warehouse_id=filters['warehouse'])
    movements = _date_filter(movements, 'date', filters)
    values = movements.values(
        'project_id', 'project__code', 'project__name', 'material_id', 'material__code', 'material__name',
    ).annotate(
        issued_quantity=Coalesce(Sum(-F('quantity_effect')), ZERO, output_field=MONEY_FIELD),
        material_cost=Coalesce(Sum(-F('value_effect')), ZERO, output_field=MONEY_FIELD),
    ).order_by('project__code', 'material__code')
    rows = [{
        'project_id': row['project_id'], 'project_code': row['project__code'],
        'project_name': row['project__name'], 'project_url': f"/api/projects/{row['project_id']}/",
        'material_id': row['material_id'], 'material_code': row['material__code'],
        'material_name': row['material__name'], 'material_url': f"/api/materials/{row['material_id']}/",
        'net_issued_quantity': row['issued_quantity'], 'material_cost': row['material_cost'],
    } for row in values]
    return _apply_ordering(_report('Material cost by project', _columns(
        ('project_id', 'Project ID'), ('project_code', 'Project code'), ('project_name', 'Project'),
        ('material_id', 'Material ID'), ('material_code', 'Material code'), ('material_name', 'Material'),
        ('net_issued_quantity', 'Net issued quantity'), ('material_cost', 'Material cost'),
        ('project_url', 'Project URL'), ('material_url', 'Material URL'),
    ), rows, {'material_cost': _money(sum((row['material_cost'] for row in rows), ZERO))}), filters)


def inventory_valuation(company, filters):
    movements = StockMovement.objects.filter(company=company)
    if filters.get('warehouse'):
        movements = movements.filter(warehouse_id=filters['warehouse'])
    # A valuation is a balance as at a date, not movement activity within a range.
    if filters.get('date_to'):
        movements = movements.filter(date__lte=filters['date_to'])
    values = movements.values(
        'warehouse_id', 'warehouse__code', 'warehouse__name',
        'material_id', 'material__code', 'material__name',
    ).annotate(
        quantity=Coalesce(Sum('quantity_effect'), ZERO, output_field=MONEY_FIELD),
        stock_value=Coalesce(Sum('value_effect'), ZERO, output_field=MONEY_FIELD),
    ).order_by('warehouse__code', 'material__code')
    rows = []
    for row in values:
        quantity = row['quantity']
        value = row['stock_value']
        rows.append({
            'warehouse_id': row['warehouse_id'], 'warehouse_code': row['warehouse__code'],
            'warehouse_name': row['warehouse__name'],
            'warehouse_url': f"/api/warehouses/{row['warehouse_id']}/",
            'material_id': row['material_id'], 'material_code': row['material__code'],
            'material_name': row['material__name'], 'material_url': f"/api/materials/{row['material_id']}/",
            'quantity': quantity, 'average_rate': _rate(value / quantity) if quantity else ZERO,
            'stock_value': value,
        })
    return _apply_ordering(_report('Inventory valuation', _columns(
        ('warehouse_id', 'Warehouse ID'), ('warehouse_code', 'Warehouse code'),
        ('warehouse_name', 'Warehouse'), ('material_id', 'Material ID'),
        ('material_code', 'Material code'), ('material_name', 'Material'), ('quantity', 'Quantity'),
        ('average_rate', 'Average rate'), ('stock_value', 'Stock value'),
        ('warehouse_url', 'Warehouse URL'), ('material_url', 'Material URL'),
    ), rows, {
        'quantity': _money(sum((row['quantity'] for row in rows), ZERO)),
        'stock_value': _money(sum((row['stock_value'] for row in rows), ZERO)),
    }), filters)


def _invoice_balances(company, filters):
    invoices = SupplierInvoice.objects.for_company(company).select_related('supplier', 'project')
    if filters.get('supplier'):
        invoices = invoices.filter(supplier_id=filters['supplier'])
    if filters.get('project'):
        invoices = invoices.filter(project_id=filters['project'])
    if filters.get('status'):
        invoices = invoices.filter(status=filters['status'].upper())
    invoices = _date_filter(invoices, 'invoice_date', filters)
    ids = list(invoices.values_list('id', flat=True))
    paid = dict(PaymentAllocation.objects.for_company(company).filter(
        invoice_id__in=ids,
        status__in=[PaymentAllocation.STATUS_APPROVED, PaymentAllocation.STATUS_POSTED],
        payment__reversal__isnull=True,
    ).values_list('invoice_id').annotate(total=Sum('amount')))
    credits = dict(SupplierCreditNote.objects.for_company(company).filter(
        invoice_id__in=ids, status=SupplierCreditNote.STATUS_POSTED,
    ).values_list('invoice_id').annotate(total=Sum('total_amount')))
    return invoices, paid, credits


def supplier_statements(company, filters):
    invoices, paid, credits = _invoice_balances(company, filters)
    rows = []
    for invoice in invoices:
        amount_paid = _money(paid.get(invoice.id))
        credit = _money(credits.get(invoice.id))
        balance = max(_money(invoice.total_amount - amount_paid - credit), ZERO)
        base_balance = _money(balance * invoice.exchange_rate)
        rows.append({
            'invoice_id': invoice.id, 'invoice_url': f'/api/v1/finance/supplier-invoices/{invoice.id}/',
            'supplier_id': invoice.supplier_id, 'supplier_name': invoice.supplier.name,
            'supplier_url': f'/api/suppliers/{invoice.supplier_id}/',
            'invoice_number': invoice.invoice_number, 'invoice_date': invoice.invoice_date,
            'due_date': invoice.due_date, 'status': invoice.status, 'currency': invoice.currency,
            'exchange_rate': invoice.exchange_rate,
            'invoice_total': invoice.total_amount, 'amount_paid': amount_paid,
            'credit_notes': credit, 'balance': balance, 'base_balance': base_balance,
            'base_invoice_total': _money(invoice.total_amount * invoice.exchange_rate),
            'base_amount_paid': _money(amount_paid * invoice.exchange_rate),
            'base_credit_notes': _money(credit * invoice.exchange_rate),
        })
    return _apply_ordering(_report('Supplier statements', _columns(
        ('invoice_id', 'Invoice ID'), ('supplier_id', 'Supplier ID'), ('supplier_name', 'Supplier'),
        ('invoice_number', 'Invoice number'), ('invoice_date', 'Invoice date'), ('due_date', 'Due date'),
        ('status', 'Status'), ('currency', 'Currency'), ('exchange_rate', 'Exchange rate'),
        ('invoice_total', 'Invoice total'),
        ('amount_paid', 'Amount paid'), ('credit_notes', 'Credit notes'), ('balance', 'Balance'),
        ('base_invoice_total', 'Base-currency invoice total'),
        ('base_amount_paid', 'Base-currency amount paid'),
        ('base_credit_notes', 'Base-currency credit notes'),
        ('base_balance', 'Base-currency balance'),
        ('invoice_url', 'Invoice URL'), ('supplier_url', 'Supplier URL'),
    ), rows, {
        'base_invoice_total': _money(sum((row['base_invoice_total'] for row in rows), ZERO)),
        'base_amount_paid': _money(sum((row['base_amount_paid'] for row in rows), ZERO)),
        'base_credit_notes': _money(sum((row['base_credit_notes'] for row in rows), ZERO)),
        'base_balance': _money(sum((row['base_balance'] for row in rows), ZERO)),
    }), filters)


def accounts_payable_ageing(company, filters):
    invoices, paid, credits = _invoice_balances(company, filters)
    as_of = filters.get('date_to') or timezone.localdate()
    rows = []
    buckets = defaultdict(lambda: ZERO)
    for invoice in invoices:
        balance = max(_money(invoice.total_amount - paid.get(invoice.id, ZERO) - credits.get(invoice.id, ZERO)), ZERO)
        if not balance:
            continue
        base_balance = _money(balance * invoice.exchange_rate)
        days = max((as_of - (invoice.due_date or invoice.invoice_date)).days, 0)
        bucket = 'current' if days == 0 else '1_30' if days <= 30 else '31_60' if days <= 60 else '61_90' if days <= 90 else 'over_90'
        buckets[bucket] += base_balance
        rows.append({
            'invoice_id': invoice.id, 'invoice_url': f'/api/v1/finance/supplier-invoices/{invoice.id}/',
            'supplier_id': invoice.supplier_id, 'supplier_name': invoice.supplier.name,
            'supplier_url': f'/api/suppliers/{invoice.supplier_id}/',
            'invoice_number': invoice.invoice_number, 'invoice_date': invoice.invoice_date,
            'due_date': invoice.due_date, 'days_overdue': days, 'ageing_bucket': bucket,
            'currency': invoice.currency, 'exchange_rate': invoice.exchange_rate,
            'balance': balance, 'base_balance': base_balance,
        })
    totals = {key: _money(buckets[key]) for key in ('current', '1_30', '31_60', '61_90', 'over_90')}
    totals['base_balance'] = _money(sum(totals.values(), ZERO))
    return _apply_ordering(_report('Accounts payable ageing', _columns(
        ('invoice_id', 'Invoice ID'), ('supplier_id', 'Supplier ID'), ('supplier_name', 'Supplier'),
        ('invoice_number', 'Invoice number'), ('invoice_date', 'Invoice date'), ('due_date', 'Due date'),
        ('days_overdue', 'Days overdue'), ('ageing_bucket', 'Ageing bucket'),
        ('currency', 'Currency'), ('exchange_rate', 'Exchange rate'), ('balance', 'Balance'),
        ('base_balance', 'Base-currency balance'), ('invoice_url', 'Invoice URL'),
        ('supplier_url', 'Supplier URL'),
    ), rows, totals), filters)


def purchase_commitments(company, filters):
    transactions = BudgetTransaction.objects.for_company(company).filter(
        transaction_type__in=[BudgetTransaction.TYPE_COMMITMENT, BudgetTransaction.TYPE_COMMITMENT_RELEASE],
        purchase_order__isnull=False,
    )
    if filters.get('project'):
        transactions = transactions.filter(budget__project_id=filters['project'])
    if filters.get('supplier'):
        transactions = transactions.filter(purchase_order__supplier_id=filters['supplier'])
    transactions = _date_filter(transactions, 'created_at__date', filters)
    values = transactions.values(
        'purchase_order_id', 'purchase_order__number', 'purchase_order__status',
        'purchase_order__supplier_id', 'purchase_order__supplier__name',
        'budget__project_id', 'budget__project__code', 'budget__project__name',
    ).annotate(open_commitment=Sum('amount')).order_by('-purchase_order_id')
    rows = [{
        'purchase_order_id': row['purchase_order_id'],
        'purchase_order_url': f"/api/purchase-orders/{row['purchase_order_id']}/",
        'purchase_order_number': row['purchase_order__number'], 'status': row['purchase_order__status'],
        'supplier_id': row['purchase_order__supplier_id'], 'supplier_name': row['purchase_order__supplier__name'],
        'supplier_url': f"/api/suppliers/{row['purchase_order__supplier_id']}/" if row['purchase_order__supplier_id'] else None,
        'project_id': row['budget__project_id'], 'project_code': row['budget__project__code'],
        'project_name': row['budget__project__name'],
        'project_url': f"/api/projects/{row['budget__project_id']}/",
        'open_commitment': row['open_commitment'],
    } for row in values if row['open_commitment']]
    return _apply_ordering(_report('Purchase commitments', _columns(
        ('purchase_order_id', 'PO ID'), ('purchase_order_number', 'PO number'), ('status', 'Status'),
        ('supplier_id', 'Supplier ID'), ('supplier_name', 'Supplier'), ('project_id', 'Project ID'),
        ('project_code', 'Project code'), ('project_name', 'Project'),
        ('open_commitment', 'Open commitment'), ('purchase_order_url', 'PO URL'),
        ('supplier_url', 'Supplier URL'), ('project_url', 'Project URL'),
    ), rows, {'open_commitment': _money(sum((row['open_commitment'] for row in rows), ZERO))}), filters)


def invoice_matching_exceptions(company, filters):
    runs = InvoiceMatchRun.objects.for_company(company).filter(
        status__in=[InvoiceMatchRun.STATUS_EXCEPTION, InvoiceMatchRun.STATUS_BLOCKED],
    ).select_related('invoice__supplier', 'purchase_order', 'run_by', 'exception_approved_by')
    if filters.get('supplier'):
        runs = runs.filter(invoice__supplier_id=filters['supplier'])
    if filters.get('project'):
        runs = runs.filter(invoice__project_id=filters['project'])
    if filters.get('status'):
        runs = runs.filter(status=filters['status'].upper())
    runs = _date_filter(runs, 'run_at__date', filters)
    rows = [{
        'match_run_id': run.id, 'invoice_id': run.invoice_id,
        'invoice_url': f'/api/v1/finance/supplier-invoices/{run.invoice_id}/',
        'invoice_number': run.invoice.invoice_number, 'supplier_id': run.invoice.supplier_id,
        'supplier_name': run.invoice.supplier.name, 'purchase_order_id': run.purchase_order_id,
        'purchase_order_number': run.purchase_order.number, 'status': run.status,
        'explanation': run.explanation, 'exception_reason': run.exception_reason,
        'exception_approved': run.exception_is_approved, 'run_at': run.run_at,
    } for run in runs]
    return _apply_ordering(_report('Invoice matching exceptions', _columns(
        ('match_run_id', 'Match run ID'), ('invoice_id', 'Invoice ID'), ('invoice_number', 'Invoice number'),
        ('supplier_id', 'Supplier ID'), ('supplier_name', 'Supplier'), ('purchase_order_id', 'PO ID'),
        ('purchase_order_number', 'PO number'), ('status', 'Status'), ('explanation', 'Explanation'),
        ('exception_reason', 'Exception reason'), ('exception_approved', 'Exception approved'),
        ('run_at', 'Run at'), ('invoice_url', 'Invoice URL'),
    ), rows, {'exception_count': len(rows)}), filters)


def payment_register(company, filters):
    payments = Payment.objects.for_company(company).select_related('supplier', 'currency', 'source_account')
    if filters.get('supplier'):
        payments = payments.filter(supplier_id=filters['supplier'])
    if filters.get('account'):
        payments = payments.filter(source_account_id=filters['account'])
    if filters.get('status'):
        payments = payments.filter(status=filters['status'].upper())
    payments = _date_filter(payments, 'payment_date', filters)
    rows = [{
        'payment_id': payment.id, 'payment_url': f'/api/v1/finance/payments/{payment.id}/',
        'number': payment.number, 'payment_date': payment.payment_date, 'status': payment.status,
        'supplier_id': payment.supplier_id, 'supplier_name': payment.supplier.name if payment.supplier else None,
        'supplier_url': f'/api/suppliers/{payment.supplier_id}/' if payment.supplier_id else None,
        'method': payment.method, 'reference': payment.reference,
        'currency': payment.currency.code if payment.currency else None,
        'exchange_rate': payment.exchange_rate, 'amount': payment.amount,
        'base_amount': _money(payment.amount * payment.exchange_rate),
        'source_account_id': payment.source_account_id,
        'source_account_code': payment.source_account.code if payment.source_account else None,
    } for payment in payments]
    return _apply_ordering(_report('Payment register', _columns(
        ('payment_id', 'Payment ID'), ('number', 'Payment number'), ('payment_date', 'Payment date'),
        ('status', 'Status'), ('supplier_id', 'Supplier ID'), ('supplier_name', 'Supplier'),
        ('method', 'Method'), ('reference', 'Reference'), ('currency', 'Currency'),
        ('exchange_rate', 'Exchange rate'), ('amount', 'Amount'), ('base_amount', 'Base amount'),
        ('source_account_id', 'Account ID'), ('source_account_code', 'Account code'),
        ('payment_url', 'Payment URL'), ('supplier_url', 'Supplier URL'),
    ), rows, {'base_amount': _money(sum((row['base_amount'] for row in rows), ZERO))}), filters)


def expense_register(company, filters):
    claims = ExpenseClaim.objects.for_company(company).select_related('claimant', 'project', 'cost_centre', 'currency')
    if filters.get('project'):
        claims = claims.filter(project_id=filters['project'])
    if filters.get('status'):
        claims = claims.filter(status=filters['status'].upper())
    claims = _date_filter(claims, 'claim_date', filters)
    rows = [{
        'expense_claim_id': claim.id, 'expense_claim_url': f'/api/v1/finance/expense-claims/{claim.id}/',
        'number': claim.number, 'claim_date': claim.claim_date, 'status': claim.status,
        'claimant_id': claim.claimant_id, 'claimant': claim.claimant.get_full_name() or claim.claimant.username,
        'project_id': claim.project_id, 'project_code': claim.project.code if claim.project else None,
        'project_url': f'/api/projects/{claim.project_id}/' if claim.project_id else None,
        'cost_centre_id': claim.cost_centre_id, 'currency': claim.currency.code,
        'total_amount': claim.total_amount, 'base_total_amount': claim.base_total_amount,
        'amount_paid': claim.amount_paid,
    } for claim in claims]
    return _apply_ordering(_report('Expense register', _columns(
        ('expense_claim_id', 'Claim ID'), ('number', 'Claim number'), ('claim_date', 'Claim date'),
        ('status', 'Status'), ('claimant_id', 'Claimant ID'), ('claimant', 'Claimant'),
        ('project_id', 'Project ID'), ('project_code', 'Project code'), ('cost_centre_id', 'Cost centre ID'),
        ('currency', 'Currency'), ('total_amount', 'Total amount'), ('base_total_amount', 'Base amount'),
        ('amount_paid', 'Amount paid'), ('expense_claim_url', 'Claim URL'), ('project_url', 'Project URL'),
    ), rows, {
        'base_total_amount': _money(sum((row['base_total_amount'] for row in rows), ZERO)),
        'amount_paid': _money(sum((row['amount_paid'] for row in rows), ZERO)),
    }), filters)


def staff_advances(company, filters):
    advances = StaffAdvance.objects.for_company(company).select_related('staff', 'project', 'currency')
    if filters.get('project'):
        advances = advances.filter(project_id=filters['project'])
    if filters.get('status'):
        advances = advances.filter(status=filters['status'].upper())
    advances = _date_filter(advances, 'advance_date', filters)
    ids = list(advances.values_list('id', flat=True))
    retired = defaultdict(lambda: ZERO)
    for item in AdvanceRetirement.objects.for_company(company).filter(advance_id__in=ids).values(
        'advance_id', 'is_reversal',
    ).annotate(total=Sum('total_retired')):
        retired[item['advance_id']] += -item['total'] if item['is_reversal'] else item['total']
    rows = []
    for advance in advances:
        retired_amount = _money(retired[advance.id])
        outstanding = max(_money(advance.amount - retired_amount), ZERO)
        rows.append({
            'staff_advance_id': advance.id,
            'staff_advance_url': f'/api/v1/finance/staff-advances/{advance.id}/',
            'number': advance.number, 'advance_date': advance.advance_date, 'status': advance.status,
            'staff_id': advance.staff_id, 'staff': advance.staff.get_full_name() or advance.staff.username,
            'project_id': advance.project_id, 'project_code': advance.project.code if advance.project else None,
            'project_url': f'/api/projects/{advance.project_id}/' if advance.project_id else None,
            'currency': advance.currency.code, 'amount': advance.amount,
            'retired_amount': retired_amount, 'outstanding_amount': outstanding,
            'outstanding_base_amount': _money(outstanding * advance.exchange_rate),
        })
    return _apply_ordering(_report('Staff advances', _columns(
        ('staff_advance_id', 'Advance ID'), ('number', 'Advance number'), ('advance_date', 'Advance date'),
        ('status', 'Status'), ('staff_id', 'Staff ID'), ('staff', 'Staff'), ('project_id', 'Project ID'),
        ('project_code', 'Project code'), ('currency', 'Currency'), ('amount', 'Amount'),
        ('retired_amount', 'Retired amount'), ('outstanding_amount', 'Outstanding amount'),
        ('outstanding_base_amount', 'Outstanding base amount'), ('staff_advance_url', 'Advance URL'),
        ('project_url', 'Project URL'),
    ), rows, {
        'amount': _money(sum((row['amount'] for row in rows), ZERO)),
        'outstanding_amount': _money(sum((row['outstanding_amount'] for row in rows), ZERO)),
        'outstanding_base_amount': _money(sum((row['outstanding_base_amount'] for row in rows), ZERO)),
    }), filters)


def general_ledger(company, filters):
    lines = JournalLine.objects.for_company(company).filter(
        entry__status__in=[JournalEntry.STATUS_POSTED, JournalEntry.STATUS_REVERSED],
    ).select_related('entry', 'account', 'project', 'supplier')
    if filters.get('project'):
        lines = lines.filter(project_id=filters['project'])
    if filters.get('supplier'):
        lines = lines.filter(supplier_id=filters['supplier'])
    if filters.get('account'):
        lines = lines.filter(account_id=filters['account'])
    if filters.get('status'):
        lines = lines.filter(entry__status=filters['status'].upper())
    lines = _date_filter(lines, 'entry__date', filters)
    rows = [{
        'journal_line_id': line.id, 'journal_id': line.entry_id,
        'journal_url': f'/api/v1/finance/journals/{line.entry_id}/',
        'journal_number': line.entry.number, 'date': line.entry.date, 'source_type': line.entry.source_type,
        'source_object_id': line.entry.source_object_id, 'account_id': line.account_id,
        'account_code': line.account.code, 'account_name': line.account.name,
        'account_url': f'/api/v1/finance/chart-of-accounts/{line.account_id}/',
        'project_id': line.project_id, 'supplier_id': line.supplier_id,
        'description': line.description or line.entry.description, 'debit': line.debit,
        'credit': line.credit, 'net': _money(line.debit - line.credit),
    } for line in lines]
    return _apply_ordering(_report('General ledger', _columns(
        ('journal_line_id', 'Line ID'), ('journal_id', 'Journal ID'), ('journal_number', 'Journal number'),
        ('date', 'Date'), ('source_type', 'Source type'), ('source_object_id', 'Source ID'),
        ('account_id', 'Account ID'), ('account_code', 'Account code'), ('account_name', 'Account'),
        ('project_id', 'Project ID'), ('supplier_id', 'Supplier ID'), ('description', 'Description'),
        ('debit', 'Debit'), ('credit', 'Credit'), ('net', 'Net'), ('journal_url', 'Journal URL'),
        ('account_url', 'Account URL'),
    ), rows, {
        'debit': _money(sum((row['debit'] for row in rows), ZERO)),
        'credit': _money(sum((row['credit'] for row in rows), ZERO)),
        'net': _money(sum((row['net'] for row in rows), ZERO)),
    }), filters)


def trial_balance(company, filters):
    lines = JournalLine.objects.for_company(company).filter(
        entry__status__in=[JournalEntry.STATUS_POSTED, JournalEntry.STATUS_REVERSED],
    )
    if filters.get('account'):
        lines = lines.filter(account_id=filters['account'])
    if filters.get('project'):
        lines = lines.filter(project_id=filters['project'])
    lines = _date_filter(lines, 'entry__date', filters)
    values = lines.values('account_id', 'account__code', 'account__name', 'account__account_type').annotate(
        debit=Coalesce(Sum('debit'), ZERO, output_field=MONEY_FIELD),
        credit=Coalesce(Sum('credit'), ZERO, output_field=MONEY_FIELD),
    ).order_by('account__code')
    rows = [{
        'account_id': row['account_id'], 'account_code': row['account__code'],
        'account_name': row['account__name'], 'account_type': row['account__account_type'],
        'account_url': f"/api/v1/finance/chart-of-accounts/{row['account_id']}/",
        'debit': row['debit'], 'credit': row['credit'],
        'balance': _money(row['debit'] - row['credit']),
    } for row in values]
    return _apply_ordering(_report('Trial balance', _columns(
        ('account_id', 'Account ID'), ('account_code', 'Account code'), ('account_name', 'Account'),
        ('account_type', 'Account type'), ('debit', 'Debit'), ('credit', 'Credit'),
        ('balance', 'Balance'), ('account_url', 'Account URL'),
    ), rows, {
        'debit': _money(sum((row['debit'] for row in rows), ZERO)),
        'credit': _money(sum((row['credit'] for row in rows), ZERO)),
        'balance': _money(sum((row['balance'] for row in rows), ZERO)),
    }), filters)


def finance_audit_events(company, filters):
    events = FinanceAuditEvent.objects.for_company(company).select_related('actor')
    if filters.get('status'):
        events = events.filter(action__iexact=filters['status'])
    events = _date_filter(events, 'created_at__date', filters)
    rows = [{
        'audit_event_id': event.id, 'action': event.action, 'object_type': event.object_type,
        'object_id': event.object_id, 'actor_id': event.actor_id,
        'actor': (event.actor.get_full_name() or event.actor.username) if event.actor else None,
        'message': event.message, 'metadata': event.metadata, 'correlation_id': event.correlation_id,
        'created_at': event.created_at,
    } for event in events]
    return _apply_ordering(_report('Finance audit events', _columns(
        ('audit_event_id', 'Event ID'), ('action', 'Action'), ('object_type', 'Object type'),
        ('object_id', 'Object ID'), ('actor_id', 'Actor ID'), ('actor', 'Actor'), ('message', 'Message'),
        ('metadata', 'Metadata'), ('correlation_id', 'Correlation ID'), ('created_at', 'Created at'),
    ), rows, {'event_count': len(rows)}), filters)


def project_forecast(company, filters):
    rows = _budget_rows(company, {**filters, 'status': ProjectBudget.STATUS_APPROVED})
    for row in rows:
        row['forecast_to_complete'] = _money(row['actual_expenditure'] + row['open_commitments'])
        row['forecast_variance'] = _money(row['revised_budget'] - row['forecast_to_complete'])
    return _apply_ordering(_report('Project forecast', _columns(
        ('project_code', 'Project code'), ('project_name', 'Project'), ('revised_budget', 'Approved budget'),
        ('open_commitments', 'Commitments'), ('actual_expenditure', 'Actuals'),
        ('forecast_to_complete', 'Forecast to complete'), ('forecast_variance', 'Forecast variance'),
    ), rows, {
        'approved_budget': _money(sum((row['revised_budget'] for row in rows), ZERO)),
        'forecast_to_complete': _money(sum((row['forecast_to_complete'] for row in rows), ZERO)),
        'forecast_variance': _money(sum((row['forecast_variance'] for row in rows), ZERO)),
    }), filters)


def procurement_aging(company, filters):
    today = filters.get('date_to') or timezone.localdate()
    orders = PurchaseOrder.objects.filter(company=company).select_related('supplier', 'project')
    if filters.get('project'):
        orders = orders.filter(project_id=filters['project'])
    if filters.get('supplier'):
        orders = orders.filter(supplier_id=filters['supplier'])
    rows = []
    for po in orders.exclude(status__in=[PurchaseOrder.STATUS_RECEIVED, PurchaseOrder.STATUS_CANCELLED]):
        expected = po.revised_delivery_date or po.supplier_confirmed_delivery_date or po.expected_delivery_date
        days_late = max((today - expected).days, 0) if expected else 0
        rows.append({'purchase_order_id': po.id, 'purchase_order_number': po.number, 'supplier': po.supplier_name,
                     'project': po.project.name if po.project_id else 'Warehouse replenishment', 'status': po.status,
                     'expected_delivery_date': expected, 'days_late': days_late,
                     'at_risk': bool(expected and expected <= today), 'order_value': _money(sum((item.quantity * item.unit_price for item in po.items.all()), ZERO))})
    return _apply_ordering(_report('Procurement aging', _columns(
        ('purchase_order_number', 'PO'), ('supplier', 'Supplier'), ('project', 'Project'), ('status', 'Status'),
        ('expected_delivery_date', 'Expected delivery'), ('days_late', 'Days late'), ('at_risk', 'At risk'), ('order_value', 'Order value'),
    ), rows, {'open_purchase_orders': len(rows), 'overdue_delivery_value': _money(sum((row['order_value'] for row in rows if row['days_late']), ZERO))}), filters)


def inventory_health(company, filters):
    materials = Material.objects.filter(company=company, is_active=True).with_current_stock().with_inventory_value()
    rows = []
    for material in materials:
        stock = _money(material.current_stock_value)
        latest = StockMovement.objects.filter(company=company, material=material).order_by('-date', '-id').values_list('date', flat=True).first()
        rows.append({'material_id': material.id, 'material_code': material.code, 'material_name': material.name,
                     'unit': material.unit, 'stock_on_hand': stock, 'minimum_stock': material.min_stock_level,
                     'stock_value': _money(material.stock_value), 'stockout_risk': stock <= material.min_stock_level,
                     'last_movement_date': latest})
    return _apply_ordering(_report('Inventory health', _columns(
        ('material_code', 'Material code'), ('material_name', 'Material'), ('unit', 'Unit'),
        ('stock_on_hand', 'On hand'), ('minimum_stock', 'Minimum'), ('stockout_risk', 'Stockout risk'),
        ('stock_value', 'Stock value'), ('last_movement_date', 'Last movement'),
    ), rows, {'material_count': len(rows), 'stockout_risk_count': sum(1 for row in rows if row['stockout_risk']), 'stock_value': _money(sum((row['stock_value'] for row in rows), ZERO))}), filters)


def finance_control_pack(company, filters):
    dashboard = finance_dashboard(company, filters)
    rows = [
        {'control': 'Unmatched invoices', 'count': dashboard['unmatched_invoices'], 'amount': ZERO},
        {'control': 'Overdue payables', 'count': dashboard['overdue_invoices']['count'], 'amount': dashboard['overdue_invoices']['base_amount']},
        {'control': 'Payments awaiting approval', 'count': dashboard['payments_awaiting_approval']['count'], 'amount': dashboard['payments_awaiting_approval']['base_amount']},
    ]
    return _report('Finance control pack', _columns(('control', 'Control'), ('count', 'Count'), ('amount', 'Base-currency amount')), rows, {'controls_requiring_attention': sum(1 for row in rows if row['count'])})


def supplier_performance(company, filters):
    orders = PurchaseOrder.objects.filter(company=company, supplier__isnull=False).select_related('supplier')
    rows = []
    for supplier_id in orders.values_list('supplier_id', flat=True).distinct():
        supplier_orders = orders.filter(supplier_id=supplier_id)
        supplier = supplier_orders.first().supplier
        delivered = supplier_orders.filter(status=PurchaseOrder.STATUS_RECEIVED).count()
        claims = SupplierClaim.objects.filter(company=company, supplier_id=supplier_id)
        rows.append({'supplier_id': supplier_id, 'supplier_name': supplier.name, 'purchase_orders': supplier_orders.count(),
                     'received_orders': delivered, 'on_time_rate': _rate(Decimal(delivered * 100) / max(supplier_orders.count(), 1)),
                     'open_claims': claims.exclude(status__in=[SupplierClaim.STATUS_RESOLVED, SupplierClaim.STATUS_CANCELLED]).count(),
                     'rejection_claims': claims.count()})
    return _apply_ordering(_report('Supplier performance', _columns(
        ('supplier_name', 'Supplier'), ('purchase_orders', 'Purchase orders'), ('received_orders', 'Received'),
        ('on_time_rate', 'Delivery completion rate %'), ('open_claims', 'Open claims'), ('rejection_claims', 'Total claims'),
    ), rows, {'supplier_count': len(rows), 'open_claims': sum(row['open_claims'] for row in rows)}), filters)


REPORTS = {
    'budget-vs-actual': budget_vs_actual,
    'project-cost-summary': project_cost_summary,
    'material-cost-by-project': material_cost_by_project,
    'inventory-valuation': inventory_valuation,
    'supplier-statements': supplier_statements,
    'accounts-payable-ageing': accounts_payable_ageing,
    'purchase-commitments': purchase_commitments,
    'invoice-matching-exceptions': invoice_matching_exceptions,
    'payment-register': payment_register,
    'expense-register': expense_register,
    'staff-advances': staff_advances,
    'general-ledger': general_ledger,
    'trial-balance': trial_balance,
    'finance-audit-events': finance_audit_events,
    'project-forecast': project_forecast,
    'procurement-aging': procurement_aging,
    'inventory-health': inventory_health,
    'finance-control-pack': finance_control_pack,
    'supplier-performance': supplier_performance,
}


def build_report(slug, company, filters):
    return REPORTS[slug](company, filters)


def finance_dashboard(company, filters):
    base_currency = FinanceSettings.objects.for_company(company).values_list(
        'base_currency__code', flat=True,
    ).first()
    budgets = _budget_rows(company, {**filters, 'status': ProjectBudget.STATUS_APPROVED})
    approved_budgets = _money(sum((row['revised_budget'] for row in budgets), ZERO))
    open_commitments = _money(sum((row['open_commitments'] for row in budgets), ZERO))
    actual_expenditure = _money(sum((row['actual_expenditure'] for row in budgets), ZERO))

    invoice_filters = {key: value for key, value in filters.items() if key in {'date_from', 'date_to', 'project', 'supplier'}}
    invoices, paid, credits = _invoice_balances(company, invoice_filters)
    today = timezone.localdate()
    unpaid = overdue = ZERO
    unpaid_count = overdue_count = 0
    for invoice in invoices:
        balance = max(_money(invoice.total_amount - paid.get(invoice.id, ZERO) - credits.get(invoice.id, ZERO)), ZERO)
        if balance:
            base_balance = _money(balance * invoice.exchange_rate)
            unpaid += base_balance
            unpaid_count += 1
            if invoice.due_date and invoice.due_date < today:
                overdue += base_balance
                overdue_count += 1

    unmatched_statuses = [SupplierInvoice.STATUS_SUBMITTED, SupplierInvoice.STATUS_MATCH_EXCEPTION]
    unmatched = invoices.filter(status__in=unmatched_statuses).count()
    pending_approvals = (
        submitted_budget_approvals(company).count()
        + invoices.filter(status__in=[SupplierInvoice.STATUS_SUBMITTED, SupplierInvoice.STATUS_MATCH_EXCEPTION]).count()
        + submitted_payments(company).count()
        + pending_expense_claims(company).count()
        + pending_staff_advances(company).count()
    )
    payment_qs = submitted_payments(company)
    payment_qs = _date_filter(payment_qs, 'payment_date', filters)
    if filters.get('supplier'):
        payment_qs = payment_qs.filter(supplier_id=filters['supplier'])

    advance_report = staff_advances(company, {
        key: value for key, value in filters.items() if key in {'date_from', 'date_to', 'project'}
    })
    outstanding_advances = sum((row['outstanding_base_amount'] for row in advance_report['rows']), ZERO)
    valuation = inventory_valuation(company, {
        key: value for key, value in filters.items() if key in {'date_from', 'date_to', 'warehouse'}
    })
    material_cost = material_cost_by_project(company, {
        key: value for key, value in filters.items() if key in {'date_from', 'date_to', 'project', 'warehouse'}
    })

    cash_accounts = CashAccount.objects.for_company(company).filter(is_active=True).select_related('currency')
    if filters.get('account'):
        cash_accounts = cash_accounts.filter(account_id=filters['account'])
    effects = dict(PettyCashTransaction.objects.for_company(company).filter(
        cash_account_id__in=cash_accounts.values('id'),
    ).values_list('cash_account_id').annotate(total=Sum('balance_effect')))
    cash_rows = [{
        'cash_account_id': account.id, 'cash_account_url': f'/api/v1/finance/cash-accounts/{account.id}/',
        'code': account.code, 'name': account.name, 'currency': account.currency.code,
        'balance': _money(account.opening_balance + effects.get(account.id, ZERO)),
    } for account in cash_accounts]
    cash_by_currency = defaultdict(lambda: ZERO)
    for row in cash_rows:
        cash_by_currency[row['currency']] += row['balance']

    payment_base_amount = ExpressionWrapper(
        F('amount') * F('exchange_rate'), output_field=MONEY_FIELD,
    )

    return {
        'as_of': filters.get('date_to') or today,
        'base_currency': base_currency,
        'approved_budgets': approved_budgets,
        'open_commitments': open_commitments,
        'actual_expenditure': actual_expenditure,
        'available_project_balances': _money(sum((row['available_balance'] for row in budgets), ZERO)),
        'pending_financial_approvals': pending_approvals,
        'unmatched_invoices': unmatched,
        'unpaid_invoices': {'count': unpaid_count, 'base_amount': _money(unpaid)},
        'overdue_invoices': {'count': overdue_count, 'base_amount': _money(overdue)},
        'payments_awaiting_approval': {
            'count': payment_qs.count(),
            'base_amount': _money(payment_qs.aggregate(total=Sum(payment_base_amount))['total']),
        },
        'outstanding_staff_advances': _money(outstanding_advances),
        'inventory_value': valuation['totals']['stock_value'],
        'project_material_costs': material_cost['totals']['material_cost'],
        'cash_and_bank_balances': {
            'totals_by_currency': {
                currency: _money(balance) for currency, balance in sorted(cash_by_currency.items())
            },
            'accounts': cash_rows,
        },
        'project_balances': budgets,
        'site_balances': _site_balance_rows(company, filters),
    }
