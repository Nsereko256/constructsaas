import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, ArrowLeft, Box, CalendarDays, Check, CheckCircle2, ChevronRight, CircleDollarSign, ClipboardList, FileText, Paperclip, Users, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/modules/procurement/api';
import type { RecordActivity } from '@/api/types';
import type { PurchaseRequest } from '@/modules/procurement/types';
import { useAuth } from '@/auth/auth-context';
import { can } from '@/api/roles';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';
import './purchase-request-detail.css';

function PrCard({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  return <section className={`pr-detail-card ${className}`}><header><h2>{title}</h2></header>{children}</section>;
}

function PrMeta({ icon: Icon, label, value }: { icon?: typeof CalendarDays; label: string; value: ReactNode }) {
  return <div className="pr-detail-meta"><span>{Icon ? <Icon size={16} /> : null}<small>{label}</small></span><strong>{value || '—'}</strong></div>;
}

function Activity({ events }: { events: RecordActivity[] }) {
  return <div className="pr-detail-activity">{events.length ? events.slice(0, 6).map((event) => <div key={event.id}><CheckCircle2 size={15} /><span><strong>{event.action.replaceAll('_', ' ')}</strong><small>{event.actor}</small></span><time>{formatDate(event.created_at)}</time></div>) : <p className="pr-detail-muted">No activity has been recorded yet.</p>}</div>;
}

function ApprovalWorkflow({ request }: { request: PurchaseRequest }) {
  const softFinance = ['APPROVED', 'OVERRIDDEN'].includes(request.finance_status);
  const steps = [
    ['Created', true, request.requested_by_username],
    ['Submitted', true, request.requested_by_username],
    ['Project Manager review', !!request.manager_approved_by_name, request.manager_approved_by_name || 'Waiting for manager'],
    ['Admin stock approval', !!request.technical_approved_by_name, request.technical_approved_by_name || 'Pending'],
    ...(request.finance_status !== 'NOT_SUBMITTED' ? [['Finance review', softFinance, request.finance_status_display]] : []),
    ['Storekeeper issue', ['STOCK_ISSUED', 'PARTIAL_STOCK_ISSUED'].includes(request.status), 'Pending'],
  ] as Array<[string, boolean, string]>;
  return <ol className="pr-detail-workflow">{steps.map(([label, complete, detail]) => <li key={label} className={complete ? 'complete' : label === request.next_action_message ? 'current' : ''}><span>{complete ? <Check size={13} /> : <i />}</span><div><strong>{label}</strong><small>{detail}</small></div></li>)}</ol>;
}

export function PurchaseRequestDetailPage() {
  const { requestId = '' } = useParams();
  const navigate = useNavigate();
  const { role, user } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const id = Number(requestId);
  const request = useQuery({ queryKey: ['purchase-request-detail', id], queryFn: () => api.purchaseRequest(id), enabled: Number.isFinite(id) && id > 0 });
  const activity = useQuery({ queryKey: ['purchase-request-activity', id], queryFn: () => api.purchaseRequestActivity(id), enabled: !!request.data });
  const orders = useQuery({ queryKey: ['purchase-request-orders', id], queryFn: () => api.purchaseOrders({ purchase_request: id, page_size: 50 }), enabled: !!request.data });
  const approve = useMutation({ mutationFn: api.approvePurchaseRequest, onSuccess: () => { toast.push({ title: 'Purchase request approved', tone: 'success' }); void queryClient.invalidateQueries({ queryKey: ['purchase-request-detail', id] }); }, onError: (error: Error) => toast.push({ title: 'Approval failed', message: error.message, tone: 'danger' }) });
  const reject = useMutation({ mutationFn: ({ id: requestId, reason }: { id: number; reason: string }) => api.rejectPurchaseRequest(requestId, reason), onSuccess: () => { toast.push({ title: 'Purchase request rejected', tone: 'warning' }); void queryClient.invalidateQueries({ queryKey: ['purchase-request-detail', id] }); }, onError: (error: Error) => toast.push({ title: 'Rejection failed', message: error.message, tone: 'danger' }) });
  const returnRequest = useMutation({ mutationFn: ({ id: requestId, comments }: { id: number; comments: string }) => api.returnPurchaseRequestForCorrection(requestId, comments), onSuccess: () => { toast.push({ title: 'Purchase request returned for correction', tone: 'warning' }); void queryClient.invalidateQueries({ queryKey: ['purchase-request-detail', id] }); }, onError: (error: Error) => toast.push({ title: 'Return failed', message: error.message, tone: 'danger' }) });
  if (request.isLoading) return <main className="pr-detail-page"><p className="pr-detail-loading">Loading purchase request…</p></main>;
  if (request.isError || !request.data) return <main className="pr-detail-page"><section className="pr-detail-empty"><h1>Purchase request unavailable</h1><p>This record may have been removed or you may not have access to it.</p><Button asChild><Link to="/procurement/requests">Back to purchase requests</Link></Button></section></main>;
  const record = request.data;
  const softFinance = Boolean(user?.soft_finance_enabled);
  const canReview = can.approvePr(role) && record.status === 'PENDING';
  const issueAvailable = record.items.some((item) => Number(item.warehouse_available) >= Number(item.outstanding_quantity));
  const returnWithPrompt = () => { const comments = window.prompt('Explain why this request needs correction:'); if (comments?.trim()) returnRequest.mutate({ id, comments: comments.trim() }); };
  const rejectWithPrompt = () => { const reason = window.prompt('Explain why this request is rejected:'); if (reason?.trim()) reject.mutate({ id, reason: reason.trim() }); };
  return <main className="pr-detail-page">
    <div className="pr-detail-breadcrumb"><Button variant="ghost" aria-label="Back to purchase requests" onClick={() => navigate(-1)}><ArrowLeft size={16} />Purchase requests</Button><span>Procurement / Purchase requests / {record.number}</span></div>
    <section className="pr-detail-hero"><div><h1>{record.number}</h1><p>{record.project_name || 'KATONGA'} <span>·</span> {record.title}</p></div><div className="pr-detail-hero-status"><Badge tone={statusTone(record.status)}>{record.status_display}</Badge><Badge tone={statusTone(record.priority)}>{record.priority_display}</Badge></div><div className="pr-detail-actions">{canReview ? <><Button variant="secondary" onClick={returnWithPrompt}><ArrowLeft size={15} />Return</Button><Button variant="destructive" onClick={rejectWithPrompt}><X size={15} />Reject</Button><Button onClick={() => approve.mutate(record.id)} loading={approve.isPending}><Check size={15} />Approve</Button></> : null}<details><summary aria-label="More purchase request actions">⋮</summary><div><Link to="/procurement/requests">Open register</Link></div></details></div></section>
    <section className="pr-detail-meta-row"><PrMeta icon={Users} label="Requested by" value={record.requested_by_username} /><PrMeta icon={CalendarDays} label="Created" value={formatDate(record.created_at)} /><PrMeta icon={CalendarDays} label="Required" value={record.required_date ? formatDate(record.required_date) : 'Not specified'} /><PrMeta icon={Box} label="Destination" value={record.delivery_destination === 'SITE' ? 'Direct to site' : 'Main warehouse'} /><PrMeta icon={Users} label="Assigned to" value={record.manager_approved_by_name || 'Unassigned'} /></section>
    <div className="pr-detail-layout"><div className="pr-detail-main">
      <PrCard title="Reason & justification"><div className="pr-detail-fields"><div><label>Reason</label><p>{record.title}</p></div><div><label>Justification</label><p>{record.justification || 'No justification provided.'}</p></div><div><label>Intended use</label><p>{record.title}</p></div><div><label>Urgency</label><p>{record.priority_display}</p></div><div><label>Requester notes</label><p>{record.items.map((item) => item.notes).filter(Boolean).join(' ') || 'No requester notes.'}</p></div></div>{record.rejection_reason || record.technical_return_reason ? <div className="pr-detail-warning"><AlertCircle size={16} /><span>{record.rejection_reason || record.technical_return_reason}</span></div> : null}</PrCard>
      <PrCard title="Requested materials"><div className="pr-detail-table-wrap"><table><thead><tr><th>Material</th><th>Specification</th><th>Requested</th><th>Approved</th><th>On hand</th><th>Reserved</th><th>Available</th><th>Unit cost</th><th>Estimate</th><th>Fulfilment</th></tr></thead><tbody>{record.items.map((item) => { const available = Number(item.warehouse_available); const outstanding = Number(item.outstanding_quantity); return <tr key={item.id}><td><strong>{item.material_name}</strong><small>{item.material_code}</small></td><td>{item.notes || 'No specification'}</td><td>{formatNumber(item.quantity)} {item.unit}</td><td>{record.status === 'APPROVED' ? formatNumber(item.quantity) : <span className="pr-detail-pending">—<small>Approval pending</small></span>}</td><td>{formatNumber(item.current_stock)}</td><td>0</td><td>{formatNumber(item.warehouse_available)}</td><td>{formatUGX(item.unit_price)}</td><td>{formatUGX(item.estimated_cost)}</td><td><Badge tone={available >= outstanding ? 'success' : issueAvailable ? 'warning' : 'info'}><span className="pr-detail-dot" />{available >= outstanding ? 'Stock available' : issueAvailable ? 'Partial stock' : 'Purchase required'}</Badge></td></tr>; })}</tbody><tfoot><tr><td colSpan={8}>Total estimate</td><td>{formatUGX(record.total_estimated_cost)}</td><td /></tr></tfoot></table></div></PrCard>
      <PrCard title="Warehouse decision"><div className="pr-detail-decision"><PrMeta label="Warehouse" value="Main Warehouse" /><PrMeta label="Stock checked" value={issueAvailable ? 'Can be fulfilled from stock.' : 'Stock is not available.'} /><PrMeta label="Quantity requiring purchase" value={formatNumber(record.items.reduce((sum, item) => sum + Math.max(Number(item.outstanding_quantity) - Number(item.warehouse_available), 0), 0))} /><PrMeta label="Status" value={<Badge tone={issueAvailable ? 'warning' : 'info'}>{record.status === 'APPROVED' ? 'Awaiting approval before reservation' : record.next_action_message}</Badge>} />{record.can_fulfill_from_stock || record.can_request_stock_issue ? <Button variant="secondary" onClick={() => navigate('/procurement/requests?action_queue=my_requests')}><Box size={15} />Open stock record</Button> : null}</div></PrCard>
      <PrCard title="Related records"><div className="pr-detail-related"><Link to="/inventory/movements"><Box size={17} /><span>Stock issue<small>View inventory movement</small></span><ChevronRight size={16} /></Link><Link to={`/procurement/purchase-orders?purchase_request=${record.id}`}><ClipboardList size={17} /><span>Purchase order<small>{orders.data?.count ? `${orders.data.count} linked` : 'Not created'}</small></span><ChevronRight size={16} /></Link><button type="button" disabled><Paperclip size={17} /><span>Attachments<small>0 files</small></span><ChevronRight size={16} /></button></div></PrCard>
    </div><aside className="pr-detail-side">
      <PrCard title="Approval workflow"><ApprovalWorkflow request={record} /></PrCard>
      {softFinance ? <PrCard title="Soft Finance"><div className="pr-detail-finance"><PrMeta label="Budget authorization" value={record.finance_budget_line ? `Budget line #${record.finance_budget_line}` : 'Not assigned'} /><PrMeta label="Request estimate" value={formatUGX(record.total_estimated_cost)} /><PrMeta label="Finance status" value={record.finance_status_display} /></div><p className="pr-detail-info"><CircleDollarSign size={15} />A PR estimate is not a commitment. Finance confirms the budget impact after the PO is priced.</p></PrCard> : null}
      <PrCard title="Activity & audit"><div className="pr-detail-side-link"><Link to={`/procurement/requests/${record.id}/`} >View full audit <ChevronRight size={13} /></Link></div><Activity events={activity.data || []} /></PrCard>
      <PrCard title="Documents"><div className="pr-detail-documents"><FileText size={19} /><span>No supporting files<small>Upload specifications, quotations or approvals.</small></span><Button variant="secondary" disabled>Upload document</Button></div></PrCard>
    </aside></div>
  </main>;
}
