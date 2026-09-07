import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { BarChart3, Box, CalendarDays, ChevronDown, ChevronRight, CircleAlert, Download, EllipsisVertical, Eye, FileText, PackageCheck, Search, Truck } from 'lucide-react';
import { api } from '@/api/services';
import { getTokens } from '@/api/client';
import { offlineScope, queueOfflineAction } from '@/pwa/offline';
import type { PurchaseOrder, SupplierClaim } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can, canReceivePurchaseOrder } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { inputClass } from '@/components/ui/field';
import { Field } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatDate, formatUGX } from '@/lib/utils';
import './deliveries-reference.css';

export function DeliveriesPage() {
  const { role } = useAuth();
  const [searchParams] = useSearchParams();
  const queryString = searchParams.toString();
  const replacementClaimId = Number(searchParams.get('replacement_claim') || 0);
  const [queue, setQueue] = useState<'all' | 'scheduled' | 'dispatched' | 'arrived' | 'received' | 'delayed'>('all');
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [destination, setDestination] = useState(searchParams.get('delivery_destination') || '');
  const [project, setProject] = useState(searchParams.get('project') || '');
  const [status, setStatus] = useState(searchParams.get('status') || '');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [sort, setSort] = useState<'expected' | 'newest'>('expected');
  const [page, setPage] = useState(1);
  const orders = useQuery({ queryKey: qk.purchaseOrders({ page_size: 100 }), queryFn: () => api.purchaseOrders({ page_size: 100 }) });
  const receipts = useQuery({ queryKey: ['goods-received-notes', 'delivery-remaining'], queryFn: () => api.goodsReceivedNotes({ page_size: 100 }) });
  const replacementClaim = useQuery({ queryKey: ['supplier-claim', replacementClaimId], queryFn: () => api.supplierClaim(replacementClaimId), enabled: replacementClaimId > 0 });
  const replacementOrder = useQuery({ queryKey: ['purchase-order', replacementClaim.data?.purchase_order], queryFn: () => api.purchaseOrder(replacementClaim.data!.purchase_order), enabled: !!replacementClaim.data?.purchase_order });
  const queryClient = useQueryClient();
  const toast = useToast();
  const [receiving, setReceiving] = useState<PurchaseOrder | null>(null);
  const actionQueue = searchParams.get('action_queue') || '';
  useEffect(() => {
    setSearch(searchParams.get('search') || '');
    setDestination(searchParams.get('delivery_destination') || '');
    setProject(searchParams.get('project') || '');
    setStatus(searchParams.get('status') || '');
    setPage(1);
  }, [queryString, searchParams]);
  useEffect(() => { if (replacementClaim.data && replacementOrder.data) setReceiving(replacementOrder.data); }, [replacementClaim.data, replacementOrder.data]);
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] }); void queryClient.invalidateQueries({ queryKey: ['goods-received-notes'] }); };
  const dispatch = useMutation({
    mutationFn: api.confirmDispatch,
    onSuccess: () => { toast.push({ title: 'Dispatch confirmed', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Dispatch blocked', message: error.message, tone: 'danger' }),
  });
  const receive = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Record<string, unknown> }) => {
      const withIdempotency = { ...body, client_uuid: crypto.randomUUID() };
      const queue = async () => queueOfflineAction({ scope: offlineScope(getTokens()?.access), kind: 'goods-received-note', path: `/api/purchase-orders/${id}/receive/`, body: withIdempotency });
      if (!navigator.onLine) {
        await queue();
        return { queued: true };
      }
      try { return replacementClaimId ? await api.receiveSupplierReplacement(replacementClaimId, withIdempotency) : await api.receivePurchaseOrder(id, withIdempotency); }
      catch (error) {
        // Retrying a transport failure with this same UUID cannot duplicate stock.
        if (error instanceof TypeError) { await queue(); return { queued: true }; }
        throw error;
      }
    },
    onSuccess: (order) => {
      if ('queued' in order) {
        toast.push({ title: 'Receipt saved offline — stock updates after server confirmation', tone: 'success' });
      } else {
        toast.push({ title: replacementClaimId ? 'Supplier replacement received and claim resolved' : order.status === 'PARTIAL' ? 'Partial receipt recorded' : 'Receipt confirmed', tone: 'success' });
        refresh();
      }
      setReceiving(null);
    },
    onError: (error: Error) => toast.push({ title: 'Receipt blocked', message: error.message, tone: 'danger' }),
  });
  const allOrders = orders.data?.results || [];
  const allReceipts = receipts.data?.results || [];
  const receiptByOrder = new Map<number, typeof allReceipts>();
  allReceipts.forEach((receipt) => receiptByOrder.set(receipt.purchase_order, [...(receiptByOrder.get(receipt.purchase_order) || []), receipt]));
  const deliveryOrders = allOrders.filter((order) => !['DRAFT', 'PENDING', 'CANCELLED'].includes(order.status));
  const deliveryState = (order: PurchaseOrder) => order.status === 'RECEIVED' ? 'received' : order.status === 'PARTIAL' ? 'arrived' : order.status === 'DISPATCH_CONFIRMED' ? 'dispatched' : order.is_overdue ? 'delayed' : 'scheduled';
  const expectedDate = (order: PurchaseOrder) => order.revised_delivery_date || order.supplier_confirmed_delivery_date || order.expected_delivery_date;
  const today = new Date().toISOString().slice(0, 10);
  const receivedOrders = deliveryOrders.filter((order) => order.status === 'RECEIVED');
  const inTransitOrders = deliveryOrders.filter((order) => ['ORDERED', 'DISPATCH_CONFIRMED'].includes(order.status) && !order.is_overdue);
  const arrivedToday = deliveryOrders.filter((order) => (order.received_at || '').slice(0, 10) === today);
  const delayedOrders = deliveryOrders.filter((order) => order.is_overdue);
  const warehouseOrders = deliveryOrders.filter((order) => order.delivery_destination === 'WAREHOUSE');
  const siteOrders = deliveryOrders.filter((order) => order.delivery_destination === 'SITE');
  const onTimeReceived = receivedOrders.filter((order) => !expectedDate(order) || !order.received_at || Date.parse(order.received_at) <= Date.parse(expectedDate(order)!)).length;
  const onTimeRate = receivedOrders.length ? Math.round(onTimeReceived / receivedOrders.length * 100) : 0;
  const averageTransit = receivedOrders.length ? Math.round(receivedOrders.reduce((sum, order) => sum + Math.max(0, (Date.parse(order.received_at || order.created_at) - Date.parse(order.created_at)) / 86400000), 0) / receivedOrders.length * 10) / 10 : 0;
  const projects = [...new Map(deliveryOrders.filter((order) => order.project && order.project_name).map((order) => [order.project!, order.project_name!])).entries()];
  const filteredOrders = deliveryOrders.filter((order) => {
    const state = deliveryState(order);
    const haystack = [order.number, order.supplier_name, order.project_name, order.delivery_destination_display].join(' ').toLowerCase();
    const date = expectedDate(order) || '';
    const matchesActionQueue = actionQueue === 'warehouse_receipts'
      ? order.delivery_destination === 'WAREHOUSE' && ['ORDERED', 'PARTIAL'].includes(order.status)
      : actionQueue === 'site_receipts'
        ? order.delivery_destination === 'SITE' && ['DISPATCH_CONFIRMED', 'PARTIAL'].includes(order.status)
        : true;
    return matchesActionQueue && (queue === 'all' || state === queue) && (!destination || order.delivery_destination === destination) && (!project || String(order.project) === project) && (!status || order.status === status) && (!fromDate || date >= fromDate) && (!toDate || date <= toDate) && haystack.includes(search.trim().toLowerCase());
  }).sort((a, b) => sort === 'newest' ? Date.parse(b.created_at) - Date.parse(a.created_at) : Date.parse(expectedDate(a) || '9999-12-31') - Date.parse(expectedDate(b) || '9999-12-31'));
  const pageSize = 5;
  const totalPages = Math.max(1, Math.ceil(filteredOrders.length / pageSize));
  const displayedOrders = filteredOrders.slice((page - 1) * pageSize, page * pageSize);
  const pageStart = filteredOrders.length ? (page - 1) * pageSize + 1 : 0;
  const pageEnd = filteredOrders.length ? Math.min(page * pageSize, filteredOrders.length) : 0;
  const update = (setter: () => void) => { setter(); setPage(1); };
  const exportRegister = async (kind: 'pdf' | 'xlsx') => {
    try { await api.downloadPurchaseOrders(kind, { search, status, delivery_destination: destination }); toast.push({ title: `Delivery ${kind === 'pdf' ? 'PDF' : 'Excel'} register prepared`, tone: 'success' }); }
    catch (error) { toast.push({ title: 'Delivery register export failed', message: (error as Error).message, tone: 'danger' }); }
  };

  return <div className="deliveries-reference"><section className="del-top"><div className="del-titlebar"><div><h1>Deliveries</h1><p>Track supplier dispatches, expected arrivals and receipt confirmation.</p></div><div className="del-title-actions"><details className="del-export-menu"><summary><Download size={15} />Export <ChevronDown size={13} /></summary><div><button type="button" onClick={() => void exportRegister('pdf')}>PDF register</button><button type="button" onClick={() => void exportRegister('xlsx')}>Excel register</button></div></details><Button asChild><Link to={can.createPo(role) ? '/procurement/deliveries?status=ORDERED&delivery_destination=SITE' : '/procurement/deliveries'}>{can.createPo(role) ? <><Truck className="h-4 w-4" />Record dispatch</> : <><PackageCheck className="h-4 w-4" />Delivery queue</>}</Link></Button></div></div><nav className="del-tabs" aria-label="Procurement sections"><Link to="/procurement">Overview</Link><Link to="/procurement/requests">Purchase requests</Link><Link to="/procurement/rfqs">Supplier quotes</Link><Link to="/procurement/purchase-orders">Purchase orders</Link><Link to="/procurement/grns">Receipts</Link><Link className="active" to="/procurement/deliveries">Deliveries</Link><Link to="/procurement/supplier-claims">Supplier claims</Link></nav></section>
    <section className="del-guidance"><CircleAlert size={17} /><span><strong>Warehouse receipts are confirmed by Storekeepers; direct-to-site receipts are confirmed by assigned Site Engineers.</strong><small>Dispatch confirmation and physical receiving stay separated for an auditable delivery trail.</small></span><Link to="/procurement/purchase-orders">Delivery workflow <ChevronRight size={14} /></Link></section>
    <section className="del-kpis"><DeliveryKpi icon={Truck} tone="blue" label="Total deliveries" value={deliveryOrders.length} note="Issued purchase orders" /><DeliveryKpi icon={Truck} tone="amber" label="In transit" value={inTransitOrders.length} note={inTransitOrders.length ? 'Supplier follow-up active' : 'No active dispatches'} /><DeliveryKpi icon={CalendarDays} tone="indigo" label="Arrived today" value={arrivedToday.length} note={arrivedToday.length ? 'Receipt recorded today' : 'No arrivals today'} /><DeliveryKpi icon={Box} tone="green" label="Received" value={receivedOrders.length} note="Linked to GRNs" /><DeliveryKpi icon={BarChart3} tone="green" label="On-time delivery" value={receivedOrders.length ? `${onTimeRate}%` : '—'} note={receivedOrders.length ? 'Received against expected date' : 'No received orders'} /></section>
    <section className="del-workspace-grid"><div className="del-register-panel"><div className="del-panel-heading"><h2>Delivery register</h2></div><div className="del-queue-tabs">{([['all', 'All', deliveryOrders.length], ['scheduled', 'Scheduled', deliveryOrders.filter((order) => deliveryState(order) === 'scheduled').length], ['dispatched', 'Dispatched', deliveryOrders.filter((order) => deliveryState(order) === 'dispatched').length], ['arrived', 'Arrived', deliveryOrders.filter((order) => deliveryState(order) === 'arrived').length], ['received', 'Received', receivedOrders.length], ['delayed', 'Delayed', delayedOrders.length]] as const).map(([value, label, count]) => <button type="button" key={value} className={queue === value ? 'active' : ''} onClick={() => update(() => setQueue(value))}>{label}<b>{count}</b></button>)}</div><div className="del-filters"><label><Search size={14} /><input aria-label="Search deliveries" placeholder="Search PO, supplier or destination" value={search} onChange={(event) => update(() => setSearch(event.target.value))} /></label><select aria-label="Filter deliveries by destination" className={inputClass} value={destination} onChange={(event) => update(() => setDestination(event.target.value))}><option value="">Destination</option><option value="WAREHOUSE">Main warehouse</option><option value="SITE">Direct to site</option></select><select aria-label="Filter deliveries by project" className={inputClass} value={project} onChange={(event) => update(() => setProject(event.target.value))}><option value="">Project</option>{projects.map(([id, name]) => <option value={id} key={id}>{name}</option>)}</select><select aria-label="Filter deliveries by status" className={inputClass} value={status} onChange={(event) => update(() => setStatus(event.target.value))}><option value="">Status</option><option value="ORDERED">Scheduled</option><option value="DISPATCH_CONFIRMED">Dispatched</option><option value="PARTIAL">Part received</option><option value="RECEIVED">Received</option></select><label className="del-date-range"><CalendarDays size={14} /><input aria-label="Filter deliveries from date" type="date" value={fromDate} onChange={(event) => update(() => setFromDate(event.target.value))} /><span>–</span><input aria-label="Filter deliveries to date" type="date" value={toDate} onChange={(event) => update(() => setToDate(event.target.value))} /></label><select aria-label="Sort deliveries" className={inputClass} value={sort} onChange={(event) => update(() => setSort(event.target.value as typeof sort))}><option value="expected">Sort: Expected arrival</option><option value="newest">Sort: Newest first</option></select></div><div className="del-table-wrap"><table className="del-table"><thead><tr><th>Delivery / PO</th><th>Supplier</th><th>Project / site</th><th>Destination</th><th>Dispatched</th><th>Expected</th><th>Arrived</th><th>Status</th><th>Receipt</th><th>Total</th><th>Next action</th><th aria-label="Actions" /></tr></thead><tbody>{displayedOrders.map((order) => <DeliveryRow key={order.id} order={order} receipts={receiptByOrder.get(order.id) || []} role={role} onDispatch={() => dispatch.mutate(order.id)} onReceive={() => setReceiving(order)} />)}</tbody></table>{!displayedOrders.length ? <p className="del-empty">{orders.isLoading ? 'Loading deliveries…' : 'No deliveries match this view.'}</p> : null}</div><footer className="del-table-footer"><span>Showing {pageStart} to {pageEnd} of {filteredOrders.length} deliveries</span><span><button type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>‹</button><b>{page}</b><button type="button" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>›</button></span></footer></div><aside className="del-side-column"><section className="del-status-panel"><div className="del-panel-heading"><h2>Delivery status</h2></div><div className="del-status-body"><div className="del-donut" style={{ background: deliveryOrders.length ? `conic-gradient(#138d68 0 ${Math.round(receivedOrders.length / deliveryOrders.length * 100)}%, #2d83c8 ${Math.round(receivedOrders.length / deliveryOrders.length * 100)}% ${Math.round((receivedOrders.length + inTransitOrders.length) / deliveryOrders.length * 100)}%, #ef9c27 ${Math.round((receivedOrders.length + inTransitOrders.length) / deliveryOrders.length * 100)}% ${Math.round((receivedOrders.length + inTransitOrders.length + delayedOrders.length) / deliveryOrders.length * 100)}%, #e9edef ${Math.round((receivedOrders.length + inTransitOrders.length + delayedOrders.length) / deliveryOrders.length * 100)}% 100%)` : '#e9edef' }}><strong>{deliveryOrders.length}</strong><small>deliveries</small></div><div className="del-status-list"><StatusRow label="Received" tone="received" value={receivedOrders.length} /><StatusRow label="In transit" tone="transit" value={inTransitOrders.length} /><StatusRow label="Delayed" tone="delayed" value={delayedOrders.length} /><StatusRow label="Awaiting receipt" tone="awaiting" value={deliveryOrders.filter((order) => order.status === 'PARTIAL').length} /></div></div></section><section className="del-summary-panel"><div className="del-panel-heading"><h2>Destination summary</h2></div><Link to="/procurement/deliveries?action_queue=warehouse_receipts"><Box size={17} /><span>Main warehouse<small>{warehouseOrders.length} deliveries</small></span><strong>{formatUGX(warehouseOrders.reduce((sum, order) => sum + Number(order.total_cost || 0), 0))}</strong></Link><Link to="/procurement/deliveries?action_queue=site_receipts"><Truck size={17} /><span>Direct to site<small>{siteOrders.length} deliveries</small></span><strong>{formatUGX(siteOrders.reduce((sum, order) => sum + Number(order.total_cost || 0), 0))}</strong></Link></section><section className="del-confirmation-panel"><div className="del-panel-heading"><h2>Arrival confirmations</h2><Badge tone={inTransitOrders.length || delayedOrders.length ? 'warning' : 'success'}>{inTransitOrders.length || delayedOrders.length ? 'Attention' : 'All clear'}</Badge></div><Link to="/procurement/deliveries?action_queue=warehouse_receipts"><PackageCheck size={17} /><span>Warehouse awaiting GRN<small>Storekeeper receipt queue</small></span><strong>{allOrders.filter((order) => order.delivery_destination === 'WAREHOUSE' && ['ORDERED', 'PARTIAL'].includes(order.status)).length}</strong></Link><Link to="/procurement/deliveries?action_queue=site_receipts"><Truck size={17} /><span>Site engineer confirmations<small>Direct-to-site receipt queue</small></span><strong>{allOrders.filter((order) => order.delivery_destination === 'SITE' && ['DISPATCH_CONFIRMED', 'PARTIAL'].includes(order.status)).length}</strong></Link><Link to="/procurement/purchase-orders"><FileText size={17} /><span>Delayed deliveries<small>Supplier follow-up required</small></span><strong>{delayedOrders.length}</strong></Link></section><section className="del-performance-panel"><div className="del-panel-heading"><h2>Supplier performance</h2><Link to="/suppliers">View all <ChevronRight size={13} /></Link></div><strong>{deliveryOrders[0]?.supplier_name || 'No supplier data'}</strong><PerformanceRow label="On-time delivery" value={onTimeRate} display={receivedOrders.length ? `${onTimeRate}%` : 'No data'} /><PerformanceRow label="Average transit time" value={averageTransit ? Math.min(100, 100 / averageTransit * 3) : 0} display={receivedOrders.length ? `${averageTransit} days` : 'No data'} /><PerformanceRow label="Total deliveries" value={deliveryOrders.length ? 100 : 0} display={String(deliveryOrders.length)} /></section></aside></section>
    <ReceiptModal order={receiving} receipts={allReceipts} pending={receive.isPending} role={role} replacementClaim={replacementClaim.data} onClose={() => setReceiving(null)} onSubmit={(body) => receiving && receive.mutate({ id: receiving.id, body: body as Record<string, unknown> })} />
  </div>;
}

function DeliveryRow({ order, receipts, role, onDispatch, onReceive }: { order: PurchaseOrder; receipts: Awaited<ReturnType<typeof api.goodsReceivedNotes>>['results']; role: ReturnType<typeof useAuth>['role']; onDispatch: () => void; onReceive: () => void }) {
  const expected = order.revised_delivery_date || order.supplier_confirmed_delivery_date || order.expected_delivery_date;
  const latestReceipt = [...receipts].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
  const nextAction = can.createPo(role) && order.delivery_destination === 'SITE' && ['ORDERED', 'PARTIAL'].includes(order.status) ? <Button size="sm" className="del-next-action" variant="secondary" onClick={onDispatch}><Truck size={13} />Dispatch</Button> : canReceivePurchaseOrder(role, order) ? <Button size="sm" className="del-next-action" onClick={onReceive}><PackageCheck size={13} />Receive</Button> : order.status === 'RECEIVED' ? <Link className="del-view-action" to={`/procurement/grns?search=${encodeURIComponent(order.number)}`}>View receipt</Link> : <span className="del-next-message">{order.is_overdue ? 'Follow up supplier' : 'Awaiting delivery'}</span>;
  return <tr><td><Link to={`/procurement/purchase-orders?search=${encodeURIComponent(order.number)}`}>{order.number}</Link><small>{order.purchase_request_number || 'Manual PO'}</small></td><td>{order.supplier_name || 'Supplier not recorded'}</td><td>{order.project_name || 'Warehouse'}<small>{order.project_name ? 'Project order' : 'No project'}</small></td><td><Badge tone={order.delivery_destination === 'SITE' ? 'info' : 'success'}>{order.delivery_destination_display}</Badge></td><td>{order.dispatch_confirmed_at ? formatDate(order.dispatch_confirmed_at) : order.status === 'ORDERED' ? 'Not dispatched' : '—'}</td><td className={order.is_overdue ? 'overdue' : ''}>{expected ? formatDate(expected) : 'Not committed'}{order.is_overdue ? <small>Overdue</small> : null}</td><td>{order.received_at ? formatDate(order.received_at) : '—'}{order.received_by_username ? <small>{order.received_by_username}</small> : null}</td><td><Badge tone={statusTone(order.status)}>{order.status_display}</Badge></td><td>{latestReceipt ? <Link to={`/procurement/grns?search=${encodeURIComponent(latestReceipt.number)}`}>{latestReceipt.number}</Link> : <span className="del-muted">Awaiting GRN</span>}</td><td>{formatUGX(order.total_cost)}</td><td>{nextAction}</td><td><details className="del-row-menu"><summary aria-label={`More actions for ${order.number}`}><EllipsisVertical size={16} /></summary><div>{can.createPo(role) && order.delivery_destination === 'SITE' && ['ORDERED', 'PARTIAL'].includes(order.status) ? <button type="button" onClick={onDispatch}><Truck size={13} />Confirm dispatch</button> : null}{canReceivePurchaseOrder(role, order) ? <button type="button" onClick={onReceive}><PackageCheck size={13} />Record receipt</button> : null}<Link to={`/procurement/purchase-orders?search=${encodeURIComponent(order.number)}`}><Eye size={13} />View purchase order</Link></div></details></td></tr>;
}

function DeliveryKpi({ icon: Icon, tone, label, value, note }: { icon: typeof Truck; tone: string; label: string; value: string | number; note: string }) {
  return <article className="del-kpi"><span className={`del-kpi-icon ${tone}`}><Icon size={23} /></span><div><p>{label}</p><strong>{value}</strong><small>{note}</small></div></article>;
}

function StatusRow({ label, tone, value }: { label: string; tone: string; value: number }) {
  return <div className="del-status-row"><span><i className={tone} />{label}</span><strong>{value}</strong></div>;
}

function PerformanceRow({ label, value, display }: { label: string; value: number; display: string }) {
  return <div className="del-performance-row"><span>{label}</span><i><b style={{ width: `${value}%` }} /></i><strong>{display}</strong></div>;
}

type ReceiptLine = { purchase_order_item: number; accepted_quantity: string; rejected_quantity: string; damaged_quantity: string; notes: string };

function ReceiptModal({ order, receipts, pending, role, replacementClaim, onClose, onSubmit }: { order: PurchaseOrder | null; receipts: Awaited<ReturnType<typeof api.goodsReceivedNotes>>['results']; pending: boolean; role: string | null; replacementClaim?: SupplierClaim; onClose: () => void; onSubmit: (body: unknown) => void }) {
  const [receiptDate, setReceiptDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<ReceiptLine[]>([]);
  const open = Boolean(order);

  const resetForOrder = (next: PurchaseOrder | null) => {
    setReceiptDate(new Date().toISOString().slice(0, 10));
    setNotes('');
    if (replacementClaim) {
      setLines([{ purchase_order_item: replacementClaim.purchase_order_item, accepted_quantity: String(replacementClaim.replacement_quantity), rejected_quantity: '0', damaged_quantity: '0', notes: `Supplier replacement for claim #${replacementClaim.id}` }]);
      return;
    }
    const dispositioned = new Map<number, number>();
    receipts.filter((receipt) => receipt.purchase_order === next?.id && receipt.status === 'ACCEPTED').forEach((receipt) => receipt.items.forEach((item) => dispositioned.set(item.purchase_order_item, (dispositioned.get(item.purchase_order_item) || 0) + Number(item.accepted_quantity) + Number(item.rejected_quantity) + Number(item.damaged_quantity))));
    setLines(next?.items.flatMap((item) => {
      const remaining = Math.max(Number(item.quantity) - (dispositioned.get(item.id) || 0), 0);
      return remaining > 0 ? [{ purchase_order_item: item.id, accepted_quantity: String(remaining), rejected_quantity: '0', damaged_quantity: '0', notes: '' }] : [];
    }) || []);
  };
  // Receipt defaults intentionally refresh only when the selected PO or server receipt list changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { resetForOrder(order); }, [order, receipts, replacementClaim]);
  const lineTotal = (line: ReceiptLine) => Number(line.accepted_quantity || 0) + Number(line.rejected_quantity || 0) + Number(line.damaged_quantity || 0);
  const remainingQty = (purchaseOrderItemId: number) => {
    const item = order?.items.find((candidate) => candidate.id === purchaseOrderItemId);
    if (!item) return 0;
    const dispositioned = receipts.filter((receipt) => receipt.purchase_order === order?.id && receipt.status === 'ACCEPTED').flatMap((receipt) => receipt.items).filter((line) => line.purchase_order_item === item.id).reduce((total, line) => total + Number(line.accepted_quantity) + Number(line.rejected_quantity) + Number(line.damaged_quantity), 0);
    return Math.max(Number(item.quantity) - dispositioned, 0);
  };
  const valid = lines.length > 0 && (replacementClaim ? lines.every((line) => Number(line.accepted_quantity) === Number(replacementClaim.replacement_quantity) && Number(line.rejected_quantity) === 0 && Number(line.damaged_quantity) === 0) : lines.every((line) => lineTotal(line) > 0 && lineTotal(line) <= remainingQty(line.purchase_order_item) && (!((Number(line.rejected_quantity) > 0 || Number(line.damaged_quantity) > 0)) || line.notes.trim().length > 0)));

  return <FormModal open={open} title={`${replacementClaim ? 'Receive supplier replacement for' : 'Receive'} ${order?.number || 'purchase order'}`} onClose={() => { resetForOrder(null); onClose(); }}>
    <form className="grid gap-4" onSubmit={(event: FormEvent) => { event.preventDefault(); if (valid) onSubmit({ receipt_date: receiptDate, notes, items: lines }); }}>
      <p className="border border-info/20 bg-info/5 p-3 text-sm text-muted">{replacementClaim ? `This replacement closes supplier claim #${replacementClaim.id}. It must accept exactly ${replacementClaim.replacement_quantity} ${replacementClaim.material_name}; a further rejection requires Procurement to open a new claim.` : order?.delivery_destination === 'SITE' && role === 'site_engineer' ? 'You are recording the physical site GRN. Count what arrived, attach delivery details in the notes, and record any rejection or damage. Storekeeper is notified for oversight; only accepted quantities update the site store and may be invoiced.' : 'You are recording the physical Goods Received Note (GRN). Only accepted quantities update stock and may be invoiced. Rejected or damaged quantities require a line reason and remain visible to Procurement and Finance as a supplier exception.'}</p>
      <div className="grid gap-3 md:grid-cols-2"><Field label="Receipt date" required><input className={inputClass} type="date" value={receiptDate} onChange={(event) => setReceiptDate(event.target.value)} /></Field><Field label="Receipt notes"><input className={inputClass} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Delivery note, condition, or escalation reference" /></Field></div>
      <div className="grid gap-3">
        {lines.map((line) => {
          const item = order?.items.find((candidate) => candidate.id === line.purchase_order_item);
          if (!item) return null;
          const update = (key: keyof ReceiptLine, value: string) => setLines((current) => current.map((row) => row.purchase_order_item === line.purchase_order_item ? { ...row, [key]: value } : row));
          const remaining = replacementClaim ? Number(replacementClaim.replacement_quantity) : remainingQty(item.id);
          const exceeds = lineTotal(line) > remaining;
          const needsReason = Number(line.rejected_quantity) > 0 || Number(line.damaged_quantity) > 0;
          return <div key={item.id} className="grid gap-3 border border-border p-3 md:grid-cols-[minmax(180px,1.5fr)_repeat(3,110px)]">
            <div><strong>{item.material_name}</strong><p className="text-xs text-muted">Ordered: {item.quantity} / remaining to receive: {remaining}</p><input className={`${inputClass} mt-2`} value={line.notes} onChange={(event) => update('notes', event.target.value)} placeholder={needsReason ? 'Reason for rejection/damage (required)' : 'Line note'} /><p className="mt-1 text-xs text-danger">{needsReason && !line.notes.trim() ? 'Reason required for rejected or damaged goods.' : ''}</p></div>
            <Field label="Accepted"><input className={inputClass} type="number" min="0" max={remaining} step="0.01" value={line.accepted_quantity} onChange={(event) => update('accepted_quantity', event.target.value)} /></Field>
            <Field label="Rejected"><input disabled={!!replacementClaim} className={inputClass} type="number" min="0" max={remaining} step="0.01" value={line.rejected_quantity} onChange={(event) => update('rejected_quantity', event.target.value)} /></Field>
            <Field label="Damaged" error={exceeds ? `Cannot exceed remaining ${remaining}` : undefined}><input disabled={!!replacementClaim} className={inputClass} type="number" min="0" max={remaining} step="0.01" value={line.damaged_quantity} onChange={(event) => update('damaged_quantity', event.target.value)} /></Field>
          </div>;
        })}
      </div>
      <Button loading={pending} loadingLabel="Recording receipt" disabled={!valid}>Record receipt</Button>
    </form>
  </FormModal>;
}
