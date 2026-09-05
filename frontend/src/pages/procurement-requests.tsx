import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Box, Check, ChevronDown, ChevronRight, CircleDollarSign, Clock3, CornerUpLeft, Download, EllipsisVertical, FileText, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { financeApi } from '@/modules/finance/api';
import { api } from '@/modules/procurement/api';
import { getTokens } from '@/api/client';
import { offlineScope, queueOfflineAction } from '@/pwa/offline';
import type { PurchaseRequest } from '@/modules/procurement/types';
import { qk } from '@/api/queryKeys';
import { can, hasRole } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { MaterialLookup } from '@/components/common/material-lookup';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';
import './purchase-requests-reference.css';

const draftKey = 'construct.pr.draft';

export function ProcurementRequestsPage() {
  const { role, user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const toast = useToast();
  const queryClient = useQueryClient();
  const list = useListState({ status: '', priority: '', project: '', action_queue: searchParams.get('action_queue') || '' });
  const [queue, setQueue] = useState<'all' | 'mine' | 'awaiting' | 'stock' | 'completed'>(() => searchParams.get('action_queue') ? 'mine' : 'all');
  const [sort, setSort] = useState<'action' | 'newest'>('action');
  const [open, setOpen] = useState(() => searchParams.get('create') === '1' && can.submitPr(role));
  const [rejecting, setRejecting] = useState<PurchaseRequest | null>(null);
  const [returning, setReturning] = useState<PurchaseRequest | null>(null);
  const [financeSubmission, setFinanceSubmission] = useState<PurchaseRequest | null>(null);
  const [financeDecision, setFinanceDecision] = useState<PurchaseRequest | null>(null);
  const [correcting, setCorrecting] = useState<PurchaseRequest | null>(null);
  const [editingDraft, setEditingDraft] = useState<PurchaseRequest | null>(null);
  const [stockIssueReview, setStockIssueReview] = useState<PurchaseRequest | null>(null);
  const [issuingStock, setIssuingStock] = useState<PurchaseRequest | null>(null);
  const requestQuery = { ...list.query, page_size: 5 };
  const requests = useQuery({ queryKey: list.filters.action_queue ? qk.purchaseRequestActionQueue(requestQuery) : qk.purchaseRequests(requestQuery), queryFn: () => api.purchaseRequests(requestQuery) });
  const allRequests = useQuery({ queryKey: qk.purchaseRequests({ page_size: 100 }), queryFn: () => api.purchaseRequests({ page_size: 100 }) });
  const projects = useQuery({ queryKey: qk.projects({ page_size: 100 }), queryFn: () => api.projects({ page_size: 100 }) });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
    void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    void queryClient.invalidateQueries({ queryKey: qk.workflowBadges });
    void queryClient.invalidateQueries({ queryKey: ['finance'] });
  };
  const approve = useMutation({
    mutationFn: api.approvePurchaseRequest,
    onSuccess: () => { toast.push({ title: 'Purchase request approved', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not approve PR', message: error.message, tone: 'danger' }),
  });
  const approveStockIssue = useMutation({
    mutationFn: api.approvePurchaseRequestStockIssue,
    onSuccess: () => { toast.push({ title: 'Stock issue approval recorded', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not approve stock issue', message: error.message, tone: 'danger' }),
  });
  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => api.rejectPurchaseRequest(id, reason),
    onSuccess: () => { toast.push({ title: 'Purchase request rejected', tone: 'warning' }); setRejecting(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not reject PR', message: error.message, tone: 'danger' }),
  });
  const returnForCorrection = useMutation({
    mutationFn: ({ id, comments }: { id: number; comments: string }) => api.returnPurchaseRequestForCorrection(id, comments),
    onSuccess: () => { toast.push({ title: 'Purchase request returned for correction', tone: 'warning' }); setReturning(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not return PR for correction', message: error.message, tone: 'danger' }),
  });
  const issue = useMutation({
    mutationFn: api.requestStockIssue,
    onSuccess: () => { toast.push({ title: 'Stock issue request sent', tone: 'success' }); setStockIssueReview(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not request stock issue', message: error.message, tone: 'danger' }),
  });
  const fulfill = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { items: Array<{ purchase_request_item: number; quantity: string }> } }) => api.fulfillStockIssue(id, body),
    onSuccess: (request) => { toast.push({ title: request.status === 'PARTIAL_STOCK_ISSUED' ? 'Available stock issued - Procurement can source the balance' : 'Warehouse stock issued', tone: 'success' }); setIssuingStock(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Stock issue blocked', message: error.message, tone: 'danger' }),
  });
  const submitFinance = useMutation({
    mutationFn: ({ id, budgetLine, comments }: { id: number; budgetLine: number | null; comments: string }) =>
      api.submitPurchaseRequestFinance(id, budgetLine, comments),
    onSuccess: () => { toast.push({ title: 'Purchase request sent to finance', tone: 'success' }); setFinanceSubmission(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Finance submission failed', message: error.message, tone: 'danger' }),
  });
  const reviewFinance = useMutation({
    mutationFn: ({ id, decision, comments, override }: { id: number; decision: FinanceDecision; comments: string; override: boolean }) => {
      if (decision === 'approve') return api.financeApprovePurchaseRequest(id, comments, override);
      if (decision === 'reject') return api.financeRejectPurchaseRequest(id, comments);
      if (decision === 'return') return api.financeReturnPurchaseRequest(id, comments);
      return api.financeHoldPurchaseRequest(id, comments);
    },
    onSuccess: (_, variables) => { toast.push({ title: `Finance review completed: ${variables.decision}`, tone: 'success' }); setFinanceDecision(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Finance review failed', message: error.message, tone: 'danger' }),
  });
  const correct = useMutation({
    mutationFn: ({ id, body }: { id: number; body: unknown }) => api.correctPurchaseRequest(id, body),
    onSuccess: () => { toast.push({ title: 'Correction saved — ready for the required approval step', tone: 'success' }); setCorrecting(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not save correction', message: error.message, tone: 'danger' }),
  });
  const editDraft = useMutation({
    mutationFn: ({ id, body }: { id: number; body: unknown }) => api.updatePurchaseRequest(id, body),
    onSuccess: () => { toast.push({ title: 'Purchase request updated', tone: 'success' }); setEditingDraft(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not update purchase request', message: error.message, tone: 'danger' }),
  });
  const deleteDraft = useMutation({
    mutationFn: api.deletePurchaseRequest,
    onSuccess: () => { toast.push({ title: 'Draft purchase request deleted', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not delete purchase request', message: error.message, tone: 'danger' }),
  });

  // Operational queues should answer “what needs attention?” before showing
  // older, already-progressed requests. Keep the API ordering intact for
  // pagination, but make the current page scan in action-first order.
  const requestNeedsAction = (request: PurchaseRequest) => [
      request.can_approve_stock_issue,
      request.can_request_stock_issue,
      request.can_fulfill_from_stock,
      request.can_issue_from_stock,
      request.can_submit_finance,
      request.can_create_purchase_order,
      request.can_correct_return,
      can.approvePr(role) && request.status === 'PENDING',
      can.reviewPrFinance(role) && ['SUBMITTED', 'HOLD'].includes(request.finance_status),
    ].some(Boolean);

  const requestRows = [...(requests.data?.results || [])].sort((a, b) => {
    if (sort === 'newest') return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    const actionScore = (request: PurchaseRequest) => requestNeedsAction(request) ? 0 : 1;
    const score = actionScore(a) - actionScore(b);
    return score || new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const allRows = allRequests.data?.results || [];
  const totalValue = allRows.reduce((sum, request) => sum + Number(request.total_estimated_cost || 0), 0);
  const actionRows = allRows.filter(requestNeedsAction);
  const awaitingApproval = allRows.filter((request) => request.status === 'PENDING');
  const stockIssueRows = allRows.filter((request) => [
    'STOCK_ISSUE_REQUESTED', 'PARTIAL_STOCK_ISSUED', 'STOCK_ISSUED',
  ].includes(request.status));
  const readyForStockIssue = allRows.filter((request) => request.can_approve_stock_issue || request.can_request_stock_issue || request.can_fulfill_from_stock);
  const stockIssueValue = stockIssueRows.reduce((sum, request) => sum + Number(request.total_estimated_cost || 0), 0);
  const purchaseValue = Math.max(0, totalValue - stockIssueValue);
  const projectOptions = projects.data?.results || [];
  const pageSize = 5;
  const totalRows = requests.data?.count || 0;
  const pageStart = totalRows ? (list.page - 1) * pageSize + 1 : 0;
  const pageEnd = totalRows ? Math.min(list.page * pageSize, totalRows) : 0;
  const stockAvailability = (request: PurchaseRequest) => {
    const lines = request.items || [];
    if (!lines.length) return { label: 'No lines', tone: 'neutral' as const };
    const fullyAvailable = lines.every((item) => Number(item.warehouse_available) >= Number(item.outstanding_quantity));
    const anyAvailable = lines.some((item) => Number(item.warehouse_available) > 0);
    if (fullyAvailable) return { label: 'Available', tone: 'success' as const };
    if (anyAvailable) return { label: 'Partial stock', tone: 'warning' as const };
    return { label: 'Not available', tone: 'danger' as const };
  };
  const updateQueue = (value: typeof queue) => {
    setQueue(value);
    if (value === 'mine') {
      list.setFilter('status', '');
      list.setFilter('action_queue', 'my_requests');
      return;
    }
    list.setFilter('action_queue', '');
    list.setFilter('status', value === 'awaiting' ? 'PENDING' : value === 'stock' ? 'STOCK_ISSUE_REQUESTED' : value === 'completed' ? 'STOCK_ISSUED' : '');
  };
  const primaryAction = (request: PurchaseRequest) => {
    if (can.approvePr(role) && request.status === 'PENDING') return <Button size="sm" className="pr-next-action" onClick={() => approve.mutate(request.id)}>Approve</Button>;
    if (request.can_approve_stock_issue) return <Button size="sm" className="pr-next-action" onClick={() => approveStockIssue.mutate(request.id)} disabled={approveStockIssue.isPending}>Approve stock</Button>;
    if (hasRole(role, ['procurement_officer', 'admin']) && request.can_request_stock_issue) return <Button size="sm" className="pr-next-action" onClick={() => setStockIssueReview(request)}>Request issue</Button>;
    if (hasRole(role, ['storekeeper', 'admin']) && request.can_fulfill_from_stock) return <Button size="sm" className="pr-next-action" onClick={() => setIssuingStock(request)}>Issue stock</Button>;
    if (can.submitPrToFinance(role) && request.can_submit_finance && request.has_purchase_order) return <Button size="sm" className="pr-next-action" onClick={() => setFinanceSubmission(request)}>Send to finance</Button>;
    if (can.createPo(role) && request.can_create_purchase_order) return <Button size="sm" className="pr-next-action" onClick={() => navigate('/procurement/purchase-orders', { state: { purchaseRequestId: request.id } })}>{request.status === 'PARTIAL_STOCK_ISSUED' ? 'Source balance' : 'Create PO'}</Button>;
    if (request.can_correct_return) return <Button size="sm" className="pr-next-action" onClick={() => setCorrecting(request)}>Correct</Button>;
    if (can.reviewPrFinance(role) && ['SUBMITTED', 'HOLD'].includes(request.finance_status)) return <Button size="sm" className="pr-next-action" onClick={() => setFinanceDecision(request)}>Finance review</Button>;
    return <span className="pr-next-message" title={request.next_action_message}>{request.next_action_message}</span>;
  };

  return (
    <div className="purchase-requests-reference">
      <section className="pr-top">
        <div className="pr-titlebar">
          <div><h1>Purchase requests</h1><p>Create, review and fulfil project material requests.</p></div>
          <div className="pr-title-actions">
            {hasRole(role, ['storekeeper', 'admin']) ? <Button variant="secondary" asChild><Link to="/procurement/requests?action_queue=my_requests"><Box className="h-4 w-4" />Stock issue queue</Link></Button> : null}
            <details className="pr-export-menu"><summary><Download className="h-4 w-4" />Export <ChevronDown className="h-3.5 w-3.5" /></summary><div><button type="button" onClick={() => void api.downloadPurchaseRequests('pdf', { ...list.filters, search: list.search })}>PDF register</button><button type="button" onClick={() => void api.downloadPurchaseRequests('xlsx', { ...list.filters, search: list.search })}>Excel register</button></div></details>
            {can.submitPr(role) || can.submitWarehouseReplenishment(role) ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />{can.submitWarehouseReplenishment(role) && !can.submitPr(role) ? 'Warehouse replenishment' : 'New PR'}</Button> : null}
          </div>
        </div>
        <nav className="pr-tabs" aria-label="Procurement sections">
          <Link to="/procurement">Overview</Link><Link className="active" to="/procurement/requests">Purchase requests</Link><Link to="/procurement/rfqs">Supplier quotes</Link><Link to="/procurement/purchase-orders">Purchase orders</Link><Link to="/procurement/grns">Receipts</Link><Link to="/procurement/deliveries">Deliveries</Link><Link to="/procurement/supplier-claims">Supplier claims</Link>
        </nav>
      </section>
      <section className="pr-guidance"><AlertCircle size={18} /><span><strong>Manager review required before approval</strong><small>Confirm project, justification, quantities, budget and warehouse availability.</small></span><Link to="/procurement/requests?action_queue=my_requests">View workflow <ChevronRight size={14} /></Link></section>
      <section className="pr-kpis">
        <RequestKpi icon={FileText} tone="blue" label="Total requests" value={allRows.length} note="Across selected sites" />
        <RequestKpi icon={AlertCircle} tone="amber" label="Needs action" value={actionRows.length} note="Assigned to your role" />
        <RequestKpi icon={Clock3} tone="sky" label="Awaiting approval" value={awaitingApproval.length} note={awaitingApproval.filter((request) => request.priority === 'URGENT').length ? `${awaitingApproval.filter((request) => request.priority === 'URGENT').length} urgent` : 'No urgent requests'} />
        <RequestKpi icon={Box} tone="green" label="Ready for stock issue" value={readyForStockIssue.length} note="Warehouse workflow" />
      </section>
      <section className="pr-workspace-grid">
        <div className="pr-queue-panel">
          <div className="pr-panel-heading"><h2>Purchase request queue</h2></div>
          <div className="pr-queue-tabs">
            {([['all', 'All', allRows.length], ['mine', 'My actions', actionRows.length], ['awaiting', 'Awaiting approval', awaitingApproval.length], ['stock', 'Stock issue', stockIssueRows.length], ['completed', 'Completed', allRows.filter((request) => ['STOCK_ISSUED', 'PO_CREATED', 'REJECTED'].includes(request.status)).length]] as const).map(([value, label, count]) => <button type="button" key={value} className={queue === value ? 'active' : ''} onClick={() => updateQueue(value)}>{label}<b>{count}</b></button>)}
          </div>
          <div className="pr-filters">
            <label><Search size={14} /><input aria-label="Search purchase requests" placeholder="Search request, project or requester" value={list.search} onChange={(event) => list.setSearch(event.target.value)} /></label>
            <select aria-label="Filter purchase requests by project" className={inputClass} value={list.filters.project} onChange={(event) => list.setFilter('project', event.target.value)}><option value="">Project</option>{projectOptions.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select>
            <select aria-label="Filter purchase requests by status" className={inputClass} value={list.filters.status} onChange={(event) => { setQueue('all'); list.setFilter('action_queue', ''); list.setFilter('status', event.target.value); }}><option value="">Status</option><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="STOCK_ISSUE_REQUESTED">Issue requested</option><option value="PARTIAL_STOCK_ISSUED">Partially issued</option><option value="STOCK_ISSUED">Stock issued</option><option value="PO_CREATED">PO created</option><option value="REJECTED">Rejected</option></select>
            <select aria-label="Filter purchase requests by priority" className={inputClass} value={list.filters.priority} onChange={(event) => list.setFilter('priority', event.target.value)}><option value="">Priority</option><option value="LOW">Low</option><option value="NORMAL">Normal</option><option value="HIGH">High</option><option value="URGENT">Urgent</option></select>
            <select aria-label="Sort purchase requests" className={inputClass} value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="action">Sort: Action first</option><option value="newest">Sort: Newest first</option></select>
          </div>
          <div className="pr-table-wrap"><table className="pr-table"><thead><tr><th>Request</th><th>Project / site</th><th>Requested by</th><th>Created</th><th>Estimate</th><th>Stock available</th><th>Priority</th><th>Status</th><th>Next action</th><th aria-label="Actions" /></tr></thead><tbody>
            {requestRows.map((request) => { const stock = stockAvailability(request); return <tr key={request.id}><td><Link to={`/procurement/requests?search=${encodeURIComponent(request.number)}`}>{request.number}</Link><small>{request.title}</small></td><td>{request.project_name || 'Warehouse replenishment'}</td><td>{request.requested_by_username || 'System'}</td><td>{formatDate(request.created_at)}</td><td>{formatUGX(request.total_estimated_cost)}</td><td><span className={`pr-stock-dot ${stock.tone}`} />{stock.label}</td><td><Badge tone={statusTone(request.priority)}>{request.priority_display}</Badge></td><td><Badge tone={statusTone(request.status)}>{request.status_display}</Badge></td><td>{primaryAction(request)}</td><td><details className="pr-row-menu"><summary aria-label={`More actions for ${request.number}`}><EllipsisVertical size={16} /></summary><div>{hasRole(role, ['admin', 'site_engineer', 'procurement_officer']) && request.status === 'PENDING' && (role === 'admin' || request.requested_by === user?.id) ? <><button type="button" onClick={() => setEditingDraft(request)}><Pencil size={13} />Edit draft</button><button type="button" onClick={() => { if (window.confirm(`Delete ${request.number}? This draft will be removed and audited.`)) deleteDraft.mutate(request.id); }}><Trash2 size={13} />Delete draft</button></> : null}{can.approvePr(role) && request.status === 'PENDING' ? <><button type="button" onClick={() => setReturning(request)}><CornerUpLeft size={13} />Return</button><button type="button" onClick={() => setRejecting(request)}><X size={13} />Reject</button></> : null}{request.can_correct_return ? <button type="button" onClick={() => setCorrecting(request)}><Pencil size={13} />Correct request</button> : null}{can.reviewPrFinance(role) && ['SUBMITTED', 'HOLD'].includes(request.finance_status) ? <button type="button" onClick={() => setFinanceDecision(request)}><CircleDollarSign size={13} />Finance review</button> : null}</div></details></td></tr>; })}
          </tbody></table>{!requestRows.length ? <p className="pr-empty">{requests.isLoading ? 'Loading purchase requests…' : 'No purchase requests match this view.'}</p> : null}</div>
          <footer className="pr-table-footer"><span>Showing {pageStart} to {pageEnd} of {totalRows} purchase requests</span><span><button type="button" disabled={!requests.data?.previous} onClick={() => list.setPage(Math.max(1, list.page - 1))}>‹</button><b>{list.page}</b><button type="button" disabled={!requests.data?.next} onClick={() => list.setPage(list.page + 1)}>›</button></span></footer>
        </div>
        <aside className="pr-side-column">
          <section className="pr-value-panel"><div className="pr-panel-heading"><h2>Request value</h2></div><div className="pr-value-body"><span>Total</span><strong>{formatUGX(totalValue)}</strong><i><b style={{ width: totalValue ? `${stockIssueValue / totalValue * 100}%` : '0%' }} /></i><div><span><em className="stock" />Stock issue <b>{formatUGX(stockIssueValue)}</b></span><span><em className="purchase" />To purchase <b>{formatUGX(purchaseValue)}</b></span></div></div></section>
          <section className="pr-flow-panel"><div className="pr-panel-heading"><h2>Approval flow</h2></div><ol><li className={awaitingApproval.length ? 'active' : ''}><b>1</b><span><strong>Manager review</strong><small>{awaitingApproval.length} awaiting decision</small></span></li><li><b>2</b><span><strong>Admin stock approval</strong><small>Technical and compliance gate</small></span></li><li><b>3</b><span><strong>Stock decision</strong><small>Issue from stock or source a PO</small></span></li><li><b>4</b><span><strong>Fulfilment</strong><small>Store issue or procurement handoff</small></span></li></ol></section>
          <section className="pr-rules-panel"><div className="pr-panel-heading"><h2>Queue rules</h2></div><p><Check size={14} />Action first, then newest context.</p><p><Check size={14} />Warehouse replenishment uses a PO, not stock issue.</p></section>
        </aside>
      </section>
      <RequestModal open={open} onClose={() => setOpen(false)} />
      <StockIssueReviewModal request={stockIssueReview} pending={issue.isPending} onClose={() => setStockIssueReview(null)} onSubmit={() => stockIssueReview && issue.mutate(stockIssueReview.id)} />
      <PartialStockIssueModal request={issuingStock} pending={fulfill.isPending} onClose={() => setIssuingStock(null)} onSubmit={(items) => issuingStock && fulfill.mutate({ id: issuingStock.id, body: { items } })} />
      <RejectModal request={rejecting} onClose={() => setRejecting(null)} onReject={(reason) => rejecting && reject.mutate({ id: rejecting.id, reason })} />
      <ReturnForCorrectionModal request={returning} pending={returnForCorrection.isPending} onClose={() => setReturning(null)} onSubmit={(comments) => returning && returnForCorrection.mutate({ id: returning.id, comments })} />
      <FinanceSubmissionModal
        request={financeSubmission}
        pending={submitFinance.isPending}
        onClose={() => setFinanceSubmission(null)}
        onSubmit={(budgetLine, comments) => financeSubmission && submitFinance.mutate({ id: financeSubmission.id, budgetLine, comments })}
      />
      <FinanceReviewModal
        request={financeDecision}
        pending={reviewFinance.isPending}
        role={role}
        onClose={() => setFinanceDecision(null)}
        onSubmit={(decision, comments, override) => financeDecision && reviewFinance.mutate({ id: financeDecision.id, decision, comments, override })}
      />
      <CorrectionModal request={correcting} pending={correct.isPending} onClose={() => setCorrecting(null)} onSubmit={(body) => correcting && correct.mutate({ id: correcting.id, body })} />
      <CorrectionModal draft request={editingDraft} pending={editDraft.isPending} onClose={() => setEditingDraft(null)} onSubmit={(body) => editingDraft && editDraft.mutate({ id: editingDraft.id, body })} />
    </div>
  );
}

function RequestKpi({ icon: Icon, tone, label, value, note }: { icon: typeof FileText; tone: string; label: string; value: number; note: string }) {
  return <article className="pr-kpi"><span className={`pr-kpi-icon ${tone}`}><Icon size={24} /></span><div><p>{label}</p><strong>{value}</strong><small>{note}</small></div></article>;
}

function StockIssueReviewModal({ request, pending, onClose, onSubmit }: { request: PurchaseRequest | null; pending: boolean; onClose: () => void; onSubmit: () => void }) {
  const lines = request?.items || [];
  const availableLines = lines.filter((item) => Number(item.warehouse_available) > 0).length;
  const fullyAvailable = lines.length > 0 && lines.every((item) => Number(item.warehouse_available) >= Number(item.outstanding_quantity));
  return <FormModal open={!!request} title={`Warehouse availability / ${request?.number || ''}`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <p className="border border-info/20 bg-info/5 p-3 text-sm text-muted">Check available stock before sending the issue request. Stock moves only after the Storekeeper records the issue.</p>
      <div className="grid gap-2 border border-border bg-background p-3 text-sm sm:grid-cols-3"><span>Lines<strong className="mt-1 block">{lines.length}</strong></span><span>Available now<strong className="mt-1 block">{availableLines} line{availableLines === 1 ? '' : 's'}</strong></span><span>Coverage<strong className={`mt-1 block ${fullyAvailable ? 'text-primary' : 'text-warning'}`}>{fullyAvailable ? 'Full' : 'Partial / none'}</strong></span></div>
      {lines.map((item) => {
        const available = Number(item.warehouse_available);
        const required = Number(item.outstanding_quantity);
        const tone = available >= required ? 'text-primary' : available > 0 ? 'text-warning' : 'text-critical';
        return <div key={item.id} className="grid gap-2 border border-border bg-background p-3 text-sm sm:grid-cols-[1fr_auto] sm:items-center"><div><strong>{item.material_name}</strong><p className="mt-1 text-xs text-muted">Requested: {formatNumber(item.outstanding_quantity)} {item.unit}{Number(item.issued_quantity) > 0 ? ` | already issued: ${formatNumber(item.issued_quantity)}` : ''}</p></div><div className="text-left sm:text-right"><p className="text-xs text-muted">Default warehouse</p><strong className={tone}>{formatNumber(item.warehouse_available)} {item.unit}</strong></div></div>;
      })}
      {!fullyAvailable ? <p className="border border-warning/30 bg-warning/5 p-3 text-sm text-foreground">The Storekeeper can issue only the available quantities. After a partial issue, Procurement can create a PO for the remaining balance only.</p> : null}
      <Button loading={pending} loadingLabel="Sending request">Send to Storekeeper</Button>
    </form>
  </FormModal>;
}

function RequestModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { role } = useAuth();
  const isWarehouseReplenishment = role === 'procurement_officer';
  const requiresProject = role === 'site_engineer';
  const projects = useQuery({ queryKey: qk.projects({ is_active: true }), queryFn: () => api.projects({ is_active: true, page_size: 100 }) });
  const [form, setForm] = useState(() => {
    const saved = localStorage.getItem(draftKey);
    if (!saved) return defaultDraft();
    const parsed = JSON.parse(saved) as Omit<Partial<RequestDraft>, 'items'> & {
      items?: Array<{ material?: string; material_id?: string; material_label?: string; quantity?: string; notes?: string }>;
    };
    return {
      ...defaultDraft(),
      ...parsed,
      items: (parsed.items || []).map((item) => ({
        material_id: item.material_id || '',
        material_label: item.material_label || item.material || '',
        quantity: item.quantity || '',
        notes: item.notes || '',
      })),
    };
  });
  const queryClient = useQueryClient();
  const toast = useToast();

  useEffect(() => {
    localStorage.setItem(draftKey, JSON.stringify(form));
  }, [form]);

  const set = (key: keyof RequestDraft, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const setItem = (index: number, key: keyof RequestDraft['items'][number], value: string) =>
    setForm((current) => ({ ...current, items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item) }));
  const addItem = () => setForm((current) => ({
    ...current,
    items: [...current.items, { material_id: '', material_label: '', quantity: '', notes: '' }],
  }));
  const removeItem = (index: number) => setForm((current) => ({ ...current, items: current.items.filter((_, itemIndex) => itemIndex !== index) }));
  const mutation = useMutation({
    mutationFn: async () => {
      const body = {
      client_uuid: crypto.randomUUID(),
      project: isWarehouseReplenishment ? null : form.project || null,
      title: form.title,
      priority: form.priority,
      justification: form.justification,
      items: form.items.map((item) => ({
        material: Number(item.material_id),
        quantity: item.quantity,
        notes: item.notes,
      })),
    };
      const queue = async () => queueOfflineAction({ scope: offlineScope(getTokens()?.access), kind: 'purchase-request', path: '/api/purchase-requests/', body });
      if (!navigator.onLine) {
        await queue();
        return { queued: true };
      }
      try { return await api.createPurchaseRequest(body); }
      catch (error) {
        // A lost response is indistinguishable from a failed request. Queue the
        // same UUID; the server returns the original PR if it already created it.
        if (error instanceof TypeError) { await queue(); return { queued: true }; }
        throw error;
      }
    },
    onSuccess: (result) => {
      const queued = 'queued' in result && result.queued;
      toast.push({ title: queued ? 'Request saved offline — it will submit when connected' : 'Purchase request submitted', tone: 'success' });
      localStorage.removeItem(draftKey);
      setForm(defaultDraft());
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    },
    onError: (error: Error) => toast.push({ title: 'Could not submit PR', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title={isWarehouseReplenishment ? 'New warehouse replenishment' : 'New purchase request'} onClose={onClose}>
      <form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
        {isWarehouseReplenishment ? <p className="border border-info/20 bg-info/5 p-3 text-sm text-muted">This replenishes warehouse stock, not a project. Procurement supplies the technical demand; Finance Manager approval is required before a warehouse purchase order can be created, and the Storekeeper independently confirms receipt.</p> : null}
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Title" required><input className={inputClass} value={form.title} onChange={(event) => set('title', event.target.value)} /></Field>
          {!isWarehouseReplenishment ? <Field label="Project" required={requiresProject}>
            <select className={inputClass} value={form.project} onChange={(event) => set('project', event.target.value)}>
              <option value="">{requiresProject ? 'Select project' : 'No project'}</option>
              {(projects.data?.results || []).map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </Field> : null}
          <Field label="Priority">
            <select className={inputClass} value={form.priority} onChange={(event) => set('priority', event.target.value)}>
              <option value="LOW">Low</option>
              <option value="NORMAL">Normal</option>
              <option value="HIGH">High</option>
              <option value="URGENT">Urgent</option>
            </select>
          </Field>
          <Field label="Justification"><input className={inputClass} value={form.justification} onChange={(event) => set('justification', event.target.value)} /></Field>
        </div>
        <Card>
          <CardHeader><CardTitle>Line items</CardTitle></CardHeader>
          <CardContent className="grid gap-2.5 p-2.5 sm:gap-3 sm:p-3">
            {form.items.map((item, index) => (
              <div key={index} className="grid gap-2 border border-border bg-background p-2.5 md:grid-cols-[1fr_120px_1fr_auto] sm:p-3">
                <Field label="Search material" required>
                  <MaterialLookup
                    label={item.material_label}
                    materialId={item.material_id}
                    required
                    onChange={(id, label) => {
                      setItem(index, 'material_id', id);
                      setItem(index, 'material_label', label);
                    }}
                  />
                </Field>
                <Field label="Quantity" required><input className={inputClass} type="number" min="0.01" step="0.01" value={item.quantity} onChange={(event) => setItem(index, 'quantity', event.target.value)} /></Field>
                <Field label="Notes"><input className={inputClass} value={item.notes} onChange={(event) => setItem(index, 'notes', event.target.value)} /></Field>
                <Button type="button" variant="ghost" size="sm" onClick={() => removeItem(index)}>Remove</Button>
              </div>
            ))}
            <Button type="button" variant="secondary" onClick={addItem}>Add item</Button>
          </CardContent>
        </Card>
        <Button
          disabled={
            !form.title
            || (requiresProject && !form.project)
            || !form.items.length
            || form.items.some((item) => !item.material_id || !item.quantity)
            || mutation.isPending
          }
        >
          {isWarehouseReplenishment ? 'Create replenishment for Finance' : 'Submit request'}
        </Button>
      </form>
    </FormModal>
  );
}

type RequestDraft = {
  project: string;
  title: string;
  priority: 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT';
  justification: string;
  items: Array<{
    material_id: string;
    material_label: string;
    quantity: string;
    notes: string;
  }>;
};

function defaultDraft(): RequestDraft {
  return {
    project: '',
    title: '',
    priority: 'NORMAL',
    justification: '',
    items: [{ material_id: '', material_label: '', quantity: '', notes: '' }],
  };
}

function RejectModal({ request, onClose, onReject }: { request: PurchaseRequest | null; onClose: () => void; onReject: (reason: string) => void }) {
  const [reason, setReason] = useState('');
  return (
    <FormModal open={!!request} title={`Reject ${request?.number || 'purchase request'}`} onClose={onClose}>
      <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onReject(reason); }}>
        <Field label="Rejection reason" required><textarea className={inputClass} value={reason} onChange={(event) => setReason(event.target.value)} /></Field>
        <Button variant="warning" disabled={!reason}>Reject request</Button>
      </form>
    </FormModal>
  );
}

function ReturnForCorrectionModal({ request, pending, onClose, onSubmit }: { request: PurchaseRequest | null; pending: boolean; onClose: () => void; onSubmit: (comments: string) => void }) {
  const [comments, setComments] = useState('');
  useEffect(() => setComments(''), [request]);
  return <FormModal open={!!request} title={`Return ${request?.number || 'purchase request'} for correction`} onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onSubmit(comments); }}><p className="text-sm text-muted">This keeps the request open. The original engineer must correct it before it returns to your approval queue.</p><Field label="Correction required" required><textarea className={inputClass} rows={4} value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Explain exactly what the engineer needs to change." /></Field><Button variant="warning" loading={pending} loadingLabel="Returning request" disabled={!comments.trim()}>Return for correction</Button></form></FormModal>;
}

function CorrectionModal({ request, pending, onClose, onSubmit, draft = false }: { request: PurchaseRequest | null; pending: boolean; onClose: () => void; onSubmit: (body: unknown) => void; draft?: boolean }) {
  const projects = useQuery({ queryKey: qk.projects({ is_active: true }), queryFn: () => api.projects({ is_active: true, page_size: 100 }) });
  const [form, setForm] = useState<null | { project: string; title: string; priority: PurchaseRequest['priority']; justification: string; correction_summary: string; items: RequestDraft['items'] }>(null);
  useEffect(() => {
    setForm(request ? {
      project: request.project ? String(request.project) : '', title: request.title, priority: request.priority,
      justification: request.justification, correction_summary: '',
      items: request.items.map((item) => ({ material_id: String(item.material), material_label: `${item.material_name} (${item.material_code})`, quantity: item.quantity, notes: item.notes })),
    } : null);
  }, [request]);
  const updateItem = (index: number, key: keyof RequestDraft['items'][number], value: string) => setForm((current) => current ? { ...current, items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item) } : current);
  const valid = Boolean(form?.title.trim() && (draft || form.correction_summary.trim()) && form.items.length && form.items.every((item) => item.material_id && item.quantity));
  return <FormModal open={!!request && !!form} title={`${draft ? 'Edit draft' : 'Correct'} ${request?.number || 'purchase request'}`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); if (form && valid) { const body = { ...form, project: form.project ? Number(form.project) : null, items: form.items.map((item) => ({ material: Number(item.material_id), quantity: item.quantity, notes: item.notes })) }; if (draft) delete (body as { correction_summary?: string }).correction_summary; onSubmit(body); } }}>
      <div className="border border-warning/35 bg-warning/5 p-3 text-sm"><strong>{draft ? 'Draft changes' : request?.status === 'RETURNED' ? 'Manager correction required' : 'Finance correction required'}</strong><p className="mt-1">{draft ? 'Only pending drafts can be edited. Submitted or approved requests must use the correction workflow.' : request?.technical_return_reason || request?.finance_return_reason || 'Changes are required before this request can be reconsidered.'}</p></div>
      {form ? <><div className="grid gap-3 md:grid-cols-2"><Field label="Title" required><input className={inputClass} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></Field><Field label="Project"><select className={inputClass} value={form.project} onChange={(event) => setForm({ ...form, project: event.target.value })}><option value="">No project</option>{(projects.data?.results || []).map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></Field><Field label="Priority"><select className={inputClass} value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value as PurchaseRequest['priority'] })}><option value="LOW">Low</option><option value="NORMAL">Normal</option><option value="HIGH">High</option><option value="URGENT">Urgent</option></select></Field><Field label="Business justification"><input className={inputClass} value={form.justification} onChange={(event) => setForm({ ...form, justification: event.target.value })} /></Field></div><Card><CardHeader><CardTitle>{draft ? 'Line items' : 'Corrected line items'}</CardTitle></CardHeader><CardContent className="grid gap-3">{form.items.map((item, index) => <div key={index} className="grid gap-2 border border-border bg-background p-3 md:grid-cols-[1fr_120px_1fr_auto]"><Field label="Material" required><MaterialLookup label={item.material_label} materialId={item.material_id} required onChange={(id, label) => { updateItem(index, 'material_id', id); updateItem(index, 'material_label', label); }} /></Field><Field label="Quantity" required><input className={inputClass} type="number" min="0.01" step="0.01" value={item.quantity} onChange={(event) => updateItem(index, 'quantity', event.target.value)} /></Field><Field label="Line note"><input className={inputClass} value={item.notes} onChange={(event) => updateItem(index, 'notes', event.target.value)} /></Field><Button type="button" variant="ghost" size="sm" onClick={() => setForm({ ...form, items: form.items.filter((_, itemIndex) => itemIndex !== index) })}>Remove</Button></div>)}<Button type="button" variant="secondary" onClick={() => setForm({ ...form, items: [...form.items, { material_id: '', material_label: '', quantity: '', notes: '' }] })}>Add item</Button></CardContent></Card>{!draft ? <Field label="What was corrected" required><textarea className={inputClass} rows={3} value={form.correction_summary} onChange={(event) => setForm({ ...form, correction_summary: event.target.value })} placeholder="Explain how the requested correction was addressed." /></Field> : null}<Button loading={pending} loadingLabel={draft ? 'Saving draft' : 'Saving correction'} disabled={!valid}>{draft ? 'Save draft changes' : 'Save correction'}</Button></> : null}
    </form>
  </FormModal>;
}

function FinanceSubmissionModal({ request, pending, onClose, onSubmit }: { request: PurchaseRequest | null; pending: boolean; onClose: () => void; onSubmit: (budgetLine: number | null, comments: string) => void }) {
  const budgets = useQuery({
    queryKey: qk.financeBudgets({ project: request?.project, status: 'APPROVED' }),
    queryFn: () => financeApi.budgets({ project: request!.project, status: 'APPROVED', page_size: 20 }),
    enabled: !!request?.project,
  });
  const [budgetLine, setBudgetLine] = useState('');
  const [comments, setComments] = useState('');
  const lines = budgets.data?.results.flatMap((budget) => budget.lines.map((line) => ({ ...line, budgetName: budget.name }))) || [];
  return <FormModal open={!!request} title={`Send quoted PO ${request?.number || 'request'} to Finance`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onSubmit(budgetLine ? Number(budgetLine) : null, comments); }}>
      <p className="border border-border bg-background p-3 text-sm">Quoted PO total for Finance review: <strong>{formatUGX(request?.total_estimated_cost)}</strong></p>
      <Field label="Budget authorization">
        <select className={inputClass} value={budgetLine} onChange={(event) => setBudgetLine(event.target.value)}>
          <option value="">Unbudgeted request - Finance Manager override required</option>
          {lines.map((line) => <option key={line.id} value={line.id}>{line.budgetName} / {line.category_code} / available {formatUGX(line.available_balance)}</option>)}
        </select>
      </Field>
      <Field label="Submission comments"><textarea className={inputClass} rows={3} value={comments} onChange={(event) => setComments(event.target.value)} /></Field>
      <Button loading={pending} loadingLabel="Sending quoted PO">Send quoted PO for Finance review</Button>
    </form>
  </FormModal>;
}

function PartialStockIssueModal({ request, pending, onClose, onSubmit }: { request: PurchaseRequest | null; pending: boolean; onClose: () => void; onSubmit: (items: Array<{ purchase_request_item: number; quantity: string }>) => void }) {
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  useEffect(() => {
    setQuantities(Object.fromEntries((request?.items || []).map((item) => [item.id, String(Math.min(Number(item.warehouse_available), Number(item.outstanding_quantity)))])));
  }, [request]);
  const lines = (request?.items || []).map((item) => ({ ...item, issue_now: quantities[item.id] || '0' }));
  const valid = lines.some((item) => Number(item.issue_now) > 0) && lines.every((item) => Number(item.issue_now) >= 0 && Number(item.issue_now) <= Number(item.warehouse_available) && Number(item.issue_now) <= Number(item.outstanding_quantity));
  return <FormModal open={!!request} title={`Issue available stock / ${request?.number || ''}`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); if (valid) onSubmit(lines.filter((item) => Number(item.issue_now) > 0).map((item) => ({ purchase_request_item: item.id, quantity: item.issue_now }))); }}>
      <p className="border border-info/20 bg-info/5 p-3 text-sm text-muted">Issue only what physically leaves the warehouse. Any balance stays on the request and Procurement can create a PO only for that remaining quantity.</p>
      {lines.map((item) => {
        const exceeds = Number(item.issue_now) > Number(item.warehouse_available) || Number(item.issue_now) > Number(item.outstanding_quantity);
        return <div key={item.id} className="grid gap-3 border border-border bg-background p-3 md:grid-cols-[1fr_120px]">
          <div><strong>{item.material_name}</strong><p className="mt-1 text-xs text-muted">Requested: {item.quantity} {item.unit} | previously issued: {item.issued_quantity} | outstanding: {item.outstanding_quantity} | default warehouse available: {item.warehouse_available}</p></div>
          <Field label="Issue now" error={exceeds ? 'Cannot exceed available or outstanding quantity.' : undefined}><input className={inputClass} type="number" min="0" max={Math.min(Number(item.warehouse_available), Number(item.outstanding_quantity))} step="0.01" value={item.issue_now} onChange={(event) => setQuantities((current) => ({ ...current, [item.id]: event.target.value }))} /></Field>
        </div>;
      })}
      <Button loading={pending} loadingLabel="Issuing stock" disabled={!valid}>Issue selected quantities</Button>
    </form>
  </FormModal>;
}

type FinanceDecision = 'approve' | 'reject' | 'return' | 'hold';

function FinanceReviewModal({ request, pending, role, onClose, onSubmit }: { request: PurchaseRequest | null; pending: boolean; role: string | null; onClose: () => void; onSubmit: (decision: FinanceDecision, comments: string, override: boolean) => void }) {
  const budgets = useQuery({
    queryKey: qk.financeBudgets({ project: request?.project, status: 'APPROVED' }),
    queryFn: () => financeApi.budgets({ project: request!.project, status: 'APPROVED', page_size: 20 }),
    enabled: !!request?.project,
  });
  const [decision, setDecision] = useState<FinanceDecision>('approve');
  const [comments, setComments] = useState('');
  const [override, setOverride] = useState(false);
  const commentsRequired = decision !== 'approve' || override;
  const budgetLine = budgets.data?.results.flatMap((budget) => budget.lines.map((line) => ({ budget, line }))).find(({ line }) => line.id === request?.finance_budget_line);
  const requestAmount = Number(request?.total_estimated_cost || 0);
  const lineAvailableAfter = budgetLine ? Number(budgetLine.line.available_balance) - requestAmount : null;
  const projectAvailableAfter = budgetLine ? Number(budgetLine.budget.available_balance) - requestAmount : null;
  const needsOverride = !budgetLine || (lineAvailableAfter !== null && lineAvailableAfter < 0);
  const canAuthorizeOverride = role === 'finance_manager' || role === 'admin';
  return <FormModal open={!!request} title={`Finance review / ${request?.number || 'request'}`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onSubmit(decision, comments, override); }}>
      <div className="grid gap-2 border border-border bg-background p-3 text-sm md:grid-cols-2"><span>Project <strong className="block">{request?.project_name || 'No project'}</strong></span><span>Quoted PO total <strong className="block">{formatUGX(request?.total_estimated_cost)}</strong></span></div>
      {budgets.isLoading ? <p className="border border-border bg-background p-3 text-sm text-muted">Loading approved project budget position…</p> : null}
      {!budgets.isLoading && budgetLine ? <section className="grid gap-3 border border-primary/25 bg-primary/5 p-3">
        <div><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-primary">Approval impact</p><strong>{budgetLine.budget.name} / {budgetLine.line.category_name}</strong><p className="text-xs text-muted">This is the approved project budget and selected authorization line for this request.</p></div>
        <div className="grid gap-2 text-sm sm:grid-cols-3"><span>Project revised budget<strong className="mt-1 block">{formatUGX(budgetLine.budget.revised_budget)}</strong></span><span>Project commitments<strong className="mt-1 block">{formatUGX(budgetLine.budget.open_commitments)}</strong></span><span>Project actual spend<strong className="mt-1 block">{formatUGX(budgetLine.budget.actual_expenditure)}</strong></span></div>
        <div className="grid gap-2 border-t border-primary/20 pt-3 text-sm sm:grid-cols-2"><span>Selected line available now<strong className="mt-1 block">{formatUGX(budgetLine.line.available_balance)}</strong></span><span>Selected line after approval<strong className={`mt-1 block ${lineAvailableAfter !== null && lineAvailableAfter < 0 ? 'text-critical' : 'text-primary'}`}>{formatUGX(String(lineAvailableAfter || 0))}</strong></span><span>Project available now<strong className="mt-1 block">{formatUGX(budgetLine.budget.available_balance)}</strong></span><span>Project available after approval<strong className={`mt-1 block ${projectAvailableAfter !== null && projectAvailableAfter < 0 ? 'text-critical' : 'text-primary'}`}>{formatUGX(String(projectAvailableAfter || 0))}</strong></span></div>
      </section> : null}
      {!budgets.isLoading && !budgetLine ? <p className="border border-warning/30 bg-warning/5 p-3 text-sm text-foreground">No approved budget line is attached to this request. Approval requires a documented Finance Manager override.</p> : null}
      <Field label="Decision" required><select className={inputClass} value={decision} onChange={(event) => { setDecision(event.target.value as FinanceDecision); setOverride(false); }}><option value="approve">Approve</option><option value="return">Return for correction</option><option value="hold">Place on hold</option><option value="reject">Reject</option></select></Field>
      {decision === 'approve' && canAuthorizeOverride ? <label className={`flex items-center gap-2 border p-3 text-sm font-semibold ${needsOverride ? 'border-warning/40 bg-warning/5' : 'border-border'}`}><input type="checkbox" checked={override} onChange={(event) => setOverride(event.target.checked)} />{needsOverride ? 'Authorize required budget override and document the reason' : 'Authorize budget override if the available balance is insufficient'}</label> : null}
      {decision === 'approve' && needsOverride && !canAuthorizeOverride ? <p className="border border-warning/30 bg-warning/5 p-3 text-sm">This request exceeds available budget. A Finance Manager or Admin must authorize the exception.</p> : null}
      <Field label="Review comments" required={commentsRequired}><textarea className={inputClass} rows={4} value={comments} onChange={(event) => setComments(event.target.value)} /></Field>
      <Button loading={pending} loadingLabel="Recording decision" variant={decision === 'reject' ? 'warning' : 'default'} disabled={(commentsRequired && !comments.trim()) || (decision === 'approve' && needsOverride && (!override || !canAuthorizeOverride))}>Confirm finance decision</Button>
    </form>
  </FormModal>;
}
