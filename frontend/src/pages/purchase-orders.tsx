import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Check, CheckCircle2, ChevronDown, ChevronRight, CircleDollarSign, Clock3, Download, EllipsisVertical, FilePenLine, FileText, MapPin, PackageCheck, Plus, Search, Trash2, Truck, X } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { api } from '@/modules/procurement/api';
import type { PurchaseOrder, PurchaseOrderAmendment, PurchaseRequest } from '@/modules/procurement/types';
import { qk } from '@/api/queryKeys';
import { can, canReceivePurchaseOrder, hasRole } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { SupplierLookup } from '@/components/common/supplier-lookup';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatUGX } from '@/lib/utils';
import './purchase-orders-reference.css';

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
  const list = useListState({ status: '', project: '', purchase_request: '', delivery_destination: '', action_queue: new URLSearchParams(location.search).get('action_queue') || '' });
  const [open, setOpen] = useState(Boolean(requestedPurchaseRequestId));
  const [cancelling, setCancelling] = useState<PurchaseOrder | null>(null);
  const [amending, setAmending] = useState<PurchaseOrder | null>(null);
  const [decidingAmendment, setDecidingAmendment] = useState<{ order: PurchaseOrder; amendment: PurchaseOrderAmendment; approve: boolean } | null>(null);
  const [reviewingPreapproval, setReviewingPreapproval] = useState<{ order: PurchaseOrder; amendment: PurchaseOrderAmendment; canConfirm: boolean } | null>(null);
  const [queue, setQueue] = useState<'all' | 'draft' | 'awaiting' | 'issued' | 'partial' | 'received' | 'closed'>('all');
  const [sort, setSort] = useState<'delivery' | 'newest'>('delivery');
  const orderQuery = { ...list.query, page_size: 5 };
  const orders = useQuery({ queryKey: list.filters.action_queue ? qk.purchaseOrderActionQueue(orderQuery) : qk.purchaseOrders(orderQuery), queryFn: () => api.purchaseOrders(orderQuery) });
  const allOrders = useQuery({ queryKey: qk.purchaseOrders({ page_size: 100 }), queryFn: () => api.purchaseOrders({ page_size: 100 }) });
  const projects = useQuery({ queryKey: qk.projects({ page_size: 100 }), queryFn: () => api.projects({ page_size: 100 }) });
  const receipts = useQuery({ queryKey: qk.goodsReceivedNotes({ page_size: 100 }), queryFn: () => api.goodsReceivedNotes({ page_size: 100 }) });
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
  const allRows = allOrders.data?.results || [];
  const receiptRows = receipts.data?.results || [];
  const receiptRowsByOrder = new Map<number, typeof receiptRows>();
  receiptRows.forEach((receipt) => receiptRowsByOrder.set(receipt.purchase_order, [...(receiptRowsByOrder.get(receipt.purchase_order) || []), receipt]));
  const receiptProgress = (order: PurchaseOrder) => {
    const ordered = order.items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
    const linkedReceipts = receiptRowsByOrder.get(order.id) || [];
    const accepted = linkedReceipts.flatMap((receipt) => receipt.items).reduce((sum, item) => sum + Number(item.accepted_quantity || 0), 0);
    const percent = ordered ? Math.min(100, Math.round((accepted / ordered) * 100)) : order.status === 'RECEIVED' ? 100 : 0;
    const latest = [...linkedReceipts].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
    return { percent, number: latest?.number || (order.status === 'RECEIVED' ? 'Receipt complete' : 'Awaiting receipt') };
  };
  const deliveryDate = (order: PurchaseOrder) => order.revised_delivery_date || order.supplier_confirmed_delivery_date || order.expected_delivery_date;
  const totalValue = allRows.reduce((sum, order) => sum + Number(order.total_cost || 0), 0);
  const awaitingDelivery = allRows.filter((order) => ['ORDERED', 'DISPATCH_CONFIRMED', 'PARTIAL'].includes(order.status));
  const receivedOrders = allRows.filter((order) => order.status === 'RECEIVED');
  const directToSiteOrders = allRows.filter((order) => order.delivery_destination === 'SITE');
  const directToSiteValue = directToSiteOrders.reduce((sum, order) => sum + Number(order.total_cost || 0), 0);
  const warehouseReceipts = receiptRows.filter((receipt) => allRows.find((order) => order.id === receipt.purchase_order)?.delivery_destination === 'WAREHOUSE');
  const siteReceipts = receiptRows.filter((receipt) => allRows.find((order) => order.id === receipt.purchase_order)?.delivery_destination === 'SITE');
  const partialOrders = allRows.filter((order) => order.status === 'PARTIAL');
  const onTimeReceived = receivedOrders.filter((order) => !deliveryDate(order) || !order.received_at || Date.parse(order.received_at) <= Date.parse(deliveryDate(order)!)).length;
  const onTimeRate = receivedOrders.length ? Math.round((onTimeReceived / receivedOrders.length) * 100) : 0;
  const receiptRate = allRows.length ? Math.round((receivedOrders.length / allRows.length) * 100) : 0;
  const averageLeadTime = receivedOrders.length ? Math.round(receivedOrders.reduce((sum, order) => sum + Math.max(0, (Date.parse(order.received_at || order.created_at) - Date.parse(order.created_at)) / 86400000), 0) / receivedOrders.length * 10) / 10 : 0;
  const projectOptions = projects.data?.results || [];
  const pageSize = 5;
  const totalRows = orders.data?.count || 0;
  const pageStart = totalRows ? (list.page - 1) * pageSize + 1 : 0;
  const pageEnd = totalRows ? Math.min(list.page * pageSize, totalRows) : 0;
  const updateQueue = (value: typeof queue) => {
    setQueue(value);
    list.setFilter('action_queue', '');
    list.setFilter('status', value === 'draft' ? 'DRAFT' : value === 'awaiting' ? 'PENDING' : value === 'issued' ? 'ORDERED' : value === 'partial' ? 'PARTIAL' : value === 'received' ? 'RECEIVED' : value === 'closed' ? 'CANCELLED' : '');
  };
  const rowAction = (order: PurchaseOrder) => {
    if (can.createPo(role) && ['DRAFT', 'PENDING'].includes(order.status)) return <Button size="sm" className="po-next-action" loading={approve.isPending && approve.variables === order.id} loadingLabel="Approving" disabled={approve.isPending} onClick={() => approve.mutate(order.id)}>Approve PO</Button>;
    if (can.createPo(role) && order.delivery_destination === 'SITE' && ['ORDERED', 'PARTIAL'].includes(order.status)) return <Button size="sm" variant="secondary" className="po-next-action" onClick={() => confirmDispatch.mutate(order.id)}><Truck size={13} />Confirm dispatch</Button>;
    if (canReceivePurchaseOrder(role, order)) return <Button size="sm" className="po-next-action" onClick={() => receive.mutate(order.id)}><CheckCircle2 size={13} />Confirm receipt</Button>;
    if (order.status === 'RECEIVED') return <Link className="po-view-action" to={`/procurement/grns?search=${encodeURIComponent(order.number)}`}>{order.delivery_destination === 'SITE' ? 'View receipt' : 'View GRN'}</Link>;
    if (order.pending_preapproval_edit && hasRole(role, ['finance_officer', 'finance_manager', 'admin'])) return <Button size="sm" variant="warning" className="po-next-action" onClick={() => { const amendment = (amendments.data?.get(order.id) || []).find((item) => item.status === 'SUBMITTED'); if (amendment) setReviewingPreapproval({ order, amendment, canConfirm: hasRole(role, ['finance_manager', 'admin']) }); }}>Review edit</Button>;
    return <span className="po-next-message" title={poNextAction(order, role)}>{poNextAction(order, role)}</span>;
  };
  const orderRows = [...(orders.data?.results || [])].sort((a, b) => sort === 'newest' ? Date.parse(b.created_at) - Date.parse(a.created_at) : Number(orderNeedsAction(b)) - Number(orderNeedsAction(a)));

  return (
    <div className="purchase-orders-reference">
      <section className="po-top"><div className="po-titlebar"><div><h1>Purchase orders</h1><p>Track supplier orders, deliveries and material receipt.</p></div><div className="po-title-actions"><details className="po-export-menu"><summary><Download size={15} />Export <ChevronDown size={13} /></summary><div><button type="button" onClick={() => void api.downloadPurchaseOrders('pdf', { ...list.filters, search: list.search })}>PDF register</button><button type="button" onClick={() => void api.downloadPurchaseOrders('xlsx', { ...list.filters, search: list.search })}>Excel register</button></div></details>{can.createPo(role) ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New PO</Button> : null}</div></div><nav className="po-tabs" aria-label="Procurement sections"><Link to="/procurement">Overview</Link><Link to="/procurement/requests">Purchase requests</Link><Link to="/procurement/rfqs">Supplier quotes</Link><Link className="active" to="/procurement/purchase-orders">Purchase orders</Link><Link to="/procurement/grns">Receipts</Link><Link to="/procurement/deliveries">Deliveries</Link><Link to="/procurement/supplier-claims">Supplier claims</Link></nav></section>
      <section className={`po-guidance ${awaitingDelivery.length ? 'attention' : 'complete'}`}><CheckCircle2 size={17} /><span><strong>{awaitingDelivery.length ? `${awaitingDelivery.length} purchase order${awaitingDelivery.length === 1 ? '' : 's'} await delivery or receipt.` : 'All purchase orders have been received.'}</strong><small>{awaitingDelivery.length ? 'Keep supplier dispatch and receipt evidence up to date.' : 'Verify receipt documents before closing.'}</small></span><Link to="/procurement/grns">Open receipts <ChevronRight size={14} /></Link></section>
      <section className="po-kpis"><PurchaseOrderKpi icon={FileText} tone="blue" label="Total orders" value={allRows.length} note="Across selected sites" /><PurchaseOrderKpi icon={Truck} tone="amber" label="Awaiting delivery" value={awaitingDelivery.length} note={awaitingDelivery.length ? 'Follow-up required' : 'All orders received'} /><PurchaseOrderKpi icon={Box} tone="green" label="Received" value={receivedOrders.length} note={`${receiptRate}% receipt completion`} /><PurchaseOrderKpi icon={CircleDollarSign} tone="indigo" label="Order value" value={formatUGX(totalValue)} note="Committed purchase value" /><PurchaseOrderKpi icon={MapPin} tone="violet" label="Direct to site" value={directToSiteOrders.length} note={formatUGX(directToSiteValue)} /></section>
      <section className="po-workspace-grid"><div className="po-register-panel"><div className="po-panel-heading"><h2>Purchase order register</h2></div><div className="po-queue-tabs">{([['all', 'All', allRows.length], ['draft', 'Draft', allRows.filter((order) => order.status === 'DRAFT').length], ['awaiting', 'Awaiting approval', allRows.filter((order) => order.status === 'PENDING').length], ['issued', 'Issued', allRows.filter((order) => order.status === 'ORDERED').length], ['partial', 'Part received', partialOrders.length], ['received', 'Received', receivedOrders.length], ['closed', 'Closed', allRows.filter((order) => order.status === 'CANCELLED').length]] as const).map(([value, label, count]) => <button type="button" key={value} className={queue === value ? 'active' : ''} onClick={() => updateQueue(value)}>{label}<b>{count}</b></button>)}</div><div className="po-filters"><label><Search size={14} /><input aria-label="Search purchase orders" placeholder="Search PO, supplier or project" value={list.search} onChange={(event) => list.setSearch(event.target.value)} /></label><select aria-label="Filter purchase orders by project" className={inputClass} value={list.filters.project} onChange={(event) => list.setFilter('project', event.target.value)}><option value="">Project</option>{projectOptions.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select><select aria-label="Filter purchase orders by destination" className={inputClass} value={list.filters.delivery_destination} onChange={(event) => list.setFilter('delivery_destination', event.target.value)}><option value="">Destination</option><option value="WAREHOUSE">Main warehouse</option><option value="SITE">Direct to site</option></select><select aria-label="Filter purchase orders by status" className={inputClass} value={list.filters.status} onChange={(event) => { setQueue('all'); list.setFilter('action_queue', ''); list.setFilter('status', event.target.value); }}><option value="">Status</option><option value="DRAFT">Draft</option><option value="PENDING">Pending</option><option value="ORDERED">Ordered</option><option value="DISPATCH_CONFIRMED">Dispatch confirmed</option><option value="PARTIAL">Part received</option><option value="RECEIVED">Received</option><option value="CANCELLED">Cancelled</option></select><select aria-label="Sort purchase orders" className={inputClass} value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="delivery">Sort: Delivery date</option><option value="newest">Sort: Newest first</option></select></div><div className="po-table-wrap"><table className="po-table"><thead><tr><th>Purchase order</th><th>Supplier</th><th>Project / site</th><th>Destination</th><th>Ordered</th><th>Delivery date</th><th>Receipt progress</th><th>Total</th><th>Status</th><th>Next action</th><th aria-label="Actions" /></tr></thead><tbody>{orderRows.map((order) => { const receipt = receiptProgress(order); const commitmentDate = deliveryDate(order); return <tr key={order.id}><td><Link to={`/procurement/purchase-orders?search=${encodeURIComponent(order.number)}`}>{order.number}</Link><small>{order.purchase_request_number || 'Manual PO'}</small></td><td>{order.supplier_name || 'Unassigned'}</td><td>{order.project_name || 'Warehouse'}<small>{order.project_name ? 'Project order' : 'No project'}</small></td><td><Badge tone={order.delivery_destination === 'SITE' ? 'info' : 'success'}>{order.delivery_destination_display}</Badge></td><td>{formatDate(order.created_at)}</td><td className={order.is_overdue ? 'overdue' : ''}>{commitmentDate ? formatDate(commitmentDate) : 'Not committed'}{order.is_overdue ? <small>Overdue</small> : null}</td><td><div className="po-receipt-progress"><span><b style={{ width: `${receipt.percent}%` }} /></span><strong>{receipt.percent}%</strong><small>{receipt.number}</small></div></td><td>{formatUGX(order.total_cost)}</td><td><Badge tone={statusTone(order.status)}>{order.status_display}</Badge>{order.pending_preapproval_edit ? <small className="po-finance-flag">Finance review</small> : null}</td><td>{rowAction(order)}</td><td><details className="po-row-menu"><summary aria-label={`More actions for ${order.number}`}><EllipsisVertical size={16} /></summary><div>{can.createPo(role) && !['RECEIVED', 'CANCELLED'].includes(order.status) ? <button type="button" onClick={() => setCancelling(order)}><X size={13} />Cancel</button> : null}{hasRole(role, ['procurement_officer', 'admin']) && ['DRAFT', 'PENDING', 'ORDERED'].includes(order.status) ? <button type="button" onClick={() => setAmending(order)}><FilePenLine size={13} />{['DRAFT', 'PENDING'].includes(order.status) ? 'Edit PO' : 'Amend PO'}</button> : null}{hasRole(role, ['procurement_officer', 'admin']) && order.status === 'DRAFT' ? <button type="button" onClick={() => { if (window.confirm(`Delete ${order.number}? This draft will be removed and audited.`)) deleteDraft.mutate(order.id); }}><Trash2 size={13} />Delete draft</button> : null}{hasRole(role, ['finance_officer', 'finance_manager', 'admin']) ? (amendments.data?.get(order.id) || []).filter((item) => item.status === 'SUBMITTED').map((item) => item.amendment_type === 'PRE_APPROVAL_EDIT' ? <button type="button" key={item.id} onClick={() => setReviewingPreapproval({ order, amendment: item, canConfirm: hasRole(role, ['finance_manager', 'admin']) })}><FilePenLine size={13} />{hasRole(role, ['finance_manager', 'admin']) ? 'Review edited PO' : 'View edited PO'}</button> : hasRole(role, ['finance_manager', 'admin']) ? <button type="button" key={item.id} onClick={() => setDecidingAmendment({ order, amendment: item, approve: true })}><Check size={13} />Review v{item.version}</button> : null) : null}{hasRole(role, ['finance_officer', 'finance_manager', 'admin']) && order.status === 'PENDING' && order.purchase_request_number ? <button type="button" onClick={() => navigate(`/procurement/requests?search=${encodeURIComponent(order.purchase_request_number || '')}`)}><Check size={13} />Finance review</button> : null}</div></details></td></tr>; })}</tbody></table>{!orderRows.length ? <p className="po-empty">{orders.isLoading ? 'Loading purchase orders…' : 'No purchase orders match this view.'}</p> : null}</div><footer className="po-table-footer"><span>Showing {pageStart} to {pageEnd} of {totalRows} purchase orders</span><span><button type="button" disabled={!orders.data?.previous} onClick={() => list.setPage(Math.max(1, list.page - 1))}>‹</button><b>{list.page}</b><button type="button" disabled={!orders.data?.next} onClick={() => list.setPage(list.page + 1)}>›</button></span></footer></div><aside className="po-side-column"><section className="po-summary-panel"><div className="po-panel-heading"><h2>Receiving summary</h2></div><Link to="/procurement/deliveries?action_queue=warehouse_receipts"><Box size={17} /><span>Warehouse receipts<small>{warehouseReceipts.length} recorded</small></span><strong>{formatUGX(warehouseReceipts.reduce((sum, receipt) => sum + Number(allRows.find((order) => order.id === receipt.purchase_order)?.total_cost || 0), 0))}</strong></Link><Link to="/procurement/deliveries?action_queue=site_receipts"><Truck size={17} /><span>Direct-to-site receipts<small>{siteReceipts.length} recorded</small></span><strong>{formatUGX(siteReceipts.reduce((sum, receipt) => sum + Number(allRows.find((order) => order.id === receipt.purchase_order)?.total_cost || 0), 0))}</strong></Link><div><Clock3 size={17} /><span>Partial receipts<small>Require follow-up</small></span><strong>{partialOrders.length}</strong></div><div><X size={17} /><span>Cancelled orders<small>Commitment released</small></span><strong>{allRows.filter((order) => order.status === 'CANCELLED').length}</strong></div></section><section className="po-steps-panel"><div className="po-panel-heading"><h2>Next steps</h2><Link to="/procurement/deliveries">View all <ChevronRight size={13} /></Link></div><Link to="/procurement/deliveries?action_queue=warehouse_receipts"><PackageCheck size={17} /><span>GRNs to verify<small>Warehouse receiving queue</small></span><strong>{allRows.filter((order) => order.delivery_destination === 'WAREHOUSE' && ['ORDERED', 'PARTIAL'].includes(order.status)).length}</strong></Link><Link to="/procurement/deliveries?action_queue=site_receipts"><Truck size={17} /><span>Site receipts to confirm<small>Direct-to-site queue</small></span><strong>{allRows.filter((order) => order.delivery_destination === 'SITE' && ['DISPATCH_CONFIRMED', 'PARTIAL'].includes(order.status)).length}</strong></Link><Link to="/finance/payables"><CircleDollarSign size={17} /><span>Ready for invoice matching<small>Finance payables workspace</small></span><strong>{receivedOrders.length}</strong></Link></section><section className="po-performance-panel"><div className="po-panel-heading"><h2>Supplier delivery</h2><Link to="/suppliers">View all <ChevronRight size={13} /></Link></div><strong>{allRows[0]?.supplier_name || 'No supplier data'}</strong><PurchaseOrderPerformance label="On-time delivery" value={onTimeRate} suffix="%" /><PurchaseOrderPerformance label="Receipt completion" value={receiptRate} suffix="%" /><PurchaseOrderPerformance label="Average lead time" value={averageLeadTime} suffix=" days" /></section></aside></section>
      {hasRole(role, ['procurement_officer', 'admin']) ? <PurchaseOrderModal open={open} onClose={() => setOpen(false)} initialPurchaseRequestId={requestedPurchaseRequestId} /> : null}
      <CancelPurchaseOrderModal order={cancelling} pending={cancel.isPending} onClose={() => setCancelling(null)} onCancel={(comments) => cancelling && cancel.mutate({ id: cancelling.id, comments })} />
      <PurchaseOrderAmendmentModal order={amending} onClose={() => setAmending(null)} onDone={refresh} />
      <PurchaseOrderAmendmentDecisionModal state={decidingAmendment} onClose={() => setDecidingAmendment(null)} onDone={refresh} />
      <PreApprovalEditReviewModal state={reviewingPreapproval} onClose={() => setReviewingPreapproval(null)} onDone={refresh} />
    </div>
  );
}

function PurchaseOrderKpi({ icon: Icon, tone, label, value, note }: { icon: typeof FileText; tone: string; label: string; value: string | number; note: string }) {
  return <article className="po-kpi"><span className={`po-kpi-icon ${tone}`}><Icon size={23} /></span><div><p>{label}</p><strong>{value}</strong><small>{note}</small></div></article>;
}

function PurchaseOrderPerformance({ label, value, suffix }: { label: string; value: number; suffix: string }) {
  const width = suffix === ' days' ? Math.min(100, value ? 100 / Math.max(value, 1) * 3 : 0) : value;
  return <div className="po-performance-row"><span>{label}</span><i><b style={{ width: `${width}%` }} /></i><strong>{value}{suffix}</strong></div>;
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
