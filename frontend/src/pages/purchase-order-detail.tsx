import { TableScroll } from '@/components/common/table-scroll';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Box, CheckCircle2, FileText, PackageCheck, Truck } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/modules/procurement/api';
import { can, canReceivePurchaseOrder } from '@/api/roles';
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
  const order = useQuery({ queryKey: ['purchase-order-detail', id], queryFn: () => api.purchaseOrder(id), enabled: Number.isFinite(id) && id > 0 });
  const activity = useQuery({ queryKey: ['purchase-order-activity', id], queryFn: () => api.purchaseOrderActivity(id), enabled: !!order.data });
  const sourceRequest = useQuery({ queryKey: ['purchase-order-source-request', order.data?.purchase_request], queryFn: () => api.purchaseRequest(order.data!.purchase_request!), enabled: !!order.data?.purchase_request });
  const receipts = useQuery({ queryKey: ['purchase-order-receipts', id], queryFn: () => api.goodsReceivedNotes({ purchase_order: id, page_size: 50 }), enabled: !!order.data });
  if (order.isLoading) return <main className="po-detail-page"><p className="po-detail-loading">Loading purchase order…</p></main>;
  if (order.isError || !order.data) return <main className="po-detail-page"><Card title="Purchase order unavailable"><p className="po-detail-muted">This record may have been removed or you may not have permission to view it.</p><Button asChild><Link to="/procurement/purchase-orders">Return to purchase orders</Link></Button></Card></main>;
  const record = order.data; const receiptRows = receipts.data?.results || []; const quantities = receivedByItem(receiptRows); const orderedQuantity = record.items.reduce((sum, item) => sum + Number(item.quantity || 0), 0); const acceptedQuantity = receiptRows.flatMap((receipt) => receipt.items).reduce((sum, item) => sum + Number(item.accepted_quantity || 0), 0); const progress = orderedQuantity ? Math.min(100, Math.round((acceptedQuantity / orderedQuantity) * 100)) : 0;
  const registerUrl = `/procurement/purchase-orders?search=${encodeURIComponent(record.number)}`;
  const receiptUrl = `/procurement/deliveries?search=${encodeURIComponent(record.number)}&open_receipt=${record.id}`;
  const canReceive = canReceivePurchaseOrder(role, record);
  const isIssued = !['PENDING', 'DRAFT', 'RETURNED'].includes(record.status);
  const hasDispatch = Boolean(record.dispatch_confirmed_at);
  const hasReceipt = acceptedQuantity > 0 || Boolean(record.received_at);
  const isClosed = /paid|complete|closed/i.test(record.lifecycle_status_display || record.status_display);
  const workflowSteps = [
    { label: 'Approved', complete: isIssued },
    { label: 'Issued', complete: isIssued },
    { label: 'Dispatched', complete: hasDispatch || hasReceipt },
    { label: 'In transit', complete: hasDispatch || hasReceipt },
    { label: 'Arrived', complete: hasReceipt },
    { label: 'Received', complete: progress >= 100 || record.status === 'RECEIVED' },
    { label: 'Closed', complete: isClosed },
  ];
  const nextAction = record.status === 'PENDING' && can.createPo(role) ? (user?.soft_finance_enabled && ['DRAFT', 'RETURNED'].includes(record.finance_status) ? 'Send the priced purchase order to Finance for budget review.' : 'Approve the purchase order so delivery can begin.') : record.delivery_destination === 'SITE' && record.status === 'ORDERED' && can.createPo(role) ? 'Confirm dispatch to the project site.' : canReceive ? `Record the ${record.delivery_destination === 'SITE' ? 'site' : 'warehouse'} receipt and physical quantities.` : record.status === 'PARTIAL' ? 'Record the remaining receipt.' : record.status === 'RECEIVED' ? 'Receipt complete; Finance can create and match the supplier invoice.' : 'Monitor the order progress and evidence.';
  const continueHref = record.status === 'PENDING' && can.createPo(role)
    ? registerUrl
    : record.delivery_destination === 'SITE' && record.status === 'ORDERED' && can.createPo(role)
      ? `/procurement/deliveries?search=${encodeURIComponent(record.number)}`
      : canReceive
        ? receiptUrl
        : record.status === 'RECEIVED' && ['finance_officer', 'finance_manager', 'admin'].includes(role || '')
          ? `/finance/payables?purchase_order=${record.id}`
          : receiptRows.length ? '/procurement/grns' : registerUrl;
  const continueLabel = record.status === 'PENDING' && can.createPo(role)
    ? (user?.soft_finance_enabled && ['DRAFT', 'RETURNED'].includes(record.finance_status) ? 'Send to Finance' : 'Approve purchase order')
    : record.delivery_destination === 'SITE' && record.status === 'ORDERED' && can.createPo(role)
      ? 'Confirm dispatch'
      : canReceive
        ? 'Record receipt'
        : record.status === 'RECEIVED' && ['finance_officer', 'finance_manager', 'admin'].includes(role || '')
          ? 'Create or match invoice'
          : receiptRows.length ? 'View receipt' : 'Open in register';
  return <main className="po-detail-page">
    <div className="po-detail-breadcrumb"><Button variant="ghost" aria-label="Back to purchase orders" onClick={() => navigate(-1)}><ArrowLeft size={16} />Purchase orders</Button><span>Procurement / Purchase orders / {record.number}</span></div>
    <section className="po-detail-hero"><div><p>PROCUREMENT / PURCHASE ORDERS</p><h1>{record.number}</h1><span>{record.supplier_name || 'Supplier to be confirmed'} · {record.project_name || 'No project'}</span></div><div className="po-detail-status"><Badge tone={statusTone(record.status)}>{record.status_display}</Badge><Badge tone={record.delivery_destination === 'SITE' ? 'info' : 'success'}>{record.delivery_destination_display}</Badge></div><div className="po-detail-actions"><Button asChild><Link to={continueHref}>{continueLabel}</Link></Button>{record.purchase_request ? <Button variant="secondary" asChild><Link to={`/procurement/requests/${record.purchase_request}/`}>View source MR</Link></Button> : null}<details><summary aria-label="More purchase order actions">⋮</summary><div><Link to={registerUrl}>Open in register</Link></div></details></div></section>
    <section className="po-detail-meta-row"><Meta label="Supplier" value={record.supplier_name || 'To be confirmed'} /><Meta label="Project / site" value={record.project_name || 'No project'} /><Meta label="PO date" value={formatDate(record.created_at)} /><Meta label="Expected delivery" value={record.expected_delivery_date ? formatDate(record.expected_delivery_date) : 'Not set'} /><Meta label="Destination" value={record.delivery_destination_display} /></section>
    <div className="po-detail-layout"><div className="po-detail-main">
      <Card title="Order summary"><div className="po-detail-summary">{canSeeMaterialCosts ? <div><span>Order value</span><strong>{formatUGX(record.total_cost)}</strong></div> : null}<div><span>Delivery route</span><strong>{record.delivery_destination_display}</strong></div><div><span>Receipt progress</span><strong>{progress}%</strong></div></div><div className="po-detail-primary"><div><strong>Next action</strong><p>{nextAction}</p></div><Button size="sm" asChild><Link to={continueHref}>{continueLabel}</Link></Button></div></Card>
      <Card title="Ordered materials"><TableScroll label="Ordered materials" className="po-detail-table-wrap"><table><thead><tr><th>Material</th><th>Specification</th><th>Ordered</th>{canSeeMaterialCosts ? <><th>Unit price</th><th>Line total</th></> : null}<th>Received</th><th>Outstanding</th><th>Status</th></tr></thead><tbody>{record.items.map((item) => { const accepted = quantities.received.get(item.id) || 0; const rejected = quantities.rejected.get(item.id) || 0; const outstanding = Math.max(0, Number(item.quantity) - accepted); return <tr key={item.id}><td><strong>{item.material_name}</strong><small>{item.material_code || 'Material'}</small></td><td>{item.notes || 'No specification'}</td><td>{formatNumber(item.quantity)} {item.unit}</td>{canSeeMaterialCosts ? <><td>{formatUGX(item.unit_price)}</td><td>{formatUGX(item.line_total)}</td></> : null}<td>{formatNumber(accepted)}<small>{rejected ? `${formatNumber(rejected)} rejected/damaged` : 'Accepted'}</small></td><td>{formatNumber(outstanding)} {item.unit}</td><td><Badge tone={outstanding === 0 ? 'success' : accepted > 0 ? 'warning' : 'info'}>{outstanding === 0 ? 'Received' : accepted > 0 ? 'Part received' : 'Awaiting receipt'}</Badge></td></tr>; })}</tbody>{canSeeMaterialCosts ? <tfoot><tr><td colSpan={4}>Final total</td><td>{formatUGX(record.total_cost)}</td><td colSpan={3} /></tr></tfoot> : null}</table></TableScroll></Card>
      <Card title="Delivery and receiving"><div className="po-detail-progress"><div><span><b style={{ width: `${progress}%` }} /></span><small>{progress}% receipt completion</small></div><Badge tone={progress === 100 ? 'success' : 'warning'}>{progress === 100 ? 'Received' : 'In progress'}</Badge></div><Workflow steps={workflowSteps} /><div className="po-detail-fields"><Meta label="Dispatch confirmed" value={record.dispatch_confirmed_at ? formatDate(record.dispatch_confirmed_at) : 'Not confirmed'} /><Meta label="Received by" value={record.received_by_username || 'Awaiting receipt'} /><Meta label="Actual receipt" value={record.received_at ? formatDate(record.received_at) : 'Not received'} /><Meta label="Delivery revision" value={record.delivery_revision_reason || 'None'} /></div></Card>
      <Card title="Source and purpose"><p className="po-detail-source">{record.purchase_request ? <Link to={`/procurement/requests/${record.purchase_request}/`}>{record.purchase_request_number}</Link> : 'No linked material request'} · source material request</p><p className="po-detail-text">{sourceRequest.data?.justification || record.notes || 'No purpose or procurement notes recorded.'}</p></Card>
    </div><aside className="po-detail-side">
      <Card title="Approval and finance"><div className="po-detail-side-list"><Meta label="Approval status" value={record.status_display} /><Meta label="Finance review" value={record.finance_status_display || (user?.soft_finance_enabled ? 'Ready for handoff' : 'Not enabled')} />{canSeeMaterialCosts ? <Meta label="Order value" value={formatUGX(record.total_cost)} /> : null}</div>{record.status === 'PENDING' && record.purchase_request ? <Button variant="secondary" asChild><Link to={`/procurement/requests?search=${encodeURIComponent(record.purchase_request_number || '')}`}>View finance decision</Link></Button> : null}{user?.soft_finance_enabled && canSeeMaterialCosts ? <p className="po-detail-info">Invoices reduce the commitment; posted payments settle the liability without duplicating expenditure.</p> : null}</Card>
      <Card title="Related records"><div className="po-detail-links"><Link to={`/procurement/requests/${record.purchase_request}/`}><FileText size={16} />Source material request</Link><Link to="/procurement/deliveries"><Truck size={16} />Deliveries</Link><Link to="/procurement/grns"><PackageCheck size={16} />Goods received notes <b>{receiptRows.length}</b></Link><Link to="/inventory/movements"><Box size={16} />Stock movements</Link></div></Card>
      <Card title="Activity and audit"><Activity events={activity.data || []} /></Card>
    </aside></div>
  </main>;
}
