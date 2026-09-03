import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, CheckCircle2, FilePenLine, Plus, Trash2, Truck, X } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '@/modules/procurement/api';
import type { PurchaseOrder, PurchaseOrderAmendment, PurchaseRequest } from '@/modules/procurement/types';
import { qk } from '@/api/queryKeys';
import { can, canReceivePurchaseOrder, hasRole } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { ExportButton } from '@/components/common/export-button';
import { SupplierLookup } from '@/components/common/supplier-lookup';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatUGX } from '@/lib/utils';

type PurchaseOrderItemDraft = {
  material_id: string;
  material_label: string;
  quantity: string;
  reference_unit_price: string;
  unit_price: string;
  notes: string;
};

const parseQuotedPrice = (value: string) => Number(value.replaceAll(',', '').trim());

export function PurchaseOrdersPage() {
  const { role } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const requestedPurchaseRequestId = (location.state as { purchaseRequestId?: number } | null)?.purchaseRequestId;
  const toast = useToast();
  const queryClient = useQueryClient();
  const list = useListState({ status: '', project: '', purchase_request: '', action_queue: new URLSearchParams(location.search).get('action_queue') || '' });
  const [open, setOpen] = useState(Boolean(requestedPurchaseRequestId));
  const [cancelling, setCancelling] = useState<PurchaseOrder | null>(null);
  const [amending, setAmending] = useState<PurchaseOrder | null>(null);
  const [decidingAmendment, setDecidingAmendment] = useState<{ order: PurchaseOrder; amendment: PurchaseOrderAmendment; approve: boolean } | null>(null);
  const [reviewingPreapproval, setReviewingPreapproval] = useState<{ order: PurchaseOrder; amendment: PurchaseOrderAmendment; canConfirm: boolean } | null>(null);
  const orders = useQuery({ queryKey: list.filters.action_queue ? qk.purchaseOrderActionQueue(list.query) : qk.purchaseOrders(list.query), queryFn: () => api.purchaseOrders(list.query) });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] });
    void queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
    void queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
    void queryClient.invalidateQueries({ queryKey: ['materials'] });
    void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    void queryClient.invalidateQueries({ queryKey: qk.workflowBadges });
    void queryClient.invalidateQueries({ queryKey: ['finance'] });
    void queryClient.invalidateQueries({ queryKey: ['purchase-order-amendments'] });
  };
  const confirmDispatch = useMutation({
    mutationFn: api.confirmDispatch,
    onSuccess: () => { toast.push({ title: 'Supplier dispatch confirmed', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Dispatch confirmation failed', message: error.message, tone: 'danger' }),
  });
  const receive = useMutation({
    mutationFn: api.receivePurchaseOrder,
    onSuccess: () => { toast.push({ title: 'Purchase order received', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Receipt failed', message: error.message, tone: 'danger' }),
  });
  const approve = useMutation({
    mutationFn: api.approvePurchaseOrder,
    onSuccess: () => { toast.push({ title: 'Purchase order approved and commitment recorded', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'PO approval failed', message: error.message, tone: 'danger' }),
  });
  const cancel = useMutation({
    mutationFn: ({ id, comments }: { id: number; comments: string }) => api.cancelPurchaseOrder(id, comments),
    onSuccess: () => { toast.push({ title: 'Purchase order cancelled and commitment released', tone: 'warning' }); setCancelling(null); refresh(); },
    onError: (error: Error) => toast.push({ title: 'PO cancellation failed', message: error.message, tone: 'danger' }),
  });
  const deleteDraft = useMutation({
    mutationFn: api.deletePurchaseOrder,
    onSuccess: () => { toast.push({ title: 'Draft purchase order deleted', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not delete purchase order', message: error.message, tone: 'danger' }),
  });
  const amendments = useQuery({ queryKey: ['purchase-order-amendments'], queryFn: async () => {
    const rows = orders.data?.results || [];
    const results = await Promise.all(rows.map(async (order) => [order.id, await api.purchaseOrderAmendments(order.id)] as const));
    return new Map(results);
  }, enabled: Boolean(orders.data?.results?.length) });

  const orderNeedsAction = (order: PurchaseOrder) => (
    (can.createPo(role) && ['DRAFT', 'PENDING'].includes(order.status))
    || (can.createPo(role) && order.delivery_destination === 'SITE' && ['ORDERED', 'PARTIAL'].includes(order.status))
    || canReceivePurchaseOrder(role, order)
    || (can.createPo(role) && !['RECEIVED', 'CANCELLED'].includes(order.status))
    || (hasRole(role, ['procurement_officer', 'admin']) && ['DRAFT', 'PENDING', 'ORDERED'].includes(order.status))
    || Boolean(order.pending_preapproval_edit && hasRole(role, ['finance_officer', 'finance_manager', 'admin']))
  );
  const orderRows = [...(orders.data?.results || [])].sort((a, b) => Number(orderNeedsAction(b)) - Number(orderNeedsAction(a)));

  const columns: ColumnDef<PurchaseOrder>[] = [
    {
      header: 'Order',
      cell: ({ row }) => (
        <div>
          <strong>{row.original.number}</strong>
          <p className="text-sm text-muted">{row.original.supplier_name}</p>
          <p className="text-xs text-muted">{row.original.purchase_request_number || 'Manual PO'}</p>
        </div>
      ),
    },
    { header: 'Project', cell: ({ row }) => row.original.project_name || 'Warehouse' },
    { header: 'Destination', cell: ({ row }) => <Badge tone={row.original.delivery_destination === 'SITE' ? 'info' : 'success'}>{row.original.delivery_destination_display}</Badge> },
    { header: 'Delivery', cell: ({ row }) => <div><strong className="text-sm">{row.original.revised_delivery_date ? formatDate(row.original.revised_delivery_date) : row.original.supplier_confirmed_delivery_date ? formatDate(row.original.supplier_confirmed_delivery_date) : row.original.expected_delivery_date ? formatDate(row.original.expected_delivery_date) : 'Not committed'}</strong><p className="text-xs text-muted">{row.original.delivery_follow_up_owner_name || 'Procurement follow-up'}</p>{row.original.is_overdue ? <Badge tone="danger">Overdue</Badge> : null}</div> },
    { header: 'Status', cell: ({ row }) => <div className="grid justify-items-start gap-1"><Badge tone={statusTone(row.original.status)}>{row.original.status_display}</Badge>{row.original.pending_preapproval_edit ? <Badge tone="warning">Finance review required</Badge> : null}<p className="max-w-[220px] text-xs text-muted">{poNextAction(row.original, role)}</p></div> },
    { header: 'Total', cell: ({ row }) => formatUGX(row.original.total_cost) },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex flex-wrap justify-end gap-2">
          {can.createPo(role) && ['DRAFT', 'PENDING'].includes(row.original.status) ? (
            <Button size="sm" loading={approve.isPending && approve.variables === row.original.id} loadingLabel="Approving" disabled={approve.isPending} onClick={() => approve.mutate(row.original.id)}><Check className="h-4 w-4" />Approve PO</Button>
          ) : null}
          {can.createPo(role) && row.original.delivery_destination === 'SITE' && ['ORDERED', 'PARTIAL'].includes(row.original.status) ? (
            <Button variant="secondary" size="sm" onClick={() => confirmDispatch.mutate(row.original.id)}><Truck className="h-4 w-4" />Confirm dispatch</Button>
          ) : null}
          {canReceivePurchaseOrder(role, row.original) ? (
            <Button size="sm" onClick={() => receive.mutate(row.original.id)}><CheckCircle2 className="h-4 w-4" />Confirm receipt</Button>
          ) : null}
          {can.createPo(role) && !['RECEIVED', 'CANCELLED'].includes(row.original.status) ? (
            <Button size="sm" variant="ghost" onClick={() => setCancelling(row.original)}><X className="h-4 w-4" />Cancel</Button>
          ) : null}
          {hasRole(role, ['procurement_officer', 'admin']) && ['DRAFT', 'PENDING', 'ORDERED'].includes(row.original.status) ? (
            <Button size="sm" variant="secondary" onClick={() => setAmending(row.original)}><FilePenLine className="h-4 w-4" />{['DRAFT', 'PENDING'].includes(row.original.status) ? 'Edit PO' : 'Amend'}</Button>
          ) : null}
          {hasRole(role, ['procurement_officer', 'admin']) && row.original.status === 'DRAFT' ? <Button size="sm" variant="ghost" onClick={() => { if (window.confirm(`Delete ${row.original.number}? This draft will be removed and audited.`)) deleteDraft.mutate(row.original.id); }}><Trash2 className="h-4 w-4" />Delete draft</Button> : null}
          {hasRole(role, ['finance_officer', 'finance_manager', 'admin']) ? (amendments.data?.get(row.original.id) || []).filter((item) => item.status === 'SUBMITTED').map((item) => item.amendment_type === 'PRE_APPROVAL_EDIT' ? (
            <Button key={item.id} size="sm" variant="warning" onClick={() => setReviewingPreapproval({ order: row.original, amendment: item, canConfirm: hasRole(role, ['finance_manager', 'admin']) })}>{hasRole(role, ['finance_manager', 'admin']) ? 'Review edited PO' : 'View edited PO'}</Button>
          ) : hasRole(role, ['finance_manager', 'admin']) ? <Button key={item.id} size="sm" variant="warning" onClick={() => setDecidingAmendment({ order: row.original, amendment: item, approve: true })}>Review v{item.version}</Button> : null) : null}
          {hasRole(role, ['finance_officer', 'finance_manager', 'admin']) && row.original.status === 'PENDING' && row.original.purchase_request_number ? <Button size="sm" variant="warning" onClick={() => navigate(`/procurement/requests?search=${encodeURIComponent(row.original.purchase_request_number || '')}`)}><Check className="h-4 w-4" />Finance review</Button> : null}
        </div>
      ),
    },
  ];

  return (
    <div className="grid gap-3 sm:gap-4">
      <PageToolbar title="Purchase orders" subtitle="Orders, warehouse receiving and direct-to-site dispatch/receipt workflow." search={list.search} onSearch={list.setSearch}>
        <select className={inputClass} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}>
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="PENDING">Pending</option>
          <option value="ORDERED">Ordered</option>
          <option value="DISPATCH_CONFIRMED">Dispatch confirmed</option>
          <option value="RECEIVED">Received</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
        <ExportButton label="PDF" onClick={() => void api.downloadPurchaseOrders('pdf', { ...list.filters, search: list.search })} />
        <ExportButton label="Excel" onClick={() => void api.downloadPurchaseOrders('xlsx', { ...list.filters, search: list.search })} />
        {can.createPo(role) ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New PO</Button> : null}
      </PageToolbar>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div className="rounded-xl border border-border/80 bg-white px-3 py-2.5 shadow-sm"><p className="text-[10px] font-bold uppercase tracking-wide text-muted">On this page</p><strong className="mt-0.5 block text-lg font-black">{orderRows.length}</strong></div>
        <div className="rounded-xl border border-warning/25 bg-warning/5 px-3 py-2.5 shadow-sm"><p className="text-[10px] font-bold uppercase tracking-wide text-warning">Needs action</p><strong className="mt-0.5 block text-lg font-black">{orderRows.filter(orderNeedsAction).length}</strong></div>
        <div className="col-span-2 rounded-xl border border-primary/15 bg-primary/[0.025] px-3 py-2.5 shadow-sm sm:col-span-1"><p className="text-[10px] font-bold uppercase tracking-wide text-primary">Queue order</p><p className="mt-0.5 truncate text-sm font-semibold">Action first · delivery context below</p></div>
      </div>
      <DataTable columns={columns} data={orderRows} mobileSummaryCells={2} mobileSummaryStacked mobileCardClassName="request-card" emptyTitle={orders.isLoading ? 'Loading purchase orders...' : 'No purchase orders found'} />
      <Pagination page={list.page} setPage={list.setPage} data={orders.data} />
      {hasRole(role, ['procurement_officer', 'admin']) ? <PurchaseOrderModal open={open} onClose={() => setOpen(false)} initialPurchaseRequestId={requestedPurchaseRequestId} /> : null}
      <CancelPurchaseOrderModal order={cancelling} pending={cancel.isPending} onClose={() => setCancelling(null)} onCancel={(comments) => cancelling && cancel.mutate({ id: cancelling.id, comments })} />
      <PurchaseOrderAmendmentModal order={amending} onClose={() => setAmending(null)} onDone={refresh} />
      <PurchaseOrderAmendmentDecisionModal state={decidingAmendment} onClose={() => setDecidingAmendment(null)} onDone={refresh} />
      <PreApprovalEditReviewModal state={reviewingPreapproval} onClose={() => setReviewingPreapproval(null)} onDone={refresh} />
    </div>
  );
}

function poNextAction(order: PurchaseOrder, role: ReturnType<typeof useAuth>['role']) {
  if (order.pending_preapproval_edit && hasRole(role, ['finance_officer', 'finance_manager', 'admin'])) return 'Review the edited PO before it proceeds.';
  if (['DRAFT', 'PENDING'].includes(order.status) && can.createPo(role)) return 'Approve the PO or adjust it before approval.';
  if (order.delivery_destination === 'SITE' && ['ORDERED', 'PARTIAL'].includes(order.status) && can.createPo(role)) return 'Confirm dispatch to the project site.';
  if (canReceivePurchaseOrder(role, order)) return order.delivery_destination === 'SITE' ? 'Confirm the site receipt.' : 'Confirm the warehouse receipt.';
  if (order.is_overdue) return 'Follow up the overdue supplier delivery.';
  if (order.status === 'RECEIVED') return 'Receipt complete; continue with invoice matching.';
  return 'Monitor delivery and invoice progress.';
}

function PurchaseOrderModal({ open, onClose, initialPurchaseRequestId }: { open: boolean; onClose: () => void; initialPurchaseRequestId?: number }) {
  const approvedPrs = useQuery({
    queryKey: qk.purchaseRequests({ page_size: 100 }),
    queryFn: () => api.purchaseRequests({ page_size: 100 }),
  });
  const [supplier, setSupplier] = useState({ id: '', label: '' });
  const [deliveryDestination, setDeliveryDestination] = useState<'WAREHOUSE' | 'SITE'>('WAREHOUSE');
  const [purchaseRequest, setPurchaseRequest] = useState('');
  const [notes, setNotes] = useState('');
  const [expectedDeliveryDate, setExpectedDeliveryDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [items, setItems] = useState<PurchaseOrderItemDraft[]>([]);
  const queryClient = useQueryClient();
  const toast = useToast();
  const remainingItems = (request: PurchaseRequest) => request.items.filter((item) => Number(item.outstanding_quantity) > 0);
  const eligiblePrs = (approvedPrs.data?.results || []).filter((request) =>
    ['APPROVED', 'PARTIAL_STOCK_ISSUED'].includes(request.status)
    && request.can_create_purchase_order
    && remainingItems(request).length > 0,
  );
  const selectedPr = eligiblePrs.find((request) => String(request.id) === purchaseRequest);

  useEffect(() => {
    if (open && initialPurchaseRequestId) setPurchaseRequest(String(initialPurchaseRequestId));
  }, [open, initialPurchaseRequestId]);

  useEffect(() => {
    if (!selectedPr) return;
    setDeliveryDestination(selectedPr.project ? 'SITE' : 'WAREHOUSE');
    setItems(remainingItems(selectedPr).map((item) => ({
      material_id: String(item.material),
      material_label: `${item.material_name} (${item.material_code})`,
      quantity: item.outstanding_quantity,
      reference_unit_price: item.unit_price,
      unit_price: item.unit_price,
      notes: item.notes,
    })));
  }, [selectedPr]);

  const mutation = useMutation<PurchaseOrder>({
    mutationFn: async () => {
      let supplierId = supplier.id;
      if (!supplierId && supplier.label.trim()) {
        const matches = await api.suppliers({ search: supplier.label.trim(), is_active: true, page_size: 20 });
        const match = matches.results.find((item) => item.name.toLowerCase() === supplier.label.trim().toLowerCase());
        supplierId = match ? String(match.id) : '';
      }
      if (!supplierId) throw new Error('Choose an active supplier from the lookup results.');
      const body = {
        supplier: Number(supplierId),
        delivery_destination: deliveryDestination,
        project: selectedPr?.project || null,
        notes,
        expected_delivery_date: expectedDeliveryDate,
        status: 'PENDING',
        items: items.map((item) => ({
          material: Number(item.material_id),
          quantity: item.quantity,
          unit_price: parseQuotedPrice(item.unit_price),
          notes: item.notes,
        })),
      };
      if (purchaseRequest) {
        return api.createPurchaseOrderFromPr(Number(purchaseRequest), body);
      }
      throw new Error('Select a manager-approved purchase request. Supplier pricing is entered here before Finance review.');
    },
    onSuccess: () => {
      toast.push({ title: 'Purchase order created', tone: 'success' });
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] });
      void queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
    },
    onError: (error: Error) => toast.push({ title: 'Could not create PO', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title="Create purchase order" onClose={onClose}>
      <form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Supplier" required>
            <SupplierLookup
              label={supplier.label}
              supplierId={supplier.id}
              onChange={(id, label) => setSupplier({ id, label })}
            />
          </Field>
          <Field label="Expected delivery date" required><input className={inputClass} type="date" value={expectedDeliveryDate} onChange={(event) => setExpectedDeliveryDate(event.target.value)} /></Field>
          <Field label="Manager-approved purchase request" required>
              <select className={inputClass} value={purchaseRequest} onChange={(event) => setPurchaseRequest(event.target.value)}>
                <option value="">Select manager-approved PR</option>
                {eligiblePrs.map((request: PurchaseRequest) => <option key={request.id} value={request.id}>{request.number} - {request.title}</option>)}
              </select>
              {!approvedPrs.isLoading && !eligiblePrs.length ? <p className="mt-1 text-xs text-warning">No manager-approved request is ready for a PO. Any available warehouse stock issue must be completed first.</p> : <p className="mt-1 text-xs text-muted">{eligiblePrs.length} manager-approved request{eligiblePrs.length === 1 ? '' : 's'} ready for supplier quoting. Finance reviews the final quoted PO total before approval.</p>}
          </Field>
          <Field label="Delivery destination">
            <select className={inputClass} value={deliveryDestination} disabled={!!selectedPr && !selectedPr.project} onChange={(event) => setDeliveryDestination(event.target.value as 'WAREHOUSE' | 'SITE')}>
              <option value="WAREHOUSE">Warehouse — reserve for this project</option>
              {selectedPr?.project ? <option value="SITE">Direct to project site (recommended)</option> : null}
            </select>
          </Field>
        </div>
        {selectedPr?.project && deliveryDestination === 'WAREHOUSE' ? <p className="border border-warning/30 bg-warning/5 p-3 text-sm text-foreground">This is an exception route. After Storekeeper receipt, the stock is reserved for this project and cannot be issued to other project requests. Dispatch it to the site through Site custody for engineer acknowledgement.</p> : null}
        {selectedPr ? (
          <Card>
            <CardHeader>
              <CardTitle>
                {`Confirm items from ${selectedPr.number}`}
              </CardTitle>
              <p className="text-xs text-muted">Only quantities still outstanding after stock issue are included. Fully issued lines are excluded automatically. Materials and quantities are locked to the manager-approved request balance; enter the supplier's actual quoted prices for all remaining lines.</p>
            </CardHeader>
            <CardContent className="grid gap-2.5 p-2.5 sm:gap-3 sm:p-3">
              {items.map((item, index) => (
                <div key={index} className="grid gap-2 border border-border bg-background p-2.5 md:grid-cols-[1fr_90px_110px_120px_120px] sm:p-3">
                  <Field label="Material">
                    <input className={inputClass} value={item.material_label} readOnly />
                  </Field>
                  <Field label="Qty">
                    <input className={inputClass} type="number" value={item.quantity} readOnly aria-label={`Outstanding quantity for ${item.material_label}`} />
                  </Field>
                  <Field label="Request price">
                    <input className={inputClass} type="number" value={item.reference_unit_price} readOnly aria-label={`Reference request price for ${item.material_label}`} />
                  </Field>
                  <Field label="Supplier quote">
                    <input className={inputClass} type="text" inputMode="decimal" minLength={1} value={item.unit_price} onChange={(event) => setItems((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, unit_price: event.target.value } : row))} aria-label={`Supplier quoted unit price for ${item.material_label}`} placeholder="e.g. 48,100" />
                  </Field>
                  <div className="text-sm"><span className="block text-xs text-muted">Variance</span><strong className={parseQuotedPrice(item.unit_price) > Number(item.reference_unit_price) ? 'text-warning' : parseQuotedPrice(item.unit_price) < Number(item.reference_unit_price) ? 'text-primary' : ''}>{Number.isFinite(parseQuotedPrice(item.unit_price)) ? `${parseQuotedPrice(item.unit_price) - Number(item.reference_unit_price) >= 0 ? '+' : ''}${formatUGX(parseQuotedPrice(item.unit_price) - Number(item.reference_unit_price))}` : '—'}</strong></div>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}
        <Field label="Notes"><textarea className={inputClass} value={notes} onChange={(event) => setNotes(event.target.value)} /></Field>
        <Button
          disabled={
            !supplier.label.trim()
            || !purchaseRequest
            || !expectedDeliveryDate
            || !items.length
            || items.some((item) => !item.material_id || !item.quantity || item.unit_price.trim() === '' || !Number.isFinite(parseQuotedPrice(item.unit_price)) || parseQuotedPrice(item.unit_price) < 0)
            || mutation.isPending
          }
        >
          Create purchase order
        </Button>
      </form>
    </FormModal>
  );
}

function CancelPurchaseOrderModal({ order, pending, onClose, onCancel }: { order: PurchaseOrder | null; pending: boolean; onClose: () => void; onCancel: (comments: string) => void }) {
  const [comments, setComments] = useState('');
  return <FormModal open={!!order} title={`Cancel ${order?.number || 'purchase order'}`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onCancel(comments); }}>
      <p className="border border-border bg-background p-3 text-sm">Cancellation releases any remaining budget commitment. Received orders cannot be cancelled.</p>
      <Field label="Cancellation reason" required><textarea className={inputClass} rows={4} value={comments} onChange={(event) => setComments(event.target.value)} /></Field>
      <Button variant="warning" loading={pending} loadingLabel="Cancelling order" disabled={!comments.trim()}>Cancel purchase order</Button>
  </form>
  </FormModal>;
}

function PurchaseOrderAmendmentModal({ order, onClose, onDone }: { order: PurchaseOrder | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [reason, setReason] = useState('');
  const [expectedDate, setExpectedDate] = useState('');
  const [notes, setNotes] = useState('');
  const [priceLines, setPriceLines] = useState<Array<{ purchase_order_item: number; material_name: string; quantity: string; original_unit_price: string; unit_price: string }>>([]);
  const isPreApproval = Boolean(order && ['DRAFT', 'PENDING'].includes(order.status));
  const changedPrices = priceLines.filter((line) => line.unit_price.trim() !== '' && Number.isFinite(parseQuotedPrice(line.unit_price)) && parseQuotedPrice(line.unit_price) !== Number(line.original_unit_price));
  const hasOtherChange = notes !== (order?.notes || '') || expectedDate !== (order?.expected_delivery_date || '');
  const mutation = useMutation<PurchaseOrderAmendment | PurchaseOrder, Error, Record<string, unknown>>({
    mutationFn: (body) => {
      if (!order) throw new Error('Select a purchase order.');
      return isPreApproval ? api.editPurchaseOrderBeforeApproval(order.id, body) : api.submitPurchaseOrderAmendment(order.id, body);
    },
    onSuccess: (result) => { toast.push({ title: isPreApproval ? 'Pending PO updated before Finance approval' : `Amendment v${(result as PurchaseOrderAmendment).version} sent to Finance`, tone: 'success' }); onDone(); onClose(); },
    onError: (error: Error) => toast.push({ title: isPreApproval ? 'Could not update pending PO' : 'Could not submit amendment', message: error.message, tone: 'danger' }),
  });
  useEffect(() => { if (order) { setReason(''); setExpectedDate(order.expected_delivery_date || ''); setNotes(order.notes || ''); setPriceLines(order.items.map((item) => ({ purchase_order_item: item.id, material_name: item.material_name, quantity: item.quantity, original_unit_price: item.unit_price, unit_price: '' }))); } }, [order]);
  return <FormModal open={!!order} title={`${isPreApproval ? 'Edit' : 'Amend'} ${order?.number || 'purchase order'}`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => {
      event.preventDefault();
      if (!order) return;
      const fields = new FormData(event.currentTarget);
      const quotes = priceLines.map((line) => ({
        purchase_order_item: line.purchase_order_item,
        unit_price: String(fields.get(`quote_${line.purchase_order_item}`) || ''),
      })).filter((line) => line.unit_price.trim() !== '' && Number.isFinite(parseQuotedPrice(line.unit_price)) && parseQuotedPrice(line.unit_price) !== Number(priceLines.find((item) => item.purchase_order_item === line.purchase_order_item)?.original_unit_price));
      const body: Record<string, unknown> = isPreApproval ? {} : { reason };
      if (expectedDate && expectedDate !== order.expected_delivery_date) body.expected_delivery_date = expectedDate;
      if (notes !== (order.notes || '')) body.notes = notes;
      if (quotes.length) body.price_lines = quotes.map(({ purchase_order_item, unit_price }) => ({ purchase_order_item, unit_price: parseQuotedPrice(unit_price) }));
      if (!quotes.length && !hasOtherChange) { toast.push({ title: 'No change selected', message: 'Enter a different supplier quote, delivery date, or PO note.', tone: 'warning' }); return; }
      mutation.mutate(body);
    }}>
      <p className="rounded-lg border border-warning/25 bg-warning/5 p-3 text-sm text-foreground">{isPreApproval ? <><strong>Before first approval:</strong> Procurement may correct prices, delivery date, or notes directly. Finance will review the final PO once.</> : <><strong>Controlled change:</strong> Finance must approve this amendment. Unit-price changes retain the approved quantity and are only allowed before supplier dispatch, receipt, or invoice capture starts.</>}</p>
      {!isPreApproval ? <Field label="Reason for amendment" required><textarea className={inputClass} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></Field> : null}
      <div className="grid gap-2 rounded-lg border border-border p-3"><div><strong className="text-sm">Line price comparison</strong><p className="text-xs text-muted">Current PO prices are shown for reference. Enter a new supplier quote only for lines that changed; values such as 48,100 are accepted.</p></div>{priceLines.map((line, index) => <div key={line.purchase_order_item} className="grid gap-2 border-t border-border pt-2 sm:grid-cols-[1fr_90px_130px_130px]"><div><strong className="text-sm">{line.material_name}</strong><p className="text-xs text-muted">Approved quantity: {line.quantity}</p></div><div className="text-sm"><span className="block text-xs text-muted">Current price</span>{Number(line.original_unit_price).toLocaleString()}</div><Field label="New supplier quote"><input className={inputClass} name={`quote_${line.purchase_order_item}`} type="text" inputMode="decimal" placeholder="e.g. 48,100" value={line.unit_price} onChange={(event) => setPriceLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, unit_price: event.target.value } : item))} /></Field><div className="text-sm"><span className="block text-xs text-muted">Line variance</span>{line.unit_price.trim() && Number.isFinite(parseQuotedPrice(line.unit_price)) ? <strong className={parseQuotedPrice(line.unit_price) > Number(line.original_unit_price) ? 'text-warning' : parseQuotedPrice(line.unit_price) < Number(line.original_unit_price) ? 'text-primary' : ''}>{((parseQuotedPrice(line.unit_price) - Number(line.original_unit_price)) * Number(line.quantity)).toLocaleString()}</strong> : <span className="text-muted">—</span>}</div></div>)}<p className={changedPrices.length ? 'text-xs font-semibold text-primary' : 'text-xs font-semibold text-warning'}>{changedPrices.length ? `${changedPrices.length} price change${changedPrices.length === 1 ? '' : 's'} will be sent to Finance.` : 'Enter a genuinely new price, delivery date, or PO note before submitting.'}</p></div>
      <Field label="Revised expected delivery"><input className={inputClass} type="date" value={expectedDate} onChange={(event) => setExpectedDate(event.target.value)} /></Field>
      <Field label="Updated PO notes"><textarea className={inputClass} rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} /></Field>
      <Button disabled={(!isPreApproval && !reason.trim()) || mutation.isPending} loading={mutation.isPending} loadingLabel={isPreApproval ? 'Saving PO' : 'Sending to Finance'}>{isPreApproval ? 'Save PO changes' : 'Send amendment to Finance'}</Button>
    </form>
  </FormModal>;
}

function PreApprovalEditReviewModal({ state, onClose, onDone }: { state: { order: PurchaseOrder; amendment: PurchaseOrderAmendment; canConfirm: boolean } | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [comments, setComments] = useState('');
  const mutation = useMutation({
    mutationFn: () => state ? api.confirmPreApprovalEdit(state.order.id, comments) : Promise.reject(new Error('Select an edited PO.')),
    onSuccess: () => { toast.push({ title: 'Edited PO confirmed for approval', tone: 'success' }); onDone(); onClose(); },
    onError: (error: Error) => toast.push({ title: 'PO edit confirmation failed', message: error.message, tone: 'danger' }),
  });
  useEffect(() => { if (state) setComments(''); }, [state]);
  const proposed = (state?.amendment.proposed_values || {}) as Record<string, unknown>;
  const original = (state?.amendment.original_values || {}) as Record<string, unknown>;
  const after = (proposed.snapshot || {}) as Record<string, unknown>;
  const beforeItems = Array.isArray(original.items) ? original.items as Array<Record<string, unknown>> : [];
  const afterItems = Array.isArray(after.items) ? after.items as Array<Record<string, unknown>> : [];
  return <FormModal open={!!state} title={`Review edited ${state?.order.number || 'purchase order'}`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
      <p className="rounded-lg border border-warning/25 bg-warning/5 p-3 text-sm">Procurement changed this PO before first approval. Confirm the before/after values before the PO can be approved.</p>
      <div className="rounded-lg border border-border p-3 text-sm"><strong>Changed fields</strong><p className="mt-1 text-muted">{((proposed.changed_fields as string[]) || []).join(', ')}</p></div>
      {after.expected_delivery_date !== original.expected_delivery_date || after.notes !== original.notes ? <div className="grid gap-2 rounded-lg border border-border p-3 text-sm"><strong>PO details</strong>{after.expected_delivery_date !== original.expected_delivery_date ? <p>Delivery: {String(original.expected_delivery_date || 'Not set')} → {String(after.expected_delivery_date || 'Not set')}</p> : null}{after.notes !== original.notes ? <p>Notes: {String(original.notes || 'None')} → {String(after.notes || 'None')}</p> : null}</div> : null}
      {afterItems.length ? <div className="rounded-lg border border-border p-3 text-sm"><strong>Price changes</strong><div className="mt-2 grid gap-2">{afterItems.map((item) => { const old = beforeItems.find((candidate) => candidate.id === item.id); return old && old.unit_price !== item.unit_price ? <div key={String(item.id)} className="flex justify-between gap-2 border-t border-border pt-2"><span>{String(item.material_name)} × {String(item.quantity)}</span><strong>{formatUGX(String(old.unit_price))} → {formatUGX(String(item.unit_price))}</strong></div> : null; })}</div></div> : null}
      {state?.canConfirm ? <><Field label="Finance confirmation comments" required><textarea className={inputClass} rows={3} value={comments} onChange={(event) => setComments(event.target.value)} /></Field><Button disabled={!comments.trim() || mutation.isPending} loading={mutation.isPending}>Confirm edit and allow PO approval</Button></> : <p className="rounded-lg border border-info/25 bg-info/5 p-3 text-sm">Read-only review. Finance Manager confirmation is required before this PO can be approved.</p>}
    </form>
  </FormModal>;
}

function PurchaseOrderAmendmentDecisionModal({ state, onClose, onDone }: { state: { order: PurchaseOrder; amendment: PurchaseOrderAmendment; approve: boolean } | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [comments, setComments] = useState('');
  const [approve, setApprove] = useState(true);
  useEffect(() => { if (state) { setComments(''); setApprove(state.approve); } }, [state]);
  const mutation = useMutation<PurchaseOrder | PurchaseOrderAmendment>({
    mutationFn: () => {
      if (!state) throw new Error('Select an amendment.');
      return approve
        ? api.approvePurchaseOrderAmendment(state.order.id, state.amendment.id, comments)
        : api.rejectPurchaseOrderAmendment(state.order.id, state.amendment.id, comments);
    },
    onSuccess: () => { toast.push({ title: approve ? 'Amendment approved and budget updated' : 'Amendment rejected', tone: approve ? 'success' : 'warning' }); onDone(); onClose(); },
    onError: (error: Error) => toast.push({ title: 'Finance decision failed', message: error.message, tone: 'danger' }),
  });
  const proposed = state?.amendment.proposed_values || {};
  const priceLines = Array.isArray(proposed.price_lines) ? proposed.price_lines as Array<Record<string, unknown>> : [];
  const impact = state?.amendment.budget_impact;
  const otherChanges = [
    proposed.expected_delivery_date ? { label: 'Expected delivery', from: state?.amendment.original_values.expected_delivery_date ? formatDate(String(state?.amendment.original_values.expected_delivery_date)) : 'Not set', to: formatDate(String(proposed.expected_delivery_date)) } : null,
    proposed.delivery_destination ? { label: 'Delivery destination', from: String(state?.amendment.original_values.delivery_destination || 'Not set'), to: String(proposed.delivery_destination) } : null,
    proposed.supplier ? { label: 'Supplier', from: String(state?.order.supplier_name || 'Not set'), to: `Supplier #${String(proposed.supplier)}` } : null,
    Object.prototype.hasOwnProperty.call(proposed, 'notes') ? { label: 'PO notes', from: String(state?.amendment.original_values.notes || 'None'), to: String(proposed.notes || 'None') } : null,
  ].filter((change): change is { label: string; from: string; to: string } => Boolean(change));
  return <FormModal open={!!state} title={`Review amendment v${state?.amendment.version || ''}`} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
      <p className="rounded-lg border border-border bg-muted/30 p-3 text-sm"><strong>Reason:</strong> {state?.amendment.reason}</p>
      {priceLines.length ? <div className="rounded-lg border border-border p-3 text-sm"><strong>Changed line prices</strong><div className="mt-2 grid gap-2">{priceLines.map((line) => <div key={String(line.purchase_order_item)} className="grid gap-1 border-t border-border pt-2 sm:grid-cols-[1fr_auto_auto_auto]"><span>{String(line.material_name)} <small className="text-muted">× {String(line.quantity)}</small></span><span>Was {formatUGX(line.original_unit_price as string)}</span><strong>Now {formatUGX(line.unit_price as string)}</strong><strong className={Number(line.proposed_line_total) > Number(line.original_line_total) ? 'text-warning' : 'text-primary'}>{Number(line.proposed_line_total) - Number(line.original_line_total) >= 0 ? '+' : ''}{formatUGX(Math.abs(Number(line.proposed_line_total) - Number(line.original_line_total)))}</strong></div>)}</div></div> : null}
      {impact ? <div className="rounded-lg border border-primary/25 bg-primary/5 p-3 text-sm"><strong>{Number(impact.change_amount) === 0 ? 'Commercial impact' : 'Budget impact if approved'}</strong><div className="mt-2 grid gap-2 sm:grid-cols-3"><div><span className="block text-xs text-muted">Current PO total</span><strong>{formatUGX(impact.current_po_total)}</strong></div><div><span className="block text-xs text-muted">Revised PO total</span><strong>{formatUGX(impact.proposed_po_total)}</strong></div><div><span className="block text-xs text-muted">Change</span><strong className={Number(impact.change_amount) > 0 ? 'text-warning' : Number(impact.change_amount) < 0 ? 'text-primary' : ''}>{Number(impact.change_amount) > 0 ? '+' : ''}{formatUGX(impact.change_amount)}</strong></div></div>{impact.has_budget_line ? Number(impact.change_amount) === 0 ? <p className="mt-3 border-t border-primary/15 pt-3 text-xs text-muted">No price change is proposed. Approving this amendment will not change the budget commitment. Budget line available now: {formatUGX(impact.available_before || '0')}.</p> : <div className="mt-3 grid gap-2 border-t border-primary/15 pt-3 sm:grid-cols-2"><div><span className="block text-xs text-muted">Budget line</span><strong>{impact.budget_line_name}</strong><p className="text-xs text-muted">Available now: {formatUGX(impact.available_before || '0')}</p></div><div><span className="block text-xs text-muted">Forecast available after PO approval</span><strong className={Number(impact.projected_available_after) < 0 && !impact.budget_override ? 'text-critical' : ''}>{formatUGX(impact.projected_available_after || '0')}</strong><p className="text-xs text-muted">{impact.budget_override ? 'Budget override is in force.' : Number(impact.projected_available_after) < 0 ? 'Approval will be blocked unless Finance applies an override.' : 'Uses the revised total and releases any current PO commitment first.'}</p></div></div> : <p className="mt-2 text-xs text-muted">This PO is not linked to a budget line, so there is no budget commitment to recalculate.</p>}</div> : null}
      {otherChanges.length ? <div className="rounded-lg border border-border p-3 text-sm"><strong>Other requested changes</strong><div className="mt-2 grid gap-2">{otherChanges.map((change) => <div key={change.label} className="grid gap-1 border-t border-border pt-2 sm:grid-cols-[140px_1fr_1fr]"><strong>{change.label}</strong><span className="text-muted">Was: {change.from}</span><span>Now: {change.to}</span></div>)}</div></div> : null}
      <Field label="Finance decision"><select className={inputClass} value={approve ? 'approve' : 'reject'} onChange={(event) => setApprove(event.target.value === 'approve')}><option value="approve">Approve amendment</option><option value="reject">Reject amendment</option></select></Field>
      <Field label="Decision comments" required><textarea className={inputClass} rows={3} value={comments} onChange={(event) => setComments(event.target.value)} /></Field>
      <Button variant={approve ? 'default' : 'warning'} disabled={!comments.trim() || mutation.isPending} loading={mutation.isPending} loadingLabel="Saving decision">{approve ? 'Approve and recheck budget' : 'Reject amendment'}</Button>
    </form>
  </FormModal>;
}
