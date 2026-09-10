import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Box, CheckCircle2, ClipboardList, FileText, PackageCheck, Truck } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/modules/procurement/api';
import type { GoodsReceivedNote } from '@/modules/procurement/types';
import type { RecordActivity } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { useAuth } from '@/auth/auth-context';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';
import './procurement-record-detail.css';

function RecordShell({ children, backTo, label }: { children: ReactNode; backTo: string; label: string }) {
  const navigate = useNavigate();
  return <main className="record-detail-page"><div className="record-detail-back"><Button variant="secondary" onClick={() => window.history.length > 1 ? navigate(-1) : navigate(backTo)}><ArrowLeft size={16} />Back to {label}</Button></div>{children}</main>;
}

function LoadingRecord({ label, backTo }: { label: string; backTo: string }) {
  return <RecordShell backTo={backTo} label={label}><div className="record-detail-loading" role="status">Loading {label}…</div></RecordShell>;
}

function RecordNotFound({ label, backTo }: { label: string; backTo: string }) {
  return <RecordShell backTo={backTo} label={label}><section className="record-detail-empty"><h1>{label} unavailable</h1><p>This record may have been removed or you may not have permission to view it.</p><Button asChild><Link to={backTo}>Return to {label}</Link></Button></section></RecordShell>;
}

function DetailCard({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <section className="record-detail-card"><header><h2>{title}</h2>{action}</header>{children}</section>;
}

function DetailMeta({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="record-detail-meta"><span>{label}</span><strong>{value || '—'}</strong></div>;
}

function TextBlock({ children }: { children: string | null | undefined }) {
  return <p className="record-detail-text">{children?.trim() || 'No details recorded.'}</p>;
}

function Workflow({ steps }: { steps: Array<{ label: string; complete: boolean; person?: string; note?: string; date?: string | null }> }) {
  return <ol className="record-detail-timeline">{steps.map((step) => <li key={step.label} className={step.complete ? 'complete' : ''}><span>{step.complete ? <CheckCircle2 size={15} /> : <span />}</span><div><strong>{step.label}</strong><small>{step.person || step.note || (step.complete ? 'Completed' : 'Awaiting action')}</small>{step.date ? <time>{formatDate(step.date)}</time> : null}</div></li>)}</ol>;
}

function ActivityTrail({ events }: { events: RecordActivity[] }) {
  if (!events.length) return <p className="record-detail-muted">No recorded activity is available yet.</p>;
  return <ol className="record-detail-activity">{events.map((event) => <li key={event.id}><div><strong>{event.action.replaceAll('_', ' ')}</strong><small>{event.actor} · {formatDate(event.created_at)}</small></div>{event.message ? <p>{event.message}</p> : null}</li>)}</ol>;
}

export function PurchaseRequestDetailPage() {
  const { requestId = '' } = useParams();
  const id = Number(requestId);
  const { user } = useAuth();
  const request = useQuery({ queryKey: ['purchase-request-detail', id], queryFn: () => api.purchaseRequest(id), enabled: Number.isFinite(id) && id > 0 });
  const activity = useQuery({ queryKey: ['purchase-request-activity', id], queryFn: () => api.purchaseRequestActivity(id), enabled: !!request.data });
  const orders = useQuery({ queryKey: qk.purchaseOrders({ purchase_request: id, page_size: 50 }), queryFn: () => api.purchaseOrders({ purchase_request: id, page_size: 50 }), enabled: !!request.data });
  if (request.isLoading) return <LoadingRecord label="purchase requests" backTo="/procurement/requests" />;
  if (request.isError || !request.data) return <RecordNotFound label="Purchase request" backTo="/procurement/requests" />;
  const record = request.data;
  const softFinance = Boolean(user?.soft_finance_enabled);
  const totalOutstanding = record.items.reduce((sum, item) => sum + Number(item.outstanding_quantity || 0), 0);
  return <RecordShell backTo="/procurement/requests" label="purchase requests">
    <section className="record-detail-hero"><div><p>Procurement / Purchase request</p><h1>{record.number}</h1><span>{record.title}</span></div><div className="record-detail-badges"><Badge tone={statusTone(record.priority)}>{record.priority_display}</Badge><Badge tone={statusTone(record.status)}>{record.status_display}</Badge></div></section>
    <section className="record-detail-primary"><div><strong>Primary next action</strong><p>{record.next_action_message}</p></div>{record.can_create_purchase_order ? <Button asChild><Link to="/procurement/purchase-orders" state={{ purchaseRequestId: record.id }}>Create purchase order</Link></Button> : null}</section>
    <div className="record-detail-grid"><DetailCard title="Request information"><div className="record-detail-meta-grid"><DetailMeta label="Project" value={record.project_name || 'Warehouse replenishment'} /><DetailMeta label="Requester" value={record.requested_by_username} /><DetailMeta label="Created" value={formatDate(record.created_at)} /><DetailMeta label="Last updated" value={formatDate(record.updated_at || record.created_at)} /><DetailMeta label="Assigned reviewer" value={record.manager_approved_by_name || record.technical_approved_by_name || 'Unassigned'} /><DetailMeta label="Outstanding quantity" value={formatNumber(totalOutstanding)} /></div></DetailCard><DetailCard title="Reason and justification"><TextBlock>{record.justification}</TextBlock>{record.technical_return_reason ? <div className="record-detail-callout warning"><strong>Return reason</strong><TextBlock>{record.technical_return_reason}</TextBlock></div> : null}{record.rejection_reason ? <div className="record-detail-callout danger"><strong>Rejection reason</strong><TextBlock>{record.rejection_reason}</TextBlock></div> : null}</DetailCard></div>
    <DetailCard title="Requested materials"><div className="record-detail-table-wrap"><table><thead><tr><th>Material</th><th>Requested</th><th>Unit cost</th><th>Estimate</th><th>On hand</th><th>Available</th><th>Issued</th><th>Outstanding</th><th>Route</th></tr></thead><tbody>{record.items.map((item) => { const available = Number(item.warehouse_available); const outstanding = Number(item.outstanding_quantity); return <tr key={item.id}><td><strong>{item.material_code}</strong><small>{item.material_name}{item.notes ? ` — ${item.notes}` : ''}</small></td><td>{formatNumber(item.quantity)} {item.unit}</td><td>{formatUGX(item.unit_price)}</td><td>{formatUGX(item.estimated_cost)}</td><td>{formatNumber(item.current_stock)}</td><td>{formatNumber(item.warehouse_available)}</td><td>{formatNumber(item.issued_quantity)}</td><td>{formatNumber(item.outstanding_quantity)}</td><td><Badge tone={available >= outstanding ? 'success' : available > 0 ? 'warning' : 'info'}>{available >= outstanding ? 'Warehouse stock' : available > 0 ? 'Partial' : 'Purchase'}</Badge></td></tr>; })}</tbody><tfoot><tr><td colSpan={3}>Request estimate</td><td>{formatUGX(record.total_estimated_cost)}</td><td colSpan={5} /></tr></tfoot></table></div></DetailCard>
    <div className="record-detail-grid"><DetailCard title="Approval workflow"><Workflow steps={[{ label: 'Created', complete: true, person: record.requested_by_username, date: record.created_at }, { label: 'Project Manager review', complete: !!record.manager_approved_by_name, person: record.manager_approved_by_name }, { label: 'Administrative approval', complete: !!record.technical_approved_by_name, person: record.technical_approved_by_name }, { label: 'Finance / budget review', complete: softFinance && ['APPROVED', 'OVERRIDDEN'].includes(record.finance_status), note: softFinance ? record.finance_status_display : 'Disabled' }, { label: 'Stock or Procurement decision', complete: ['STOCK_ISSUED', 'PARTIAL_STOCK_ISSUED', 'PO_CREATED'].includes(record.status) }, { label: 'Completed', complete: ['STOCK_ISSUED', 'PO_CREATED'].includes(record.status) }]} /></DetailCard><DetailCard title="Related records"><div className="record-detail-links"><Link to={`/procurement/purchase-orders?purchase_request=${record.id}`}><ClipboardList size={16} />Purchase orders <b>{orders.data?.count || 0}</b></Link><Link to="/procurement/deliveries"><Truck size={16} />Deliveries</Link><Link to="/procurement/grns"><PackageCheck size={16} />Goods received notes</Link><Link to="/inventory/movements"><Box size={16} />Stock movements</Link></div></DetailCard></div>
    {softFinance ? <DetailCard title="Soft Finance"><div className="record-detail-meta-grid"><DetailMeta label="Finance status" value={record.finance_status_display} /><DetailMeta label="Budget line" value={record.finance_budget_line ? `Budget line #${record.finance_budget_line}` : 'Not selected'} /><DetailMeta label="Request estimate" value={formatUGX(record.total_estimated_cost)} /><DetailMeta label="Budget note" value={record.finance_review_reason || record.finance_return_reason || 'No finance note'} /></div><p className="record-detail-muted">This estimate is not a commitment. A commitment begins only when the purchase order receives final Finance approval.</p></DetailCard> : null}
    <DetailCard title="Activity and audit history"><ActivityTrail events={activity.data || []} /></DetailCard>
  </RecordShell>;
}

function receivedByItem(notes: GoodsReceivedNote[]) { const received = new Map<number, number>(); const rejected = new Map<number, number>(); notes.forEach((note) => note.items.forEach((item) => { received.set(item.purchase_order_item, (received.get(item.purchase_order_item) || 0) + Number(item.accepted_quantity)); rejected.set(item.purchase_order_item, (rejected.get(item.purchase_order_item) || 0) + Number(item.rejected_quantity) + Number(item.damaged_quantity)); })); return { received, rejected }; }

export function PurchaseOrderDetailPage() {
  const { orderId = '' } = useParams();
  const id = Number(orderId);
  const { user } = useAuth();
  const order = useQuery({ queryKey: ['purchase-order-detail', id], queryFn: () => api.purchaseOrder(id), enabled: Number.isFinite(id) && id > 0 });
  const activity = useQuery({ queryKey: ['purchase-order-activity', id], queryFn: () => api.purchaseOrderActivity(id), enabled: !!order.data });
  const sourceRequest = useQuery({ queryKey: ['purchase-order-source-request', order.data?.purchase_request], queryFn: () => api.purchaseRequest(order.data!.purchase_request!), enabled: !!order.data?.purchase_request });
  const receipts = useQuery({ queryKey: ['purchase-order-receipts', id], queryFn: () => api.goodsReceivedNotes({ purchase_order: id, page_size: 50 }), enabled: !!order.data });
  if (order.isLoading) return <LoadingRecord label="purchase orders" backTo="/procurement/purchase-orders" />;
  if (order.isError || !order.data) return <RecordNotFound label="Purchase order" backTo="/procurement/purchase-orders" />;
  const record = order.data;
  const receiptRows = receipts.data?.results || [];
  const quantities = receivedByItem(receiptRows);
  const progress = record.status === 'RECEIVED' ? 100 : record.status === 'PARTIAL' ? 65 : record.status === 'DISPATCH_CONFIRMED' ? 45 : record.status === 'ORDERED' ? 25 : 10;
  return <RecordShell backTo="/procurement/purchase-orders" label="purchase orders">
    <section className="record-detail-hero"><div><p>Procurement / Purchase order</p><h1>{record.number}</h1><span>{record.supplier_name || 'Supplier to be confirmed'}</span></div><div className="record-detail-badges"><Badge tone={statusTone(record.status)}>{record.status_display}</Badge><Badge tone={record.delivery_destination === 'SITE' ? 'info' : 'success'}>{record.delivery_destination_display}</Badge></div></section>
    <section className="record-detail-primary"><div><strong>Primary next action</strong><p>{record.status === 'PENDING' ? 'Send the priced purchase order to Finance for budget review.' : record.status === 'ORDERED' ? 'Confirm supplier dispatch or follow up delivery.' : record.status === 'PARTIAL' ? 'Record the remaining receipt.' : record.status === 'RECEIVED' ? 'Receipt complete; Finance can match the supplier invoice.' : 'Monitor the order progress and evidence.'}</p></div>{record.purchase_request ? <Button asChild><Link to={`/procurement/requests/${record.purchase_request}/`}>View source PR</Link></Button> : null}</section>
    <div className="record-detail-grid"><DetailCard title="Order information"><div className="record-detail-meta-grid"><DetailMeta label="Project" value={record.project_name || 'Warehouse'} /><DetailMeta label="Destination" value={record.delivery_destination_display} /><DetailMeta label="Expected delivery" value={record.expected_delivery_date ? formatDate(record.expected_delivery_date) : 'Not set'} /><DetailMeta label="PO date" value={formatDate(record.created_at)} /><DetailMeta label="Created by" value="Recorded in audit history" /><DetailMeta label="Total value" value={formatUGX(record.total_cost)} /></div></DetailCard><DetailCard title="Source and purpose">{record.purchase_request ? <p className="record-detail-source"><Link to={`/procurement/requests/${record.purchase_request}/`}>{record.purchase_request_number}</Link> — source purchase request</p> : null}<TextBlock>{sourceRequest.data?.justification || record.notes}</TextBlock>{record.notes && sourceRequest.data?.justification ? <div className="record-detail-callout"><strong>Procurement notes</strong><TextBlock>{record.notes}</TextBlock></div> : null}</DetailCard></div>
    <DetailCard title="Ordered materials"><div className="record-detail-table-wrap"><table><thead><tr><th>Material</th><th>Ordered</th><th>Unit price</th><th>Line total</th><th>Received</th><th>Rejected / damaged</th><th>Outstanding</th><th>Receipt</th></tr></thead><tbody>{record.items.map((item) => { const accepted = quantities.received.get(item.id) || 0; const rejected = quantities.rejected.get(item.id) || 0; const outstanding = Math.max(0, Number(item.quantity) - accepted); return <tr key={item.id}><td><strong>{item.material_name}</strong><small>{item.material_code || 'Material'}{item.notes ? ` — ${item.notes}` : ''}</small></td><td>{formatNumber(item.quantity)} {item.unit}</td><td>{formatUGX(item.unit_price)}</td><td>{formatUGX(item.line_total)}</td><td>{formatNumber(accepted)}</td><td>{formatNumber(rejected)}</td><td>{formatNumber(outstanding)}</td><td>{receiptRows.length ? <Link to="/procurement/grns">View GRN</Link> : 'Awaiting receipt'}</td></tr>; })}</tbody><tfoot><tr><td colSpan={3}>Final total</td><td>{formatUGX(record.total_cost)}</td><td colSpan={4} /></tr></tfoot></table></div></DetailCard>
    <div className="record-detail-grid"><DetailCard title="Delivery and receiving"><div className="record-detail-progress"><span><b style={{ width: `${progress}%` }} /></span><strong>{progress}%</strong></div><ol className="record-detail-steps">{['Approved', 'Issued', 'Dispatched', 'In transit', 'Arrived', 'Received', 'Closed'].map((step, index) => <li key={step} className={progress >= (index + 1) / 7 * 100 ? 'complete' : ''}>{step}</li>)}</ol><div className="record-detail-meta-grid"><DetailMeta label="Dispatch confirmed" value={record.dispatch_confirmed_at ? formatDate(record.dispatch_confirmed_at) : 'Not confirmed'} /><DetailMeta label="Received by" value={record.received_by_username || 'Awaiting receipt'} /><DetailMeta label="Actual receipt" value={record.received_at ? formatDate(record.received_at) : 'Not received'} /><DetailMeta label="Delivery revision" value={record.delivery_revision_reason || 'None'} /></div></DetailCard><DetailCard title="Related records"><div className="record-detail-links"><Link to="/procurement/deliveries"><Truck size={16} />Deliveries</Link><Link to="/procurement/grns"><PackageCheck size={16} />Goods received notes <b>{receiptRows.length}</b></Link><Link to="/finance/payables"><FileText size={16} />Invoice matching</Link><Link to="/finance/payments"><FileText size={16} />Payments</Link></div></DetailCard></div>
    {user?.soft_finance_enabled ? <DetailCard title="Soft Finance"><div className="record-detail-meta-grid"><DetailMeta label="Original commitment" value={formatUGX(record.total_cost)} /><DetailMeta label="Remaining commitment" value={record.status === 'RECEIVED' ? formatUGX(0) : formatUGX(record.total_cost)} /><DetailMeta label="Invoices and payments" value="View Finance workspace" /><DetailMeta label="Match status" value="Available after invoice posting" /></div><p className="record-detail-muted">Invoices reduce the remaining commitment and increase actual expenditure; payments settle the liability without creating a second expense.</p></DetailCard> : null}
    <DetailCard title="Activity and audit history"><ActivityTrail events={activity.data || []} /></DetailCard>
  </RecordShell>;
}
