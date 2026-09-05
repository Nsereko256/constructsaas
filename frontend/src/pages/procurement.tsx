import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Box, ChevronRight, CircleDollarSign, ClipboardList, FileText, MoreVertical, Plus, Search, Truck, Upload } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { financeApi } from '@/api/finance-services';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { api } from '@/api/services';
import type { PurchaseOrder, PurchaseRequest } from '@/api/types';
import { useAuth } from '@/auth/auth-context';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { inputClass } from '@/components/ui/field';
import { formatUGX } from '@/lib/utils';
import './procurement-reference.css';

const tabs = [
  ['Overview', '/procurement'], ['Purchase requests', '/procurement/requests'], ['Supplier quotes', '/procurement/rfqs'],
  ['Purchase orders', '/procurement/purchase-orders'], ['Receipts', '/procurement/grns'], ['Deliveries', '/procurement/deliveries'],
  ['Supplier claims', '/procurement/supplier-claims'],
] as const;
const openStatuses = new Set(['DRAFT', 'PENDING', 'ORDERED', 'DISPATCH_CONFIRMED', 'PARTIAL']);
const issuedStatuses = new Set(['ORDERED', 'DISPATCH_CONFIRMED']);
const priorityWeight: Record<string, number> = { URGENT: 4, HIGH: 3, NORMAL: 2, LOW: 1 };

function compactUGX(value: number | string) {
  const amount = Number(value || 0);
  if (amount >= 1_000_000_000) return `UGX ${(amount / 1_000_000_000).toFixed(amount >= 10_000_000_000 ? 1 : 2).replace(/\.0+$/, '')}B`;
  if (amount >= 1_000_000) return `UGX ${(amount / 1_000_000).toFixed(amount >= 100_000_000 ? 1 : 2).replace(/\.0+$/, '')}M`;
  if (amount >= 1_000) return `UGX ${(amount / 1_000).toFixed(amount >= 100_000 ? 0 : 1).replace(/\.0$/, '')}K`;
  return formatUGX(amount);
}

function shortDate(value: string | null) {
  if (!value) return 'Not committed';
  return new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function poTone(status: string, overdue = false): BadgeTone {
  if (overdue || status === 'CANCELLED') return 'danger';
  if (status === 'PENDING' || status === 'DRAFT') return 'warning';
  if (status === 'ORDERED' || status === 'DISPATCH_CONFIRMED') return 'info';
  if (status === 'PARTIAL' || status === 'RECEIVED') return 'success';
  return 'neutral';
}

function priorityTone(priority: string): BadgeTone {
  if (priority === 'URGENT') return 'danger';
  if (priority === 'HIGH' || priority === 'NORMAL') return 'warning';
  return 'info';
}

function exportOrders(rows: PurchaseOrder[]) {
  const csv = [
    ['PO number', 'Project', 'Supplier', 'Value', 'Delivery', 'Status'],
    ...rows.map((order) => [order.number, order.project_name || '', order.supplier_name || '', order.total_cost, order.revised_delivery_date || order.supplier_confirmed_delivery_date || order.expected_delivery_date || '', order.status_display]),
  ].map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(',')).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'procurement-purchase-orders.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ProcurementPage() {
  const { role } = useAuth();
  const [activeTab, setActiveTab] = useState<'all' | 'approval' | 'issued' | 'partial'>('all');
  const [search, setSearch] = useState('');
  const [project, setProject] = useState('');
  const [supplier, setSupplier] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const requests = useQuery({ queryKey: qk.purchaseRequests({ page_size: 100 }), queryFn: () => api.purchaseRequests({ page_size: 100 }) });
  const orders = useQuery({ queryKey: qk.purchaseOrders({ page_size: 100 }), queryFn: () => api.purchaseOrders({ page_size: 100 }) });
  const receipts = useQuery({ queryKey: qk.goodsReceivedNotes({ page_size: 100 }), queryFn: () => api.goodsReceivedNotes({ page_size: 100 }) });
  const workflow = useQuery({ queryKey: qk.workflowBadges, queryFn: api.workflowBadges });
  const invoices = useQuery({ queryKey: qk.financeInvoices({ page_size: 100, source: 'procurement' }), queryFn: () => financeApi.invoices({ page_size: 100 }), enabled: can.viewFinance(role) });

  const requestRows = requests.data?.results || [];
  const orderRows = orders.data?.results || [];
  const receiptRows = receipts.data?.results || [];
  const invoiceRows = invoices.data?.results || [];
  const openOrders = orderRows.filter((order) => openStatuses.has(order.status));
  const pendingRequests = requestRows.filter((request) => request.status === 'PENDING').sort((a, b) => (priorityWeight[b.priority] || 0) - (priorityWeight[a.priority] || 0));
  const pendingOrders = orderRows.filter((order) => order.status === 'PENDING');
  const urgentApprovals = pendingRequests.filter((request) => request.priority === 'URGENT').length;
  const pendingApprovals = pendingRequests.length + pendingOrders.length;
  const inTransit = orderRows.filter((order) => ['DISPATCH_CONFIRMED', 'PARTIAL'].includes(order.status));
  const today = new Date();
  const dateKey = today.toISOString().slice(0, 10);
  const dueToday = inTransit.filter((order) => (order.revised_delivery_date || order.supplier_confirmed_delivery_date || order.expected_delivery_date) === dateKey).length;
  const monthSpend = orderRows.filter((order) => !['DRAFT', 'CANCELLED'].includes(order.status) && order.created_at && new Date(order.created_at).getMonth() === today.getMonth() && new Date(order.created_at).getFullYear() === today.getFullYear()).reduce((sum, order) => sum + Number(order.total_cost || 0), 0);
  const committed = openOrders.reduce((sum, order) => sum + Number(order.total_cost || 0), 0);
  const workflowRecord = workflow.data as unknown as Record<string, number> | undefined;
  const actionTotal = ['requests', 'purchase_orders', 'deliveries', 'supplier_claims'].reduce((sum, key) => sum + Number(workflowRecord?.[key] || 0), 0);
  const draftQuotes = orderRows.filter((order) => order.status === 'DRAFT').length;
  const issuedOrders = orderRows.filter((order) => issuedStatuses.has(order.status));

  const projectOptions = Array.from(new Map(orderRows.filter((order) => order.project).map((order) => [String(order.project), order.project_name || 'Project'])).entries());
  const supplierOptions = Array.from(new Map(orderRows.filter((order) => order.supplier).map((order) => [String(order.supplier), order.supplier_name || 'Supplier'])).entries());
  const filteredOrders = useMemo(() => openOrders.filter((order) => {
    if (activeTab === 'approval' && order.status !== 'PENDING') return false;
    if (activeTab === 'issued' && !issuedStatuses.has(order.status)) return false;
    if (activeTab === 'partial' && order.status !== 'PARTIAL') return false;
    if (project && String(order.project) !== project) return false;
    if (supplier && String(order.supplier) !== supplier) return false;
    if (status && order.status !== status) return false;
    const haystack = `${order.number} ${order.project_name || ''} ${order.supplier_name || ''}`.toLowerCase();
    return !search || haystack.includes(search.toLowerCase());
  }), [activeTab, openOrders, project, search, status, supplier]);
  const pageCount = Math.max(1, Math.ceil(filteredOrders.length / 4));
  const visibleOrders = filteredOrders.slice((page - 1) * 4, page * 4);

  const receivedWithDates = orderRows.filter((order) => order.status === 'RECEIVED' && order.received_at && (order.revised_delivery_date || order.supplier_confirmed_delivery_date || order.expected_delivery_date));
  const onTimeCount = receivedWithDates.filter((order) => new Date(order.received_at!).getTime() <= new Date(`${order.revised_delivery_date || order.supplier_confirmed_delivery_date || order.expected_delivery_date}T23:59:59`).getTime()).length;
  const onTimeRate = receivedWithDates.length ? Math.round(onTimeCount / receivedWithDates.length * 100) : 0;
  const receiptQuantities = receiptRows.flatMap((receipt) => receipt.items).reduce((summary, item) => ({ accepted: summary.accepted + Number(item.accepted_quantity || 0), total: summary.total + Number(item.accepted_quantity || 0) + Number(item.rejected_quantity || 0) + Number(item.damaged_quantity || 0) }), { accepted: 0, total: 0 });
  const qualityRate = receiptQuantities.total ? Math.round(receiptQuantities.accepted / receiptQuantities.total * 100) : 0;
  const receivedWithLeadTime = orderRows.filter((order) => order.status === 'RECEIVED' && order.received_at && order.created_at);
  const averageLeadTime = receivedWithLeadTime.length ? Math.round(receivedWithLeadTime.reduce((sum, order) => sum + Math.max(0, (new Date(order.received_at!).getTime() - new Date(order.created_at).getTime()) / 86400000), 0) / receivedWithLeadTime.length) : 0;

  const setFilter = (setter: (value: string) => void, value: string) => { setter(value); setPage(1); };
  const pipeline = [
    { label: 'Requests', value: requestRows.length, note: pendingRequests.length ? `${pendingRequests.length} need attention` : 'All reviewed', tone: pendingRequests.length ? 'amber' : 'green', href: '/procurement/requests' },
    { label: 'Quotes', value: draftQuotes, note: draftQuotes ? `${draftQuotes} being prepared` : 'No draft quotes', tone: draftQuotes ? 'neutral' : 'green', href: '/procurement/rfqs' },
    { label: 'Approvals', value: pendingApprovals, note: urgentApprovals ? `${urgentApprovals} urgent` : 'No urgent items', tone: pendingApprovals ? 'amber' : 'green', href: '/procurement/requests?action_queue=my_requests' },
    { label: 'POs', value: issuedOrders.length, note: `${issuedOrders.length} issued`, tone: 'neutral', href: '/procurement/purchase-orders' },
    { label: 'Deliveries', value: inTransit.length, note: dueToday ? `${dueToday} due today` : 'No deliveries due', tone: dueToday ? 'amber' : 'green', href: '/procurement/deliveries' },
    { label: 'Receipts', value: receiptRows.length, note: receiptRows.length ? 'Recorded' : 'None recorded', tone: receiptRows.length ? 'green' : 'neutral', href: '/procurement/grns' },
    { label: 'Invoices', value: invoiceRows.length || workflow.data?.supplier_invoices || 0, note: invoices.isError ? 'Finance access required' : invoiceRows.filter((invoice) => !['PAID', 'REVERSED'].includes(invoice.status)).length ? `${invoiceRows.filter((invoice) => !['PAID', 'REVERSED'].includes(invoice.status)).length} pending` : 'All clear', tone: invoiceRows.some((invoice) => !['PAID', 'REVERSED'].includes(invoice.status)) ? 'amber' : 'green', href: '/finance/payables' },
  ];

  return (
    <div className="procurement-reference">
      <section className="procurement-top"><div className="procurement-titlebar"><div><h1>Procurement</h1><p>Control requests, sourcing, orders, deliveries and supplier performance.</p></div><div className="procurement-title-actions"><Button variant="secondary" onClick={() => exportOrders(filteredOrders)}><Upload className="h-4 w-4" />Export</Button>{can.submitPr(role) || can.submitWarehouseReplenishment(role) ? <Button asChild><Link to="/procurement/requests?create=1"><Plus className="h-4 w-4" />New request</Link></Button> : null}</div></div><nav className="procurement-tabs" aria-label="Procurement sections">{tabs.map(([label, href], index) => <Link className={index === 0 ? 'active' : ''} to={href} key={href}>{label}</Link>)}</nav></section>
      <section className="procurement-alert"><AlertTriangle size={17} /><strong>{actionTotal} actions require your attention</strong><Link to="/procurement/requests?action_queue=my_requests">View priority queue <ChevronRight size={14} /></Link></section>
      <section className="procurement-kpis"><ProcurementKpi icon={ClipboardList} tone="amber" label="Pending approvals" value={pendingApprovals} note={urgentApprovals ? `${urgentApprovals} urgent` : 'No urgent items'} noteTone={urgentApprovals ? 'amber' : 'green'} /><ProcurementKpi icon={Box} tone="blue" label="Open purchase orders" value={openOrders.length} note={`${compactUGX(committed)} committed`} noteTone="blue" /><ProcurementKpi icon={Truck} tone="green" label="Deliveries in transit" value={inTransit.length} note={dueToday ? `${dueToday} due today` : 'No deliveries due today'} noteTone={dueToday ? 'amber' : 'green'} /><ProcurementKpi icon={CircleDollarSign} tone="indigo" label="Spend this month" value={compactUGX(monthSpend)} note="Issued PO value" noteTone="green" /></section>
      <section className="procurement-pipeline procurement-panel"><div className="procurement-panel-heading"><h2>Procurement pipeline</h2></div><div className="procurement-pipeline-row">{pipeline.map((item, index) => <Link to={item.href} className="procurement-stage" key={item.label}><span className="procurement-stage-number">{index + 1}</span><span><small>{item.label}</small><strong>{item.value}</strong><em className={item.tone}>{item.note}</em></span>{index < pipeline.length - 1 ? <i aria-hidden="true" /> : null}</Link>)}</div></section>
      <section className="procurement-content-grid"><div className="procurement-orders procurement-panel"><div className="procurement-panel-heading"><h2>Active purchase orders</h2></div><div className="procurement-order-tabs">{[['all', 'All', openOrders.length], ['approval', 'Awaiting approval', pendingOrders.length], ['issued', 'Issued', issuedOrders.length], ['partial', 'Part delivered', orderRows.filter((order) => order.status === 'PARTIAL').length]].map(([value, label, count]) => <button type="button" className={activeTab === value ? 'active' : ''} key={String(value)} onClick={() => { setActiveTab(value as typeof activeTab); setPage(1); }}>{label} <b>{count}</b></button>)}</div><div className="procurement-filters"><label><Search size={14} /><input aria-label="Search purchase orders" placeholder="Search purchase orders" value={search} onChange={(event) => setFilter(setSearch, event.target.value)} /></label><select aria-label="Filter purchase orders by project" className={inputClass} value={project} onChange={(event) => setFilter(setProject, event.target.value)}><option value="">Project</option>{projectOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><select aria-label="Filter purchase orders by supplier" className={inputClass} value={supplier} onChange={(event) => setFilter(setSupplier, event.target.value)}><option value="">Supplier</option>{supplierOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><select aria-label="Filter purchase orders by status" className={inputClass} value={status} onChange={(event) => setFilter(setStatus, event.target.value)}><option value="">Status</option><option value="DRAFT">Draft</option><option value="PENDING">Awaiting approval</option><option value="ORDERED">Ordered</option><option value="DISPATCH_CONFIRMED">Dispatched</option><option value="PARTIAL">Part delivered</option></select></div><div className="procurement-table-wrap"><table className="procurement-table"><thead><tr><th>PO number</th><th>Project</th><th>Supplier</th><th>Value</th><th>Delivery</th><th>Status</th><th>Approval</th><th aria-label="Actions" /></tr></thead><tbody>{visibleOrders.map((order) => { const delivery = order.revised_delivery_date || order.supplier_confirmed_delivery_date || order.expected_delivery_date; return <tr key={order.id}><td><Link to={`/procurement/purchase-orders?search=${encodeURIComponent(order.number)}`}>{order.number}</Link></td><td>{order.project_name || 'Warehouse'}</td><td>{order.supplier_name || 'Not selected'}</td><td>{compactUGX(order.total_cost)}</td><td className={order.is_overdue ? 'overdue' : ''}>{order.is_overdue ? `Overdue · ${shortDate(delivery)}` : shortDate(delivery)}</td><td><Badge tone={poTone(order.status, order.is_overdue)}>{order.is_overdue ? 'Delayed' : order.status_display}</Badge></td><td><Badge tone={order.status === 'PENDING' || order.status === 'DRAFT' ? 'warning' : 'success'}>{order.status === 'PENDING' ? 'Awaiting approval' : order.status === 'DRAFT' ? 'Not submitted' : 'Approved'}</Badge></td><td><Link aria-label={`Open ${order.number}`} to={`/procurement/purchase-orders?search=${encodeURIComponent(order.number)}`}><MoreVertical size={16} /></Link></td></tr>; })}</tbody></table>{!visibleOrders.length ? <p className="procurement-empty">{orders.isLoading ? 'Loading purchase orders…' : 'No purchase orders match this view.'}</p> : null}</div><div className="procurement-table-footer"><span>Showing {visibleOrders.length ? (page - 1) * 4 + 1 : 0} to {(page - 1) * 4 + visibleOrders.length} of {filteredOrders.length} purchase orders</span><span><button type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>‹</button><b>{page}</b><button type="button" disabled={page >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>›</button></span></div></div>
        <aside className="procurement-side-column"><section className="procurement-panel procurement-approvals"><div className="procurement-panel-heading"><h2>Approval queue</h2><Link to="/procurement/requests?action_queue=my_requests">View all</Link></div>{pendingRequests.slice(0, 3).map((request) => <ApprovalRow request={request} key={request.id} />)}{!pendingRequests.length ? <p className="procurement-empty">No purchase requests await approval.</p> : null}</section><section className="procurement-panel procurement-performance"><div className="procurement-panel-heading"><h2>Supplier performance</h2><Link to="/suppliers">View all</Link></div><PerformanceRow label="On-time delivery" value={onTimeRate} display={receivedWithDates.length ? `${onTimeRate}%` : 'No data'} /><PerformanceRow label="Quality acceptance" value={qualityRate} display={receiptQuantities.total ? `${qualityRate}%` : 'No data'} /><PerformanceRow label="Average lead time" value={Math.min(100, averageLeadTime / 30 * 100)} display={receivedWithLeadTime.length ? `${averageLeadTime} days` : 'No data'} /></section></aside></section>
    </div>
  );
}

function ProcurementKpi({ icon: Icon, tone, label, value, note, noteTone }: { icon: typeof ClipboardList; tone: string; label: string; value: number | string; note: string; noteTone: string }) {
  return <article className="procurement-kpi"><span className={`procurement-kpi-icon ${tone}`}><Icon size={24} /></span><div><p>{label}</p><strong>{value}</strong><small className={noteTone}>{note}</small></div></article>;
}

function ApprovalRow({ request }: { request: PurchaseRequest }) {
  return <Link className="procurement-approval-row" to={`/procurement/requests?search=${encodeURIComponent(request.number)}`}><span className="procurement-approval-icon"><FileText size={15} /></span><span><strong>{request.number}</strong><small>{request.title}</small></span><b>{compactUGX(request.total_estimated_cost)}</b><Badge tone={priorityTone(request.priority)}>{request.priority_display}</Badge></Link>;
}

function PerformanceRow({ label, value, display }: { label: string; value: number; display: string }) {
  return <div className="procurement-performance-row"><span>{label}</span><i><b style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></i><strong>{display}</strong></div>;
}
