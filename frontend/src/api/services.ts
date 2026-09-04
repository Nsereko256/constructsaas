import { apiDownload, apiRequest, pageParams, setTokens, clearTokens, getTokens } from './client';
import type {
  DashboardData,
  GoodsReceivedNote,
  Category,
  ChatMessage,
  ChatRoom,
  Material,
  NotificationItem,
  Paginated,
  Project,
  ProjectGoal,
  ProjectSite,
  PurchaseOrder,
  PurchaseOrderAmendment,
  SiteTransfer,
  PurchaseOrderThreeWaySummary,
  PurchaseRequest,
  StockMovement,
  Supplier,
  SupplierClaim,
  User,
  WorkflowBadges,
  Warehouse,
  BinLocation,
  ProjectStaffAssignment,
  ApprovalDelegation,
  WorkOrder,
  WorkOrderMetrics,
  WorkOrderSite,
} from './types';

export async function login(username: string, password: string, terminateOtherSession = false) {
  const tokens = await apiRequest<{ access: string; refresh: string }>('/api/token/', {
    method: 'POST',
    body: { username, password, terminate_other_session: terminateOtherSession },
  });
  setTokens(tokens);
  return tokens;
}

export async function requestPasswordReset(email: string) {
  return apiRequest<{ detail: string }>('/api/password-reset/', { method: 'POST', body: { email } });
}

export async function confirmPasswordReset(uid: string, token: string, password: string) {
  return apiRequest<{ detail: string }>('/api/password-reset/confirm/', {
    method: 'POST', body: { uid, token, password },
  });
}

export async function registerCompany(body: { company_name: string; username: string; first_name: string; last_name: string; email: string; password: string; password_confirm: string }) {
  return apiRequest<{ detail: string; username: string }>('/api/register-company/', { method: 'POST', body });
}

export async function logout() {
  const refresh = getTokens()?.refresh;
  const request = refresh ? apiRequest('/api/token/logout/', { method: 'POST', body: { refresh }, keepalive: true }).catch(() => undefined) : Promise.resolve();
  clearTokens();
  await request;
}

export const api = {
  dashboard: () => apiRequest<DashboardData>('/api/dashboard/'),
  workflowBadges: () => apiRequest<WorkflowBadges>('/api/workflow-badges/'),
  reports: () => apiRequest<DashboardData>('/api/reports/'),
  me: () => apiRequest<User>('/api/users/me/'),
  users: (params = {}) => apiRequest<Paginated<User>>(`/api/users/${pageParams(params)}`),
  user: (id: number) => apiRequest<User>(`/api/users/${id}/`),
  createUser: (body: Partial<User> & { password?: string }) => apiRequest<User>('/api/users/', { method: 'POST', body }),
  updateUser: (id: number, body: Partial<User> & { password?: string }) => apiRequest<User>(`/api/users/${id}/`, { method: 'PATCH', body }),
  categories: (params = {}) => apiRequest<Paginated<Category>>(`/api/categories/${pageParams(params)}`),
  createCategory: (body: Partial<Category>) => apiRequest<Category>('/api/categories/', { method: 'POST', body }),
  projects: (params = {}) => apiRequest<Paginated<Project>>(`/api/projects/${pageParams(params)}`),
  projectSites: (params = {}) => apiRequest<Paginated<ProjectSite>>(`/api/project-sites/${pageParams(params)}`),
  saveProjectSite: (body: Partial<ProjectSite>, id?: number) => apiRequest<ProjectSite>(id ? `/api/project-sites/${id}/` : '/api/project-sites/', { method: id ? 'PATCH' : 'POST', body }),
  toggleProjectSiteClosed: (id: number) => apiRequest<{ detail: string; site: ProjectSite }>(`/api/project-sites/${id}/toggle-closed/`, { method: 'POST' }),
  projectGoals: (params = {}) => apiRequest<Paginated<ProjectGoal>>(`/api/project-goals/${pageParams(params)}`),
  saveProjectGoal: (body: Partial<ProjectGoal>, id?: number) => apiRequest<ProjectGoal>(id ? `/api/project-goals/${id}/` : '/api/project-goals/', { method: id ? 'PATCH' : 'POST', body }),
  warehouses: (params = {}) => apiRequest<Paginated<Warehouse>>(`/api/warehouses/${pageParams(params)}`),
  binLocations: (params = {}) => apiRequest<Paginated<BinLocation>>(`/api/bin-locations/${pageParams(params)}`),
  saveBinLocation: (body: unknown, id?: number) => apiRequest<BinLocation>(id ? `/api/bin-locations/${id}/` : '/api/bin-locations/', { method: id ? 'PATCH' : 'POST', body }),
  project: (id: string | number) => apiRequest<Project>(`/api/projects/${id}/`),
  saveProject: (body: Partial<Project>, id?: number) =>
    apiRequest<Project>(id ? `/api/projects/${id}/` : '/api/projects/', { method: id ? 'PATCH' : 'POST', body }),
  materials: (params = {}) => apiRequest<Paginated<Material>>(`/api/materials/${pageParams(params)}`),
  saveMaterial: (body: Partial<Material>, id?: number) =>
    apiRequest<Material>(id ? `/api/materials/${id}/` : '/api/materials/', { method: id ? 'PATCH' : 'POST', body }),
  deleteMaterial: (id: number) => apiRequest<void>(`/api/materials/${id}/`, { method: 'DELETE' }),
  downloadInventoryPdf: (params = {}) => apiDownload(`/api/materials/download-pdf/${pageParams(params)}`, 'inventory-register.pdf'),
  downloadInventoryXlsx: (params = {}) => apiDownload(`/api/materials/download-xlsx/${pageParams(params)}`, 'inventory-register.xlsx'),
  movements: (params = {}) => apiRequest<Paginated<StockMovement>>(`/api/stock-movements/${pageParams(params)}`),
  createMovement: (body: Partial<StockMovement>) => apiRequest<StockMovement>('/api/stock-movements/', { method: 'POST', body }),
  downloadMovementsPdf: (params = {}) => apiDownload(`/api/stock-movements/download-pdf/${pageParams(params)}`, 'stock-movements.pdf'),
  downloadMovementsXlsx: (params = {}) => apiDownload(`/api/stock-movements/download-xlsx/${pageParams(params)}`, 'stock-movements.xlsx'),
  suppliers: (params = {}) => apiRequest<Paginated<Supplier>>(`/api/suppliers/${pageParams(params)}`),
  saveSupplier: (body: Partial<Supplier>, id?: number) =>
    apiRequest<Supplier>(id ? `/api/suppliers/${id}/` : '/api/suppliers/', { method: id ? 'PATCH' : 'POST', body }),
  purchaseRequests: (params = {}) => apiRequest<Paginated<PurchaseRequest>>(`/api/purchase-requests/${pageParams(params)}`),
  downloadPurchaseRequests: (kind: 'pdf' | 'xlsx', params = {}) => apiDownload(`/api/purchase-requests/download/${kind}/${pageParams(params)}`, `purchase-request-register.${kind}`),
  workOrders: (params = {}) => apiRequest<Paginated<WorkOrder>>(`/api/work-orders/${pageParams(params)}`),
  workOrder: (id: number) => apiRequest<WorkOrder>(`/api/work-orders/${id}/`),
  saveWorkOrder: (body: Partial<WorkOrder>, id?: number) => apiRequest<WorkOrder>(id ? `/api/work-orders/${id}/` : '/api/work-orders/', { method: id ? 'PATCH' : 'POST', body }),
  workOrderTransition: (id: number, action: string, comments = '', details: Record<string, unknown> = {}) => apiRequest<WorkOrder>(`/api/work-orders/${id}/${action}/`, { method: 'POST', body: { comments, ...details } }),
  submitWorkOrderFinanceReview: (id: number) => apiRequest<WorkOrder>(`/api/work-orders/${id}/submit-finance-review/`, { method: 'POST' }),
  assignWorkOrder: (id: number, body: Partial<WorkOrder>) => apiRequest<WorkOrder>(`/api/work-orders/${id}/assign/`, { method: 'POST', body }),
  acceptWorkOrderAssignment: (id: number, response = '') => apiRequest<WorkOrder>(`/api/work-orders/${id}/accept-assignment/`, { method: 'POST', body: { response } }),
  declineWorkOrderAssignment: (id: number, response: string) => apiRequest<WorkOrder>(`/api/work-orders/${id}/decline-assignment/`, { method: 'POST', body: { response } }),
  financeReviewWorkOrder: (id: number, body: { approved_cost: string; notes?: string }) => apiRequest<WorkOrder>(`/api/work-orders/${id}/finance-review/`, { method: 'POST', body }),
  workOrderChanges: (id: number) => apiRequest<import('./types').WorkOrderChange[]>(`/api/work-orders/${id}/changes/`),
  createWorkOrderChange: (id: number, body: unknown) => apiRequest(`/api/work-orders/${id}/changes/`, { method: 'POST', body }),
  approveWorkOrderChange: (id: number, changeId: number, body: { finance_confirmed?: boolean; review_notes?: string }) => apiRequest(`/api/work-orders/${id}/changes/${changeId}/approve/`, { method: 'POST', body }),
  rejectWorkOrderChange: (id: number, changeId: number, review_notes: string) => apiRequest(`/api/work-orders/${id}/changes/${changeId}/reject/`, { method: 'POST', body: { review_notes } }),
  createWorkOrderTask: (id: number, body: unknown) => apiRequest(`/api/work-orders/${id}/tasks/`, { method: 'POST', body }),
  updateWorkOrderTask: (id: number, taskId: number, body: unknown) => apiRequest(`/api/work-orders/${id}/tasks/${taskId}/`, { method: 'PATCH', body }),
  uploadWorkOrderAttachment: (id: number, file: File, name = '') => { const body = new FormData(); body.append('file', file); if (name) body.append('name', name); return apiRequest(`/api/work-orders/${id}/attachments/`, { method: 'POST', body }); },
  createWorkOrderSite: (id: number, body: unknown) => apiRequest<WorkOrderSite>(`/api/work-orders/${id}/sites/`, { method: 'POST', body }),
  workOrderSites: (params = {}) => apiRequest<Paginated<WorkOrderSite>>(`/api/work-order-sites/${pageParams(params)}`),
  updateWorkOrderSiteProgress: (id: number, body: { progress_percent: number; progress_notes: string }) => apiRequest<WorkOrderSite>(`/api/work-order-sites/${id}/progress/`, { method: 'POST', body }),
  transitionWorkOrderSite: (id: number, body: { status: string; comments?: string }) => apiRequest<WorkOrderSite>(`/api/work-order-sites/${id}/transition/`, { method: 'POST', body }),
  closeoutWorkOrderSite: (id: number, body: { materials_reconciled: boolean; quality_checked: boolean; safety_checked: boolean; client_signed_off: boolean; closeout_notes: string }) => apiRequest<WorkOrderSite>(`/api/work-order-sites/${id}/closeout/`, { method: 'POST', body }),
  createWorkOrderMaterialRequest: (id: number, body: unknown) => apiRequest(`/api/work-orders/${id}/material-requests/`, { method: 'POST', body }),
  workOrderMetrics: () => apiRequest<WorkOrderMetrics>('/api/work-orders/metrics/'),
  workOrderActionQueue: () => apiRequest<{ requires_action: WorkOrder[]; overdue: WorkOrder[]; held: WorkOrder[] }>('/api/work-orders/action-queue/'),
  workOrderSchedule: () => apiRequest<Array<{ id: number; work_order: string; project: string; site: string; scope: string; start: string | null; due: string | null; status: string; progress: number; responsible: string; contractor: string }>>('/api/work-orders/schedule/'),
  workOrderOperationsReport: () => apiRequest<Record<string, number>>('/api/work-orders/operations-report/'),
  contractorPerformance: () => apiRequest<Array<Record<string, unknown>>>('/api/work-orders/contractor-performance/'),
  escalateOverdueWorkOrders: () => apiRequest<{ escalated: number }>('/api/work-orders/escalate-overdue/', { method: 'POST' }),
  reopenWorkOrder: (id: number, reason: string) => apiRequest<WorkOrder>(`/api/work-orders/${id}/reopen/`, { method: 'POST', body: { reason } }),
  reviewEmergencyWorkOrder: (id: number, notes: string) => apiRequest<WorkOrder>(`/api/work-orders/${id}/emergency-retrospective-review/`, { method: 'POST', body: { notes } }),
  workOrderMaterialAvailability: (material: number, warehouse?: number) => apiRequest<{ material: number; locations: Array<{ warehouse: number; warehouse_name: string; on_hand: string }> }>(`/api/work-orders/material-availability/?material=${material}${warehouse ? `&warehouse=${warehouse}` : ''}`),
  workOrderInvoices: () => apiRequest<import('./types').WorkOrderInvoiceRecord[]>('/api/work-orders/invoices/'),
  downloadWorkOrders: (kind: 'pdf' | 'xlsx', params = {}) => apiDownload(`/api/work-orders/download/${kind}/${pageParams(params)}`, `work-orders-register.${kind}`),
  downloadWorkOrderDetail: (id: number, kind: 'pdf' | 'xlsx', number: string) => apiDownload(`/api/work-orders/${id}/download/${kind}/`, `${number}.${kind}`),
  downloadWorkOrderProgress: (kind: 'pdf' | 'xlsx', params = {}) => apiDownload(`/api/work-order-sites/download/${kind}/${pageParams(params)}`, `work-order-site-progress.${kind}`),
  purchaseRequest: (id: number) => apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/`),
  createPurchaseRequest: (body: unknown) => apiRequest<PurchaseRequest>('/api/purchase-requests/', { method: 'POST', body }),
  updatePurchaseRequest: (id: number, body: unknown) => apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/`, { method: 'PATCH', body }),
  deletePurchaseRequest: (id: number) => apiRequest<void>(`/api/purchase-requests/${id}/`, { method: 'DELETE' }),
  approvePurchaseRequest: (id: number) => apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/approve/`, { method: 'POST' }),
  approvePurchaseRequestStockIssue: (id: number) => apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/approve-stock-issue/`, { method: 'POST' }),
  rejectPurchaseRequest: (id: number, rejection_reason: string) =>
    apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/reject/`, { method: 'POST', body: { rejection_reason } }),
  returnPurchaseRequestForCorrection: (id: number, comments: string) =>
    apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/return-for-correction/`, { method: 'POST', body: { comments } }),
  requestStockIssue: (id: number) => apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/issue-stock/`, { method: 'POST' }),
  fulfillStockIssue: (id: number, body: { items: Array<{ purchase_request_item: number; quantity: string }> }) => apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/fulfill-stock/`, { method: 'POST', body }),
  submitPurchaseRequestFinance: (id: number, budget_line: number | null, comments = '') =>
    apiRequest(`/api/purchase-requests/${id}/submit-finance/`, { method: 'POST', body: { budget_line, comments } }),
  financeApprovePurchaseRequest: (id: number, comments = '', override = false) =>
    apiRequest(`/api/purchase-requests/${id}/finance-approve/`, { method: 'POST', body: { comments, override } }),
  financeRejectPurchaseRequest: (id: number, comments: string) =>
    apiRequest(`/api/purchase-requests/${id}/finance-reject/`, { method: 'POST', body: { comments } }),
  financeReturnPurchaseRequest: (id: number, comments: string) =>
    apiRequest(`/api/purchase-requests/${id}/finance-return/`, { method: 'POST', body: { comments } }),
  correctPurchaseRequest: (id: number, body: unknown) =>
    apiRequest<PurchaseRequest>(`/api/purchase-requests/${id}/correct/`, { method: 'POST', body }),
  financeHoldPurchaseRequest: (id: number, comments: string) =>
    apiRequest(`/api/purchase-requests/${id}/finance-hold/`, { method: 'POST', body: { comments } }),
  purchaseOrders: (params = {}) => apiRequest<Paginated<PurchaseOrder>>(`/api/purchase-orders/${pageParams(params)}`),
  downloadPurchaseOrders: (kind: 'pdf' | 'xlsx', params = {}) => apiDownload(`/api/purchase-orders/download/${kind}/${pageParams(params)}`, `purchase-order-register.${kind}`),
  purchaseOrder: (id: number) => apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/`),
  updatePurchaseOrder: (id: number, body: unknown) => apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/`, { method: 'PATCH', body }),
  deletePurchaseOrder: (id: number) => apiRequest<void>(`/api/purchase-orders/${id}/`, { method: 'DELETE' }),
  purchaseOrderThreeWaySummary: (id: number) => apiRequest<PurchaseOrderThreeWaySummary>(`/api/purchase-orders/${id}/three-way-summary/`),
  createPurchaseOrder: (body: unknown) => apiRequest<PurchaseOrder>('/api/purchase-orders/', { method: 'POST', body }),
  createPurchaseOrderFromPr: (id: number, body: unknown) =>
    apiRequest<PurchaseOrder>(`/api/purchase-orders/from-pr/${id}/`, { method: 'POST', body }),
  confirmDispatch: (id: number) => apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/confirm-dispatch/`, { method: 'POST' }),
  receivePurchaseOrder: (id: number, body?: unknown) => apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/receive/`, { method: 'POST', body }),
  goodsReceivedNotes: (params = {}) => apiRequest<Paginated<GoodsReceivedNote>>(`/api/goods-received-notes/${pageParams(params)}`),
  downloadGoodsReceivedNotePdf: (id: number, number: string) => apiDownload(`/api/goods-received-notes/${id}/download-pdf/`, `${number}.pdf`),
  downloadGoodsReceivedNoteRegisterPdf: (params = {}) => apiDownload(`/api/goods-received-notes/download-register-pdf/${pageParams(params)}`, 'goods-received-note-register.pdf'),
  downloadGoodsReceivedNoteRegisterXlsx: (params = {}) => apiDownload(`/api/goods-received-notes/download-register-xlsx/${pageParams(params)}`, 'goods-received-note-register.xlsx'),
  supplierClaims: (params = {}) => apiRequest<Paginated<SupplierClaim>>(`/api/supplier-claims/${pageParams(params)}`),
  supplierClaim: (id: number) => apiRequest<SupplierClaim>(`/api/supplier-claims/${id}/`),
  updateSupplierClaim: (id: number, body: Partial<SupplierClaim>) => apiRequest<SupplierClaim>(`/api/supplier-claims/${id}/`, { method: 'PATCH', body }),
  receiveSupplierReplacement: (id: number, body: Record<string, unknown>) => apiRequest<GoodsReceivedNote>(`/api/supplier-claims/${id}/receive-replacement/`, { method: 'POST', body }),
  downloadSupplierClaims: (kind: 'pdf' | 'xlsx', params = {}) => apiDownload(`/api/supplier-claims/download/${kind}/${pageParams(params)}`, `supplier-claims-register.${kind}`),
  approvePurchaseOrder: (id: number) => apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/approve/`, { method: 'POST' }),
  cancelPurchaseOrder: (id: number, comments: string) =>
    apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/cancel/`, { method: 'POST', body: { comments } }),
  purchaseOrderAmendments: (id: number) => apiRequest<PurchaseOrderAmendment[]>(`/api/purchase-orders/${id}/amendments/`),
  submitPurchaseOrderAmendment: (id: number, body: unknown) =>
    apiRequest<PurchaseOrderAmendment>(`/api/purchase-orders/${id}/submit-amendment/`, { method: 'POST', body }),
  editPurchaseOrderBeforeApproval: (id: number, body: unknown) =>
    apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/edit-before-approval/`, { method: 'POST', body }),
  approvePurchaseOrderAmendment: (id: number, amendmentId: number, comments: string) =>
    apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/amendments/${amendmentId}/approve/`, { method: 'POST', body: { comments } }),
  rejectPurchaseOrderAmendment: (id: number, amendmentId: number, comments: string) =>
    apiRequest<PurchaseOrderAmendment>(`/api/purchase-orders/${id}/amendments/${amendmentId}/reject/`, { method: 'POST', body: { comments } }),
  confirmPreApprovalEdit: (id: number, comments: string) =>
    apiRequest<PurchaseOrder>(`/api/purchase-orders/${id}/confirm-preapproval-edit/`, { method: 'POST', body: { comments } }),
  siteTransfers: () => apiRequest<SiteTransfer[]>('/api/stock-movements/site-transfers/'),
  dispatchToSite: (body: unknown) => apiRequest<SiteTransfer>('/api/stock-movements/dispatch-to-site/', { method: 'POST', body }),
  acknowledgeSiteTransfer: (id: number) => apiRequest<SiteTransfer>(`/api/stock-movements/site-transfers/${id}/acknowledge/`, { method: 'POST' }),
  consumeSiteStock: (body: unknown) => apiRequest<StockMovement>('/api/stock-movements/consume-site-stock/', { method: 'POST', body }),
  returnSiteStock: (body: unknown) => apiRequest<StockMovement>('/api/stock-movements/return-site-stock/', { method: 'POST', body }),
  staffAssignments: (params = {}) => apiRequest<Paginated<ProjectStaffAssignment>>(`/api/project-staff-assignments/${pageParams(params)}`),
  createStaffAssignment: (body: unknown) => apiRequest<ProjectStaffAssignment>('/api/project-staff-assignments/', { method: 'POST', body }),
  updateStaffAssignment: (id: number, body: unknown) => apiRequest<ProjectStaffAssignment>(`/api/project-staff-assignments/${id}/`, { method: 'PATCH', body }),
  delegations: (params = {}) => apiRequest<Paginated<ApprovalDelegation>>(`/api/approval-delegations/${pageParams(params)}`),
  createDelegation: (body: unknown) => apiRequest<ApprovalDelegation>('/api/approval-delegations/', { method: 'POST', body }),
  updateDelegation: (id: number, body: unknown) => apiRequest<ApprovalDelegation>(`/api/approval-delegations/${id}/`, { method: 'PATCH', body }),
  notifications: (params = {}) => apiRequest<Paginated<NotificationItem>>(`/api/notifications/${pageParams(params)}`),
  unreadCount: () => apiRequest<{ unread_count: number }>('/api/notifications/unread-count/'),
  markNotificationRead: (id: number) => apiRequest(`/api/notifications/${id}/mark-read/`, { method: 'POST' }),
  markAllNotificationsRead: () => apiRequest('/api/notifications/mark-all-read/', { method: 'POST' }),
  pushConfig: () => apiRequest<{ enabled: boolean; public_key: string }>('/api/notifications/push-config/'),
  savePushSubscription: (subscription: PushSubscriptionJSON) => apiRequest('/api/notifications/push-subscription/', { method: 'POST', body: subscription }),
  removePushSubscription: (endpoint: string) => apiRequest('/api/notifications/push-subscription/', { method: 'DELETE', body: { endpoint } }),
  sendTestPush: () => apiRequest<{ delivered: number }>('/api/notifications/send-test-push/', { method: 'POST' }),
  chatRooms: (params = {}) => apiRequest<Paginated<ChatRoom>>(`/api/chat-rooms/${pageParams(params)}`),
  chatMessages: (params = {}) => apiRequest<Paginated<ChatMessage>>(`/api/chat-messages/${pageParams(params)}`),
};
