import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, CircleDollarSign, CornerUpLeft, PackageOpen, Pencil, Plus, Send, Trash2, X } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { financeApi } from '@/modules/finance/api';
import { api } from '@/modules/procurement/api';
import { getTokens } from '@/api/client';
import { offlineScope, queueOfflineAction } from '@/pwa/offline';
import type { PurchaseRequest } from '@/modules/procurement/types';
import { qk } from '@/api/queryKeys';
import { can, hasRole } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { ExportButton } from '@/components/common/export-button';
import { MaterialLookup } from '@/components/common/material-lookup';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';

const draftKey = 'construct.pr.draft';

export function ProcurementRequestsPage() {
  const { role, user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const toast = useToast();
  const queryClient = useQueryClient();
  const list = useListState({ status: '', priority: '', project: '', action_queue: searchParams.get('action_queue') || '' });
  const [open, setOpen] = useState(false);
  const [rejecting, setRejecting] = useState<PurchaseRequest | null>(null);
  const [returning, setReturning] = useState<PurchaseRequest | null>(null);
  const [financeSubmission, setFinanceSubmission] = useState<PurchaseRequest | null>(null);
  const [financeDecision, setFinanceDecision] = useState<PurchaseRequest | null>(null);
  const [correcting, setCorrecting] = useState<PurchaseRequest | null>(null);
  const [editingDraft, setEditingDraft] = useState<PurchaseRequest | null>(null);
  const [stockIssueReview, setStockIssueReview] = useState<PurchaseRequest | null>(null);
  const [issuingStock, setIssuingStock] = useState<PurchaseRequest | null>(null);
  const requests = useQuery({ queryKey: list.filters.action_queue ? qk.purchaseRequestActionQueue(list.query) : qk.purchaseRequests(list.query), queryFn: () => api.purchaseRequests(list.query) });
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
    const actionScore = (request: PurchaseRequest) => requestNeedsAction(request) ? 0 : 1;
    return actionScore(a) - actionScore(b);
  });

  const columns: ColumnDef<PurchaseRequest>[] = [
    {
      header: 'Request',
      cell: ({ row }) => (
        <div>
          <strong className="block truncate">{row.original.number}</strong>
          <p className="text-sm text-muted">{row.original.title}</p>
          <p className="text-xs text-muted">{row.original.project_name || 'No project'} · {row.original.requested_by_username} · {formatDate(row.original.created_at)}</p>
        </div>
      ),
    },
    { header: 'Status', cell: ({ row }) => <div><Badge tone={statusTone(row.original.status)}>{row.original.status_display}</Badge><p className="mt-1 max-w-[260px] text-xs text-muted">{row.original.next_action_message}</p></div> },
    { header: 'Priority', cell: ({ row }) => <Badge tone={statusTone(row.original.priority)}>{row.original.priority_display}</Badge> },
    {
      header: 'Finance',
      cell: ({ row }) => (
        <div>
          <Badge tone={statusTone(row.original.finance_status)}>{row.original.finance_status_display}</Badge>
          {row.original.finance_return_reason ? <p className="mt-1 max-w-48 truncate text-xs font-semibold text-warning" title={row.original.finance_return_reason}>Return: {row.original.finance_return_reason}</p> : row.original.finance_review_reason ? <p className="mt-1 max-w-48 truncate text-xs text-muted" title={row.original.finance_review_reason}>{row.original.finance_review_reason}</p> : null}
        </div>
      ),
    },
    {
      header: 'Warehouse available',
      cell: ({ row }) => (
        <div className="grid gap-1 text-xs">
          {row.original.items.slice(0, 2).map((item) => {
            const available = Number(item.warehouse_available);
            const needed = Number(item.outstanding_quantity);
            return <span key={item.id} className={available >= needed ? 'text-primary' : available > 0 ? 'text-warning' : 'text-critical'}>{item.material_code}: {formatNumber(item.warehouse_available)}/{formatNumber(item.outstanding_quantity)} {item.unit}</span>;
          })}
          {row.original.items.length > 2 ? <span className="text-muted">+{row.original.items.length - 2} more</span> : null}
        </div>
      ),
    },
    { header: 'Estimate', cell: ({ row }) => <span className="whitespace-nowrap font-semibold">{formatUGX(row.original.total_estimated_cost)}</span> },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex flex-wrap justify-end gap-2">
          {hasRole(role, ['admin', 'site_engineer', 'procurement_officer']) && row.original.status === 'PENDING' && (role === 'admin' || row.original.requested_by === user?.id) ? <>
            <Button size="sm" variant="secondary" onClick={() => setEditingDraft(row.original)}><Pencil className="h-4 w-4" />Edit draft</Button>
            <Button size="sm" variant="ghost" onClick={() => { if (window.confirm(`Delete ${row.original.number}? This draft will be removed and audited.`)) deleteDraft.mutate(row.original.id); }}><Trash2 className="h-4 w-4" />Delete draft</Button>
          </> : null}
          {can.approvePr(role) && row.original.status === 'PENDING' ? (
            <>
              <Button size="sm" title="Review the project, justification, materials and quantities before approving" onClick={() => approve.mutate(row.original.id)}><Check className="h-4 w-4" />Approve</Button>
              <Button size="sm" variant="secondary" onClick={() => setReturning(row.original)}><CornerUpLeft className="h-4 w-4" />Return</Button>
              <Button size="sm" variant="secondary" onClick={() => setRejecting(row.original)}><X className="h-4 w-4" />Reject</Button>
            </>
          ) : null}
          {row.original.can_approve_stock_issue ? (
            <Button size="sm" onClick={() => approveStockIssue.mutate(row.original.id)} disabled={approveStockIssue.isPending}>
              <Check className="h-4 w-4" />Approve stock issue
            </Button>
          ) : null}
          {hasRole(role, ['procurement_officer', 'admin']) && row.original.can_request_stock_issue ? (
            <Button size="sm" variant="secondary" onClick={() => setStockIssueReview(row.original)}><Send className="h-4 w-4" />Request issue</Button>
          ) : null}
          {role === 'procurement_officer' && row.original.status === 'APPROVED' && !row.original.can_request_stock_issue && !row.original.has_purchase_order ? <span className="self-center text-xs font-semibold text-warning">Awaiting Admin approval for stock issue</span> : null}
          {hasRole(role, ['storekeeper', 'admin']) && row.original.can_fulfill_from_stock ? (
            <Button size="sm" onClick={() => setIssuingStock(row.original)}><PackageOpen className="h-4 w-4" />Issue available stock</Button>
          ) : null}
          {can.submitPrToFinance(role) && row.original.can_submit_finance && row.original.has_purchase_order ? (
            <Button size="sm" variant="secondary" onClick={() => setFinanceSubmission(row.original)}><CircleDollarSign className="h-4 w-4" />Send quoted PO to finance</Button>
          ) : null}
          {can.createPo(role) && row.original.can_create_purchase_order ? (
            <Button size="sm" onClick={() => navigate('/procurement/purchase-orders', { state: { purchaseRequestId: row.original.id } })}><PackageOpen className="h-4 w-4" />{row.original.status === 'PARTIAL_STOCK_ISSUED' ? 'Source balance' : 'Create PO'}</Button>
          ) : null}
          {row.original.can_correct_return ? <Button size="sm" variant="secondary" onClick={() => setCorrecting(row.original)}>Correct request</Button> : null}
          {can.reviewPrFinance(role) && ['SUBMITTED', 'HOLD'].includes(row.original.finance_status) ? (
            <Button size="sm" onClick={() => setFinanceDecision(row.original)}><CircleDollarSign className="h-4 w-4" />Finance review</Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <div className="grid gap-3 sm:gap-4">
      <PageToolbar title="Purchase requests" subtitle="Create and route project material requests." search={list.search} onSearch={list.setSearch}>
        <select className={inputClass} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}>
          <option value="">All statuses</option>
          <option value="PENDING">Pending</option>
          <option value="APPROVED">Approved</option>
          <option value="STOCK_ISSUE_REQUESTED">Issue requested</option>
          <option value="PARTIAL_STOCK_ISSUED">Partially issued</option>
          <option value="STOCK_ISSUED">Stock issued</option>
          <option value="PO_CREATED">PO created</option>
          <option value="REJECTED">Rejected</option>
        </select>
        <select className={inputClass} value={list.filters.priority} onChange={(event) => list.setFilter('priority', event.target.value)}>
          <option value="">All priorities</option>
          <option value="LOW">Low</option>
          <option value="NORMAL">Normal</option>
          <option value="HIGH">High</option>
          <option value="URGENT">Urgent</option>
        </select>
        <ExportButton label="PDF" onClick={() => void api.downloadPurchaseRequests('pdf', { ...list.filters, search: list.search })} />
        <ExportButton label="Excel" onClick={() => void api.downloadPurchaseRequests('xlsx', { ...list.filters, search: list.search })} />
        {can.submitPr(role) || can.submitWarehouseReplenishment(role) ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />{can.submitWarehouseReplenishment(role) && !can.submitPr(role) ? 'Warehouse replenishment' : 'New PR'}</Button> : null}
      </PageToolbar>
      <div className="border border-info/25 bg-info/5 p-3 text-sm text-foreground"><strong>Manager review required before approval.</strong><p className="mt-1 text-muted">The Project Manager must review the project, justification, priority, requested quantities, materials, and warehouse availability before approving. Incomplete or inaccurate requests should be returned for correction.</p></div>
      {hasRole(role, ['storekeeper', 'admin', 'procurement_officer']) ? <div className="border border-primary/25 bg-primary/[0.045] p-3 text-sm text-foreground"><strong>Stock issue workflow</strong><p className="mt-1 text-muted">For project requests, the sequence is: Manager approval → Admin stock-issue approval → Procurement selects <strong>Request issue</strong> → Storekeeper selects <strong>Issue available stock</strong>. Warehouse replenishment requests must use a purchase order and will not show this action.</p></div> : null}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div className="rounded-xl border border-border/80 bg-white px-3 py-2.5 shadow-sm"><p className="text-[10px] font-bold uppercase tracking-wide text-muted">On this page</p><strong className="mt-0.5 block text-lg font-black">{requestRows.length}</strong></div>
        <div className="rounded-xl border border-warning/25 bg-warning/5 px-3 py-2.5 shadow-sm"><p className="text-[10px] font-bold uppercase tracking-wide text-warning">Needs action</p><strong className="mt-0.5 block text-lg font-black text-foreground">{requestRows.filter(requestNeedsAction).length}</strong></div>
        <div className="col-span-2 rounded-xl border border-primary/15 bg-primary/[0.025] px-3 py-2.5 shadow-sm sm:col-span-1"><p className="text-[10px] font-bold uppercase tracking-wide text-primary">Queue order</p><p className="mt-0.5 truncate text-sm font-semibold">Action first · newest context below</p></div>
      </div>
      <DataTable columns={columns} data={requestRows} mobileSummaryCells={2} mobileSummaryStacked mobileCardClassName="request-card" emptyTitle={requests.isLoading ? 'Loading requests...' : 'No purchase requests found'} />
      <Pagination page={list.page} setPage={list.setPage} data={requests.data} />
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
