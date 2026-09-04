import type { Paginated } from './types';

export type Money = string;

export type FinanceDashboard = {
  as_of: string;
  base_currency: string | null;
  approved_budgets: Money;
  open_commitments: Money;
  actual_expenditure: Money;
  available_project_balances: Money;
  pending_financial_approvals: number;
  unmatched_invoices: number;
  unpaid_invoices: { count: number; base_amount: Money };
  overdue_invoices: { count: number; base_amount: Money };
  payments_awaiting_approval: { count: number; base_amount: Money };
  outstanding_staff_advances: Money;
  inventory_value: Money;
  project_material_costs: Money;
  cash_and_bank_balances: {
    totals_by_currency: Record<string, Money>;
    accounts: Array<{ cash_account_id: number; code: string; name: string; currency: string; balance: Money }>;
  };
  project_balances: ProjectBalance[];
  site_balances: SiteBalance[];
};

export type SiteBalance = {
  id: number;
  project_code: string;
  project_name: string;
  site_code: string;
  site_name: string;
  work_order_count: number;
  planned_cost: Money;
  committed_cost: Money;
  actual_cost: Money;
  forecast_cost: Money;
  variance: Money;
};

export type ProjectBalance = {
  id: number;
  project_id: number;
  project_code: string;
  project_name: string;
  status: string;
  original_budget: Money;
  approved_revisions: Money;
  revised_budget: Money;
  open_commitments: Money;
  actual_expenditure: Money;
  available_balance: Money;
};

export type BudgetLine = {
  id: number;
  category: number;
  category_code: string;
  category_name: string;
  description: string;
  original_amount: Money;
  revised_budget: Money;
  open_commitments: Money;
  actual_expenditure: Money;
  available_balance: Money;
};

export type ProjectBudget = ProjectBalance & {
  name: string;
  project: number;
  project_name: string;
  project_code: string;
  lines: BudgetLine[];
  submitted_at: string | null;
  approved_at: string | null;
  created_at: string;
};

export type FinancialApproval = {
  id: number;
  purchase_request: number;
  purchase_request_number: string;
  project_name: string;
  project_budget: number;
  budget_line: number;
  requested_amount: Money;
  status: string;
  review_reason: string;
  submitted_at: string | null;
  reviewed_at: string | null;
};

export type Currency = { id: number; code: string; name: string; symbol: string; decimal_places: number; is_active: boolean };
export type TaxCode = { id: number; code: string; name: string; rate_percent: string; description: string; is_active: boolean };
export type CostCentre = { id: number; code: string; name: string; project: number | null; project_name: string; description: string; is_active: boolean };
export type BudgetCategory = { id: number; code: string; name: string; cost_centre: number; cost_centre_name: string; description: string; is_active: boolean };

export type FinanceSettings = {
  id: number;
  base_currency: number;
  base_currency_code: string;
  financial_year_start: string;
  quantity_matching_tolerance: string;
  price_matching_tolerance: string;
  finance_officer_approval_threshold: Money;
  finance_manager_approval_threshold: Money;
  maker_checker_enforced: boolean;
  negative_stock_policy: 'PREVENT' | 'WARN' | 'ALLOW';
  document_retention_years: number;
  require_invoice_attachment: boolean;
  require_payment_attachment: boolean;
};

export type ApprovalMatrixRule = {
  id: number;
  document_type: string;
  stage: string;
  approver_role: string;
  project: number | null;
  budget_category: number | null;
  minimum_amount: Money;
  maximum_amount: Money | null;
  due_hours: number;
  escalation_hours: number;
  is_active: boolean;
};

export type InvoiceItem = {
  id: number;
  purchase_order_item: number | null;
  material: number | null;
  material_name: string | null;
  material_code: string | null;
  description: string;
  quantity: string;
  unit_price: Money;
  tax_amount: Money;
  subtotal: Money;
  total: Money;
};

export type SupplierInvoice = {
  id: number;
  version: number;
  supplier: number;
  supplier_name: string;
  purchase_order: number | null;
  purchase_order_number: string | null;
  project: number | null;
  project_name: string;
  work_order: number | null;
  work_order_number: string | null;
  work_order_site: number | null;
  work_order_site_name: string | null;
  internal_number: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  currency: string;
  exchange_rate: string;
  subtotal: Money;
  discount_amount: Money;
  freight_amount: Money;
  other_charges_amount: Money;
  tax_amount: Money;
  withholding_amount: Money;
  total_amount: Money;
  amount_paid: Money;
  credit_amount: Money;
  balance: Money;
  status: string;
  notes: string;
  rejection_reason: string;
  is_reversed: boolean;
  items: InvoiceItem[];
};

export type InvoiceAttachment = { id: number; invoice: number; original_name: string; content_type: string; size: number; uploaded_by: number; created_at: string; download_url: string };

export type MatchItemResult = {
  id: number;
  material_code: string;
  ordered_quantity: string;
  accepted_quantity: string;
  previously_invoiced_quantity: string;
  current_invoice_quantity: string;
  remaining_invoiceable_quantity: string;
  po_price: Money;
  invoice_price: Money;
  quantity_variance: string;
  price_variance: Money;
  status: string;
  explanation: string;
};

export type MatchRun = { id: number; status: string; explanation: string; exception_reason: string; item_results: MatchItemResult[] };

export type PaymentAllocation = { id: number; invoice: number; invoice_number: string; amount: Money; invoice_balance: Money };
export type Payment = {
  id: number;
  version: number;
  supplier: number;
  supplier_name: string;
  source_account: number;
  source_account_name: string;
  currency: number;
  currency_code: string;
  number: string;
  amount: Money;
  allocated_amount: Money;
  unallocated_amount: Money;
  payment_date: string;
  method: string;
  reference: string;
  voucher_reference: string;
  notes: string;
  status: string;
  rejection_reason: string;
  is_reversed: boolean;
  allocations: PaymentAllocation[];
};
export type PaymentBatch = {
  id: number; number: string; source_account: number; source_account_name: string; currency: number;
  currency_code: string; payment_date: string; status: string; notes: string; total_amount: Money;
  created_by: number; submitted_at: string | null; approved_at: string | null; released_at: string | null;
  cancellation_reason: string; items: Array<{ id: number; payment: number; payment_number: string; supplier_name: string; amount: Money }>;
};
export type MonthEndChecklist = { period: { id: number; name: string; start_date: string; end_date: string }; checks: Array<{ key: string; label: string; count: number; blocking: boolean }>; is_ready: boolean };

export type ExpenseClaim = {
  id: number; number: string; claimant: number; claimant_name: string; project: number | null; project_name: string;
  purpose: string; claim_date: string; currency: number; currency_code: string; total_amount: Money; base_total_amount: Money;
  amount_paid: Money; status: string; rejection_reason: string;
};

export type StaffAdvance = {
  id: number; number: string; staff: number; staff_name: string; project: number | null; project_name: string;
  purpose: string; advance_date: string; due_date: string; currency: number; currency_code: string; amount: Money;
  retired_amount: Money; outstanding_amount: Money; outstanding_base_amount: Money; status: string;
};

export type CashAccount = { id: number; code: string; name: string; account: number; currency: number; currency_code?: string; opening_balance: Money; current_balance?: Money; is_petty_cash?: boolean; is_active: boolean };
export type BankStatementLine = {
  id: number; cash_account: number; cash_account_name: string; cash_account_ledger: number; currency_code: string;
  statement_date: string; reference: string; description: string; amount: Money;
  payment: number | null; payment_number: string; payment_reference: string;
  status: 'UNRECONCILED' | 'MATCHED' | 'IGNORED'; match_notes: string;
  imported_by_name: string; matched_by_name: string | null; matched_at: string | null;
};
export type ExpenseCategory = { id: number; code: string; name: string; category_type: string; expense_account: number; expense_account_name: string; is_overhead: boolean; is_approved: boolean; is_active: boolean };
export type PettyCashTransaction = { id: number; cash_account: number; cash_account_name: string; currency_code: string; transaction_type: string; amount: Money; balance_effect: Money; transaction_date: string; reference: string; reason: string; status: string };

export type Account = { id: number; code: string; name: string; account_type: string; system_key: string; allow_manual_posting: boolean; is_active: boolean };
export type FiscalPeriod = { id: number; name: string; start_date: string; end_date: string; status: string };
export type JournalLine = { id: number; account: number; account_code: string; account_name: string; description: string; debit: Money; credit: Money };
export type Journal = { id: number; number: string; date: string; description: string; source_type: string; source_reference: string; status: string; debit_total?: Money; credit_total?: Money; lines: JournalLine[] };
export type AuditEvent = { id: number; actor_username: string | null; action: string; object_type: string; object_id: string; message: string; metadata: Record<string, unknown>; created_at: string };

export type FinanceReport = Paginated<Record<string, unknown>> & { title: string; filters: Record<string, unknown>; totals: Record<string, Money | number> };
