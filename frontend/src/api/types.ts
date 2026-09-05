export type Role =
  | 'site_engineer'
  | 'storekeeper'
  | 'project_manager'
  | 'procurement_officer'
  | 'finance_officer'
  | 'finance_manager'
  | 'finance_viewer'
  | 'admin';

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type ApiErrorPayload = Record<string, unknown> | { detail?: string };

export type WorkflowBadges = {
  requests: number;
  purchase_orders: number;
  deliveries: number;
  inventory: number;
  budgets: number;
  supplier_invoices: number;
  payments: number;
  expenses: number;
  ledger: number;
  supplier_claims: number;
  work_orders?: number;
};

export type WorkOrderTask = { id: number; title: string; description: string; assignee: number | null; assignee_name: string; contractor: number | null; contractor_name: string; priority: string; planned_start_date: string | null; due_date: string | null; planned_hours: string; dependency: number | null; blocker: string; completion_notes: string; status: string; completion_percent: number; completed_at: string | null };
export type WorkOrderAttachment = { id: number; file: string; name: string; uploaded_by: number; uploaded_by_name: string; created_at: string };
export type WorkOrderAuditLog = { id: number; actor: number | null; actor_name: string; action: string; from_status: string; to_status: string; message: string; metadata: Record<string, unknown>; created_at: string };
export type WorkOrderInvoice = { id: number; internal_number: string; invoice_number: string; supplier__name: string; total_amount: string; currency: string; status: string };
export type WorkOrderInvoiceRecord = { id: number; work_order: string; site: string; internal_number: string; invoice_number: string; supplier: string; total_amount: string; currency: string; status: string; due_date: string | null };
export type WorkOrderChange = { id: number; work_order: number; requested_by: number; requested_by_name: string; reason: string; proposed_scope: string; proposed_due_date: string | null; proposed_estimated_cost: string | null; proposed_contractor: number | null; proposed_contractor_name: string; status: string; reviewed_by: number | null; reviewed_by_name: string; review_notes: string; reviewed_at: string | null; created_at: string };
export type WorkOrderSite = { id: number; work_order: number; project: number; project_name: string; project_site: number | null; project_site_name: string; site: number | null; site_name: string; title: string; description: string; responsible_person: number | null; responsible_person_name: string; contractor: number | null; contractor_name: string; estimated_start_date: string | null; due_date: string | null; revised_due_date: string | null; estimated_cost: string; actual_cost: string; material_cost: string; invoice_cost: string; total_actual_cost: string; committed_cost: string; forecast_cost: string; remaining_estimated_budget: string; cost_variance: string; progress_percent: number; task_progress_percent: number; closeout_completion_percent: number; progress_notes: string; progress_updated_at: string | null; materials_reconciled: boolean; quality_checked: boolean; safety_checked: boolean; client_signed_off: boolean; closeout_notes: string; hold_owner: number | null; hold_recovery_date: string | null; status: string; status_display: string; notes: string; tasks: WorkOrderTask[]; material_requests: Array<{ id: number; number: string; status: string; title: string }>; invoices: WorkOrderInvoice[] };
export type WorkOrder = { id: number; number: string; project: number | null; project_name: string; site: number | null; site_name: string; title: string; description: string; work_category: string; priority: string; priority_display: string; requester: number; requester_name: string; responsible_person: number | null; responsible_person_name: string; responsible_team: number[]; contractor: number | null; contractor_name: string; estimated_start_date: string | null; due_date: string | null; revised_due_date: string | null; actual_completion_date: string | null; estimated_cost: string; approved_cost: string; actual_cost: string; actual_material_cost: string; scope_version: number; assignment_status: string; assignment_response: string; assignment_responded_at: string | null; finance_reviewed_by: number | null; finance_reviewed_at: string | null; finance_review_notes: string; is_emergency: boolean; emergency_reason: string; emergency_spend_cap: string; status: string; status_display: string; notes: string; rejection_reason: string; hold_reason: string; hold_owner: number | null; hold_recovery_date: string | null; is_overdue: boolean; material_requests: Array<{ id: number; number: string; status: string; title: string }>; invoices: WorkOrderInvoice[]; changes: WorkOrderChange[]; site_packages: WorkOrderSite[]; tasks: WorkOrderTask[]; attachments: WorkOrderAttachment[]; audit_logs: WorkOrderAuditLog[]; created_at: string; updated_at: string };
export type WorkOrderMetrics = { open: number; in_progress: number; overdue: number; completed: number; estimated_cost: string; actual_cost: string };

export type SupplierClaim = {
  id: number;
  purchase_order: number;
  purchase_order_number: string;
  supplier_name: string | null;
  project_name: string | null;
  material_name: string;
  material_code: string;
  purchase_order_item: number;
  replacement_quantity: string;
  replacement_grn_item: number | null;
  replacement_grn_number: string | null;
  grn_number: string;
  reported_by_name: string;
  assigned_to: number | null;
  assigned_to_name: string | null;
  status: string;
  status_display: string;
  due_date: string | null;
  supplier_reference: string;
  notes: string;
  resolution_notes: string;
  created_at: string;
};

export type Category = {
  id: number;
  company: number;
  name: string;
  description: string;
  created_at: string;
};

export type User = {
  id: number;
  username: string;
  full_name?: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  role: Role;
  role_display: string;
  company: number;
  company_name: string;
  is_active: boolean;
};

export type Material = {
  id: number;
  category: number;
  category_name: string;
  name: string;
  code: string;
  unit: string;
  unit_display: string;
  unit_price: string;
  min_stock_level: string;
  current_stock: string;
  stock_value: string;
  is_low_stock: boolean;
  description: string;
  is_active: boolean;
};

export type Project = {
  id: number;
  name: string;
  code: string;
  client: string;
  location: string;
  description: string;
  budget: string;
  status: string;
  status_display: string;
  manager: number | null;
  manager_name: string;
  site_engineers: number[];
  site_engineer_names: string[];
  total_material_cost: string;
  remaining_budget: string;
  budget_source: 'finance' | 'legacy';
  budget_revised: string;
  budget_commitments: string;
  budget_actual_expenditure: string;
  budget_available_balance: string;
  site_total: number;
  closed_site_total: number;
  site_closure_percent: number;
  goal_total: number;
  goal_completion_percent: number;
  progress_percent: number;
  progress_basis: 'sites' | 'goals';
  start_date: string | null;
  end_date: string | null;
  is_active: boolean;
};
export type ProjectSite = { id: number; project: number; project_name: string; name: string; code: string; location: string; description: string; manager: number | null; manager_name: string; site_engineers: number[]; engineer_names: string[]; status: string; closed_at: string | null; closed_by: number | null; is_active: boolean };
export type ProjectGoal = { id: number; project: number; project_name: string; site: number | null; site_name: string; title: string; description: string; weight: string; completion_percent: number; status: string; status_display: string; due_date: string | null; completed_at: string | null; completed_by: number | null; completed_by_name: string };

export type Supplier = {
  id: number;
  name: string;
  contact_person: string;
  phone: string;
  email: string;
  address: string;
  rating: number;
  is_contractor: boolean;
  contractor_specialty: string;
  notes: string;
  is_active: boolean;
};

export type StockMovement = {
  id: number;
  material: number;
  material_name: string;
  project: number | null;
  project_name: string | null;
  movement_type: 'IN' | 'OUT' | 'ADJUST_IN' | 'ADJUST_OUT';
  movement_type_display: string;
  source: string;
  source_display: string;
  quantity: string;
  unit_price: string;
  date: string;
  notes: string;
  created_by_username: string;
  purchase_order: number | null;
  purchase_order_number: string | null;
};

export type Warehouse = { id: number; name: string; code: string; location: string; project: number | null; project_name: string | null; is_default: boolean; is_active: boolean };
export type BinLocation = { id: number; warehouse: number; warehouse_name: string; code: string; description: string; is_active: boolean };
export type SiteTransfer = { id: number; project: number; project_name: string; material: number; material_name: string; source_warehouse: number; source_warehouse_name: string; destination_store: number; destination_store_name: string; quantity: string; status: 'DISPATCHED' | 'ACKNOWLEDGED'; reason: string; dispatched_by: number; dispatched_at: string; acknowledged_by: number | null; acknowledged_at: string | null; outbound_movement: number; inbound_movement: number | null };
export type ProjectStaffAssignment = { id: number; project: number; project_name: string; user: number; username: string; user_name: string; role: 'MANAGER' | 'ENGINEER' | 'SITE_CONTACT'; is_primary_contact: boolean; allocation_percent: string; start_date: string | null; end_date: string | null; is_active: boolean };
export type ApprovalDelegation = { id: number; delegator: number; delegator_name: string; delegate: number; delegate_name: string; project: number | null; project_name: string | null; effective_from: string; effective_to: string; reason: string; is_active: boolean; revoked_at: string | null };

export type PurchaseRequestItem = {
  id: number;
  material: number;
  material_name: string;
  material_code: string;
  unit: string;
  unit_price: string;
  current_stock: string;
  warehouse_available: string;
  quantity: string;
  issued_quantity: string;
  outstanding_quantity: string;
  estimated_cost: string;
  notes: string;
};

export type PurchaseRequest = {
  id: number;
  project: number | null;
  project_name: string | null;
  number: string;
  title: string;
  priority: 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT';
  priority_display: string;
  status: string;
  status_display: string;
  justification: string;
  requested_by: number;
  requested_by_username: string;
  technical_approved_by_name: string;
  manager_approved_by_name: string;
  rejection_reason: string;
  technical_return_reason: string;
  total_estimated_cost: string;
  has_purchase_order: boolean;
  can_request_stock_issue: boolean;
  can_approve_stock_issue: boolean;
  can_fulfill_from_stock: boolean;
  can_issue_from_stock: boolean;
  can_create_purchase_order: boolean;
  stock_issue_blockers: string[];
  next_action_message: string;
  finance_approval_id: number | null;
  finance_status: string;
  finance_status_display: string;
  finance_review_reason: string;
  finance_return_reason: string;
  finance_budget_line: number | null;
  can_submit_finance: boolean;
  can_correct_finance_return: boolean;
  can_correct_return: boolean;
  items: PurchaseRequestItem[];
  created_at: string;
  updated_at?: string;
};

export type PurchaseOrder = {
  id: number;
  purchase_request: number | null;
  purchase_request_number: string | null;
  project: number | null;
  project_name: string | null;
  number: string;
  supplier: number | null;
  supplier_name: string;
  delivery_destination: 'WAREHOUSE' | 'SITE';
  delivery_destination_display: string;
  status: string;
  status_display: string;
  expected_delivery_date: string | null;
  supplier_confirmed_delivery_date: string | null;
  revised_delivery_date: string | null;
  delivery_revision_reason: string;
  delivery_follow_up_owner: number | null;
  delivery_follow_up_owner_name: string | null;
  is_overdue: boolean;
  notes: string;
  dispatch_confirmed_by_username: string | null;
  dispatch_confirmed_at: string | null;
  received_by_username: string | null;
  received_at: string | null;
  total_cost: string;
  pending_preapproval_edit: {
    id: number;
    version: number;
    changed_fields: string[];
    original_values: Record<string, unknown>;
    proposed_values: Record<string, unknown>;
    submitted_by: number;
    submitted_by_username: string;
    created_at: string;
  } | null;
  items: Array<{
    id: number;
    material: number;
    material_name: string;
    quantity: string;
    unit_price: string;
    line_total: string;
  }>;
};

export type PurchaseOrderAmendment = {
  id: number;
  version: number;
  amendment_type: 'CONTROLLED' | 'PRE_APPROVAL_EDIT';
  reason: string;
  original_values: Record<string, unknown>;
  proposed_values: Record<string, unknown>;
  status: 'SUBMITTED' | 'APPROVED' | 'REJECTED';
  submitted_by: number;
  decided_by: number | null;
  decision_reason: string;
  created_at: string;
  decided_at: string | null;
  budget_impact: {
    current_po_total: string;
    proposed_po_total: string;
    change_amount: string;
    has_budget_line: boolean;
    budget_line_name?: string;
    available_before?: string;
    current_po_commitment?: string;
    projected_available_after?: string;
    budget_override?: boolean;
  };
};

export type GoodsReceivedNote = {
  id: number;
  purchase_order: number;
  purchase_order_number: string;
  number: string;
  receipt_date: string;
  status: string;
  notes: string;
  received_by: number | null;
  received_by_username: string | null;
  received_by_name: string | null;
  created_at: string;
  items: Array<{
    id: number;
    purchase_order_item: number;
    material_name: string;
    accepted_quantity: string;
    rejected_quantity: string;
    damaged_quantity: string;
    notes: string;
  }>;
};

export type PurchaseOrderThreeWaySummary = {
  purchase_order: number;
  purchase_order_number: string;
  items: Array<{
    purchase_order_item: number;
    material_name: string;
    material_code: string;
    ordered_quantity: string;
    accepted_quantity: string;
    rejected_quantity: string;
    damaged_quantity: string;
    invoiced_quantity: string;
    paid_quantity: string;
    paid_amount: string;
    remaining_receivable_quantity: string;
    remaining_invoiceable_quantity: string;
    remaining_payable_quantity: string;
  }>;
};

export type NotificationItem = {
  id: number;
  notification_type: string;
  notification_type_display: string;
  level: 'info' | 'success' | 'warning' | 'danger';
  title: string;
  message: string;
  link: string;
  is_read: boolean;
  created_at: string;
};

export type ChatRoom = {
  id: number;
  company: number;
  project: number;
  project_name: string;
  created_at: string;
};

export type ChatMessage = {
  id: number;
  room: number;
  project: number;
  sender: number | null;
  sender_username: string | null;
  content: string;
  is_system_message: boolean;
  created_at: string;
};

export type DashboardMovement = {
  id: number;
  material: { id: number; name: string; code: string };
  project: { id: number; name: string; code: string } | null;
  movement_type: string;
  movement_type_display: string;
  source: string;
  source_display: string;
  quantity: string;
  unit_price: string;
  date: string;
  notes: string;
};

export type DashboardData = {
  total_active_materials: number;
  active_projects: number;
  low_stock_count: number;
  pending_purchase_requests: number;
  stock_in_today: string;
  inventory_value: string;
  recent_stock_movements: DashboardMovement[];
  low_stock_materials: Material[];
  pending_purchase_requests_list: PurchaseRequest[];
  project_budget_vs_actual: Array<{
    id: number;
    name: string;
    code: string;
    budget: string;
    actual_material_cost: string;
    actual_expenditure: string;
    open_commitments: string;
    remaining_budget: string;
    budget_source: 'finance' | 'legacy';
    planned_progress?: number;
    actual_progress?: number;
  }>;
};
