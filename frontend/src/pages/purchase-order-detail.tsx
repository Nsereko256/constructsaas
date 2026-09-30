import { TableScroll } from '@/components/common/table-scroll';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Box, CheckCircle2, FileText, PackageCheck, Truck } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/modules/procurement/api';
import { PurchaseOrderFinanceHandoffModal } from '@/components/common/purchase-order-finance-handoff';
import { useToast } from '@/components/ui/toast';
import type { GoodsReceivedNote } from '@/modules/procurement/types';
import type { RecordActivity } from '@/api/types';
import { useAuth } from '@/auth/auth-context';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';
import './purchase-order-detail.css';

function Card({ title, children }: { title: string; children: ReactNode }) { return <section className="po-detail-card"><header><h2>{title}</h2></header>{children}</section>; }
function Meta({ label, value }: { label: string; value: ReactNode }) { return <div className="po-detail-meta"><span>{label}</span><strong>{value || '—'}</strong></div>; }
function receivedByItem(notes: GoodsReceivedNote[]) { const received = new Map<number, number>(); const rejected = new Map<number, number>(); notes.forEach((note) => note.items.forEach((item) => { received.set(item.purchase_order_item, (received.get(item.purchase_order_item) || 0) + Number(item.accepted_quantity)); rejected.set(item.purchase_order_item, (rejected.get(item.purchase_order_item) || 0) + Number(item.rejected_quantity) + Number(item.damaged_quantity)); })); return { received, rejected }; }
function Workflow({ steps }: { steps: Array<{ label: string; complete: boolean }> }) { const currentStep = steps.findIndex((step) => !step.complete); return <ol className="po-detail-steps">{steps.map((step, index) => <li key={step.label} className={step.complete ? 'complete' : index === currentStep ? 'current' : ''}><span>{step.complete ? <CheckCircle2 size={14} /> : index + 1}</span><small>{step.label}</small></li>)}</ol>; }
function Activity({ events }: { events: RecordActivity[] }) { return events.length ? <ol className="po-detail-activity">{events.slice(0, 6).map((event) => <li key={event.id}><CheckCircle2 size={15} /><div><strong>{event.action.replaceAll('_', ' ')}</strong><small>{event.actor} · {formatDate(event.created_at)}</small>{event.message ? <p>{event.message}</p> : null}</div></li>)}</ol> : <p className="po-detail-muted">No activity has been recorded yet.</p>; }

export function PurchaseOrderDetailPage() {
  const { orderId = '' } = useParams(); const id = Number(orderId); const navigate = useNavigate(); const { user, role } = useAuth();
  const canSeeMaterialCosts = role !== 'site_engineer';
  const queryClient = useQueryClient(); const toast = useToast();
  const [handoffOpen, setHandoffOpen] = useState(false);
  const refresh = () => { for (const key of ['purchase-order-detail', 'purchase-order-activity', 'purchase-orders', 'purchase-requests', 'purchase-request-detail', 'workflow-badges', 'finance']) void queryClient.invalidateQueries({ queryKey: [key] }); };
  const approve = useMutation({ mutationFn: () => api.approvePurchaseOrder(id), onSuccess: () => { refresh(); toast.push({ title: 'Purchase order issued', message: 'The delivery team can now follow up this order.', tone: 'success' }); }, onError: (error: Error) => toast.push({ title: 'PO approval failed', message: error.message, tone: 'danger' }) });
  const dispatch = useMutation({ mutationFn: () => api.confirmDispatch(id), onSuccess: () => { refresh(); toast.push({ title: 'Dispatch confirmed', message: 'The receiving team can now confirm arrival and quantities.', tone: 'success' }); }, onError: (error: Error) => toast.push({ title: 'Dispatch failed', message: error.message, tone: 'danger' }) });
  const order = useQuery({ queryKey: ['purchase-order-detail', id], queryFn: () => api.purchaseOrder(id), enabled: Number.isFinite(id) && id > 0 });
  const activity = useQuery({ queryKey: ['purchase-order-activity', id], queryFn: () => api.purchaseOrderActivity(id), enabled: !!order.data });
  const sourceRequest = useQuery({ queryKey: ['purchase-order-source-request', order.data?.purchase_request], queryFn: () => api.purchaseRequest(order.data!.purchase_request!), enabled: !!order.data?.purchase_request });
  const receipts = useQuery({ queryKey: ['purchase-order-receipts', id], queryFn: () => api.goodsReceivedNotes({ purchase_order: id, page_size: 50 }), enabled: !!order.data });
  if (order.isLoading) return <main className="po-detail-page"><p className="po-detail-loading">Loading purchase order…</p></main>;
  if (order.isError || !order.data) return <main className="po-detail-page"><Card title="Purchase order unavailable"><p className="po-detail-muted">This record may have been removed or you may not have permission to view it.</p><Button asChild><Link to="/procurement/purchase-orders">Return to purchase orders</Link></Button></Card></main>;
  const record = order.data; const receiptRows = receipts.data?.results || []; const summary = record.receipt_summary; const quantities = receivedByItem(receiptRows.filter((receipt) => receipt.status === 'ACCEPTED')); const progress = summary?.percent ?? null;
  const financeReviewEnabled = record.next_step?.finance_review_required ?? false;
  const registerUrl = `/procurement/purchase-orders?search=${encodeURIComponent(record.number)}`;
  const isIssued = ['ORDERED', 'DISPATCH_CONFIRMED', 'PARTIAL', 'RECEIVED'].includes(record.status);
  const workflowSteps = [
    { label: 'Created', complete: true },
    ...(financeReviewEnabled ? [{ label: 'Finance cleared', complete: ['APPROVED', 'OVERRIDDEN'].includes(record.finance_status) }] : []),
    { label: 'Issued', complete: isIssued },
    ...(record.delivery_destination === 'SITE' ? [{ label: 'Dispatch confirmed', complete: Boolean(record.dispatch_confirmed_at) }] : []),
    { label: 'Receipt recorded', complete: Boolean(summary?.receipt_count) },
    { label: 'Receiving finished', complete: record.status === 'RECEIVED' },
  ];
  const step = record.next_step;
  const nextAction = step?.message || 'Open the register to review available actions.';
  const action = step?.action;
  const primaryAction = action?.key === 'send_finance'
    ? <Button onClick={() => setHandoffOpen(true)}>{action.label}</Button>
    : action?.key === 'approve' ? <Button loading={approve.isPending} onClick={() => approve.mutate()}>{action.label}</Button>
    : action?.key === 'dispatch' ? <Button loading={dispatch.isPending} onClick={() => dispatch.mutate()}>{action.label}</Button>
    : action?.href ? <Button asChild><Link to={action.href}>{action.label}</Link></Button> : null;
  return <main className="po-detail-page">
    <PurchaseOrderFinanceHandoffModal order={handoffOpen ? record : null} onClose={() => setHandoffOpen(false)} />
    <div className="po-detail-breadcrumb"><Button variant="ghost" aria-label="Back to purchase orders" onClick={() => navigate("/procurement/purchase-orders")}><ArrowLeft size={16} />Purchase orders</Button><span>Procurement / Purchase orders / {record.number}</span></div>
    <section className="po-detail-hero"><div><p>PROCUREMENT / PURCHASE ORDERS</p><h1>{record.number}</h1><span>{record.supplier_name || 'Supplier to be confirmed'} · {record.project_name || 'No project'}</span></div><div className="po-detail-status"><Badge tone={statusTone(record.status)}>{record.status_display}</Badge><Badge tone={record.delivery_destination === 'SITE' ? 'info' : 'success'}>{record.delivery_destination_display}</Badge></div><div className="po-detail-actions">{primaryAction}{record.purchase_request ? <Button variant="secondary" asChild><Link to={`/procurement/requests/${record.purchase_request}/`}>View source MR</Link></Button> : null}<details><summary aria-label="More purchase order actions">⋮</summary><div><Link to={registerUrl}>Open in register</Link></div></details></div></section>
    <section className="po-detail-meta-row"><Meta label="Supplier" value={record.supplier_name || 'To be confirmed'} /><Meta label="Project / site" value={record.project_name || 'No project'} /><Meta label="PO date" value={formatDate(record.created_at)} /><Meta label="Expected delivery" value={record.expected_delivery_date ? formatDate(record.expected_delivery_date) : 'Not set'} /><Meta label="Destination" value={record.delivery_destination_display} /></section>
    <div className="po-detail-layout"><div className="po-detail-main">
      <Card title="Order summary"><div className="po-detail-summary">{canSeeMaterialCosts ? <div><span>Order value</span><strong>{formatUGX(record.total_cost)}</strong></div> : null}<div><span>Delivery route</span><strong>{record.delivery_destination_display}</strong></div><div><span>Receipt progress</span><strong>{progress === null ? "Unavailable" : `${progress ?? 0}%`}</strong></div></div><div className="po-detail-primary"><div><strong>Next action{step?.owner && step.owner !== "—" ? ` · ${step.owner}` : ""}</strong><p>{nextAction}</p></div></div></Card>
      <Card title="Ordered materials"><TableScroll label="Ordered materials" className="po-detail-table-wrap"><table><thead><tr><th>Material</th><th>Specification</th><th>Ordered</th>{canSeeMaterialCosts ? <><th>Unit price</th><th>Line total</th></> : null}<th>Received</th><th>Outstanding</th><th>Status</th></tr></thead><tbody>{record.items.map((item) => { const line = summary?.lines.find((row) => row.purchase_order_item === item.id); const accepted = line ? Number(line.accepted) : quantities.received.get(item.id) || 0; const rejected = line ? Number(line.exceptions) : quantities.rejected.get(item.id) || 0; const outstanding = Math.max(0, Number(item.quantity) - accepted); return <tr key={item.id}><td><strong>{item.material_name}</strong><small>{item.material_code || 'Material'}</small></td><td>{item.notes || 'No specification'}</td><td>{formatNumber(item.quantity)} {item.unit}</td>{canSeeMaterialCosts ? <><td>{formatUGX(item.unit_price)}</td><td>{formatUGX(item.line_total)}</td></> : null}<td>{formatNumber(accepted)}<small>{rejected ? `${formatNumber(rejected)} rejected/damaged` : 'Accepted'}</small></td><td>{formatNumber(outstanding)} {item.unit}</td><td><Badge tone={outstanding === 0 ? 'success' : accepted > 0 ? 'warning' : 'info'}>{outstanding === 0 ? 'Received' : accepted > 0 ? 'Part received' : 'Awaiting receipt'}</Badge></td></tr>; })}</tbody>{canSeeMaterialCosts ? <tfoot><tr><td colSpan={4}>Final total</td><td>{formatUGX(record.total_cost)}</td><td colSpan={3} /></tr></tfoot> : null}</table></TableScroll></Card>
      <Card title="Delivery and receiving"><div className="po-detail-progress"><div><span><b style={{ width: `${progress ?? 0}%` }} /></span><small>{progress === null ? "Progress unavailable" : `${progress}% accepted coverage`}</small></div><Badge tone={progress === 100 ? 'success' : 'warning'}>{record.status === 'RECEIVED' ? 'Receiving finished' : 'In progress'}</Badge></div><Workflow steps={workflowSteps} /><div className="po-detail-fields"><Meta label="Dispatch confirmed" value={record.dispatch_confirmed_at ? formatDate(record.dispatch_confirmed_at) : 'Not confirmed'} /><Meta label="Received by" value={record.received_by_username || 'Awaiting receipt'} /><Meta label="Actual receipt" value={record.received_at ? formatDate(record.received_at) : 'Not received'} /><Meta label="Delivery revision" value={record.delivery_revision_reason || 'None'} /></div></Card>
      <Card title="Source and purpose"><p className="po-detail-source">{record.purchase_request ? <Link to={`/procurement/requests/${record.purchase_request}/`}>{record.purchase_request_number}</Link> : 'No linked material request'} · source material request</p><p className="po-detail-text">{sourceRequest.data?.justification || record.notes || 'No purpose or procurement notes recorded.'}</p></Card>
    </div><aside className="po-detail-side">
      <Card title="Approval and finance"><div className="po-detail-side-list"><Meta label="Approval status" value={isIssued ? "Issued" : record.status === "CANCELLED" ? "Cancelled" : "Not issued"} /><Meta label="Finance review" value={record.finance_status_display || (user?.soft_finance_enabled ? 'Ready for handoff' : 'Not enabled')} />{canSeeMaterialCosts ? <Meta label="Order value" value={formatUGX(record.total_cost)} /> : null}</div>{record.status === 'PENDING' && record.purchase_request ? <Button variant="secondary" asChild><Link to={`/procurement/requests/${record.purchase_request}/`}>View finance decision</Link></Button> : null}{user?.soft_finance_enabled && canSeeMaterialCosts ? <p className="po-detail-info">Invoices reduce the commitment; posted payments settle the liability without duplicating expenditure.</p> : null}</Card>
      <Card title="Related records"><div className="po-detail-links">{record.purchase_request ? <Link to={`/procurement/requests/${record.purchase_request}/`}><FileText size={16} />Source material request</Link> : null}<Link to={`/procurement/deliveries?search=${encodeURIComponent(record.number)}`}><Truck size={16} />Deliveries</Link><Link to={`/procurement/grns?search=${encodeURIComponent(record.number)}`}><PackageCheck size={16} />Goods received notes <b>{summary?.receipt_count ?? "—"}</b></Link><Link to={`/inventory/movements?purchase_order=${record.id}`}><Box size={16} />Stock movements</Link></div></Card>
      <Card title="Activity and audit"><Activity events={activity.data || []} /></Card>
    </aside></div>
  </main>;
}
