import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Trash2 } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { allChoices, canReadExternalTransfers, externalTransfers, type ExternalLine, type ExternalOrder, type ExternalReceipt } from '@/api/external-transfers';
import type { BinLocation, Material, Project, Warehouse } from '@/api/types';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { InventoryTabs } from '@/components/common/inventory-tabs';
import { SearchableSelect } from '@/components/ui/searchable-select';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { RegisterFilters } from '@/components/common/register-filters';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';
import './operations-reference.css';
import './external-transfers.css';

const today = () => new Date().toLocaleDateString('en-CA');
const canCreate = (role: string | null) => ['admin', 'storekeeper', 'procurement_officer'].includes(role || '');
const canReceive = (role: string | null) => ['admin', 'storekeeper'].includes(role || '');

export function ExternalTransfersPage() {
  const { role } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [ownership, setOwnership] = useState('');
  const [pending, setPending] = useState('');
  const [creating, setCreating] = useState(false);
  const orders = useQuery({ queryKey: ['external-transfers', page, search, ownership, pending], queryFn: () => externalTransfers.list({ page, page_size: 5, search, ownership, pending }), enabled: canReadExternalTransfers(role) });
  if (!canReadExternalTransfers(role)) return <p>This inventory workflow is available to warehouse, procurement, finance and admin staff.</p>;
  return <div className="operations-reference external-transfers grid gap-4">
    <PageToolbar title="External transfers" subtitle="Receive materials from another company, without a purchase order.">
      {canCreate(role) && <Button onClick={() => setCreating(true)}><Plus size={16} />New move order</Button>}
    </PageToolbar>
    <InventoryTabs />
    <p className="external-guidance">Permanent transfers join owned stock after admin approval. Borrowed materials remain separately tracked by owner and must be returned. Purchases still use a PO.</p>
    <section className="ops-register" data-pagination-region>
      <div className="ops-register-head"><h2>Move orders</h2></div>
      <RegisterFilters activeCount={Number(Boolean(ownership)) + Number(Boolean(pending))} onClear={() => { setOwnership(''); setPending(''); setPage(1); }}>
        <input className={inputClass} aria-label="Search move orders" placeholder="Search sender, reference or material" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        <select className={inputClass} aria-label="Ownership" value={ownership} onChange={e => { setOwnership(e.target.value); setPage(1); }}><option value="">All ownership</option><option value="PERMANENT">Permanent transfer</option><option value="BORROWED">Borrowed</option></select>
        <select className={inputClass} aria-label="Approval queue" value={pending} onChange={e => { setPending(e.target.value); setPage(1); }}><option value="">All move orders</option><option value="true">Awaiting admin approval</option></select>
      </RegisterFilters>
      {orders.isError ? <div className="p-4" role="alert"><p>{orders.error.message}</p><Button onClick={() => void orders.refetch()} variant="secondary">Retry</Button></div> : <DataTable loading={orders.isLoading} data={orders.data?.results || []} columns={[
        { header: 'Move order', cell: ({ row }) => <Link className="external-link" to={`/inventory/external-transfers/${row.original.id}`}>MO-{row.original.id}<span className="block text-sm text-muted">{row.original.reference}</span></Link> },
        { id: 'actions', header: 'Next action', cell: ({ row }) => <Button size="sm" variant="secondary" asChild><Link to={`/inventory/external-transfers/${row.original.id}`}>{role === 'admin' && row.original.pending_receipts ? 'Review receipt' : canReceive(role) && !row.original.closed && row.original.lines.some(l => Number(l.remaining) > 0) ? 'Confirm arrival' : 'View transfer'}</Link></Button> },
        { header: 'Sending company', accessorKey: 'sender' },
        { header: 'Ownership', cell: ({ row }) => <Badge tone={row.original.ownership === 'BORROWED' ? 'warning' : 'neutral'}>{row.original.ownership === 'BORROWED' ? 'Borrowed' : 'Permanent'}</Badge> },
        { header: 'Warehouse', accessorKey: 'warehouse_name' },
        { header: 'Stage', accessorKey: 'status' },
        { header: 'Return due', cell: ({ row }) => row.original.return_due_date ? <span>{formatDate(row.original.return_due_date)}{row.original.return_due_date < today() && row.original.lines.some(l => Number(l.outstanding) > 0) ? <Badge tone="danger">Overdue</Badge> : null}</span> : '—' },
      ]} emptyTitle="No external transfers" emptyMessage="Create a move order for permanent or borrowed materials coming into your warehouse." />}
      <Pagination page={page} setPage={setPage} pageSize={5} data={orders.data} loading={orders.isFetching} itemLabel="move orders" />
    </section>
    {creating && <CreateMoveOrder onClose={() => setCreating(false)} />}
  </div>;
}

type DraftLine = { key: string; material: string; label: string; quantity: string; unit_cost: string; bin_location: string };
const draftLine = (): DraftLine => ({ key: crypto.randomUUID(), material: '', label: '', quantity: '', unit_cost: '0', bin_location: '' });
function CreateMoveOrder({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate(); const client = useQueryClient();
  const [form, setForm] = useState({ sender: '', reference: '', ownership: 'PERMANENT', warehouse: '', expected_date: today(), return_due_date: '', notes: '' });
  const [lines, setLines] = useState<DraftLine[]>([draftLine()]);
  const warehouses = useQuery({ queryKey: ['warehouses', 'external-choices'], queryFn: () => allChoices<Warehouse>('/api/warehouses/?is_active=true') });
  const materials = useQuery({ queryKey: ['materials', 'external-choices'], queryFn: () => allChoices<Material>('/api/materials/?is_active=true') });
  const bins = useQuery({ queryKey: ['bins', 'external-choices', form.warehouse], queryFn: () => allChoices<BinLocation>(`/api/bin-locations/?is_active=true&warehouse=${form.warehouse}`), enabled: !!form.warehouse });
  const change = (key: keyof typeof form, value: string) => setForm(prev => ({ ...prev, [key]: value }));
  const editLine = (index: number, values: Partial<DraftLine>) => setLines(prev => prev.map((line, i) => i === index ? { ...line, ...values } : line));
  const save = useMutation({ mutationFn: () => externalTransfers.create({ ...form, warehouse: Number(form.warehouse), return_due_date: form.ownership === 'BORROWED' ? form.return_due_date : null, lines: lines.map(line => ({ material: Number(line.material), quantity: line.quantity, unit_cost: form.ownership === 'PERMANENT' ? line.unit_cost : '0', bin_location: line.bin_location ? Number(line.bin_location) : null })) }), onSuccess: result => { void client.invalidateQueries({ queryKey: ['external-transfers'] }); navigate(`/inventory/external-transfers/${result.id}`); onClose(); } });
  return <FormModal open title="New external move order" onClose={onClose}><form className="grid gap-4" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
    <p className="text-sm text-muted">Record the sender’s document. No stock or invoice is created until a physical receipt is approved.</p>
    <div className="external-form-grid">
      <Field label="Sending company" required><input required maxLength={160} className={inputClass} value={form.sender} onChange={e => change('sender', e.target.value)} /></Field>
      <Field label="Sender’s move-order reference" required><input required maxLength={100} className={inputClass} value={form.reference} onChange={e => change('reference', e.target.value)} /></Field>
      <Field label="Ownership" required><select className={inputClass} value={form.ownership} onChange={e => change('ownership', e.target.value)}><option value="PERMANENT">Permanent transfer — our stock</option><option value="BORROWED">Borrowed — return to owner</option></select></Field>
      <Field label="Receiving warehouse" required><select required className={inputClass} value={form.warehouse} onChange={e => { change('warehouse', e.target.value); setLines(prev => prev.map(l => ({ ...l, bin_location: '' }))); }}><option value="">Select warehouse</option>{warehouses.data?.filter(w => !w.project).map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>
      <Field label="Expected arrival" required><input required className={inputClass} type="date" value={form.expected_date} onChange={e => change('expected_date', e.target.value)} /></Field>
      {form.ownership === 'BORROWED' && <Field label="Return due date" required><input required min={form.expected_date} className={inputClass} type="date" value={form.return_due_date} onChange={e => change('return_due_date', e.target.value)} /></Field>}
    </div>
    {warehouses.isError || bins.isError || materials.isError ? <p role="alert">Material or location choices could not load. Reopen this form to retry.</p> : null}
    {lines.map((line, index) => <fieldset key={line.key} className="external-line-form"><legend>Material {index + 1}</legend>
      <Field label="Material" required><SearchableSelect required value={line.material} placeholder={materials.isLoading ? 'Loading materials…' : 'Search material name or code'} options={(materials.data || []).map(m => ({ value: m.id, label: `${m.name} · ${m.code} · ${m.unit}` }))} onChange={id => editLine(index, { material: id })} /></Field>
      <div className="external-form-grid"><Field label="Expected quantity" required><input required type="number" min="0.01" step="0.01" className={inputClass} value={line.quantity} onChange={e => editLine(index, { quantity: e.target.value })} /></Field>
      {form.ownership === 'PERMANENT' && <Field label="Proposed unit value (UGX)" required><input required type="number" min="0" step="0.01" className={inputClass} value={line.unit_cost} onChange={e => editLine(index, { unit_cost: e.target.value })} /></Field>}
      <Field label="Bin / rack (optional)"><select className={inputClass} value={line.bin_location} onChange={e => editLine(index, { bin_location: e.target.value })}><option value="">No bin assigned</option>{bins.data?.map(b => <option key={b.id} value={b.id}>{b.code}</option>)}</select></Field></div>
      {lines.length > 1 && <Button type="button" variant="ghost" onClick={() => setLines(prev => prev.filter((_, i) => i !== index))}><Trash2 size={16} />Remove material {index + 1}</Button>}
    </fieldset>)}
    <Button type="button" variant="secondary" disabled={lines.length >= 100} onClick={() => setLines(prev => [...prev, draftLine()])}><Plus size={16} />Add material</Button>
    <Field label="Transfer terms / notes"><textarea maxLength={4000} className={inputClass} value={form.notes} onChange={e => change('notes', e.target.value)} /></Field>
    {save.isError && <p role="alert" className="text-critical">{save.error.message}</p>}
    <Button disabled={save.isPending || !lines.every(l => l.material)}>{save.isPending ? 'Creating…' : 'Create move order'}</Button>
  </form></FormModal>;
}

type ActionMode = { kind: 'receive' } | { kind: 'close' } | { kind: 'review'; receipt: ExternalReceipt } | { kind: 'reverse'; receipt: ExternalReceipt } | { kind: 'stock'; line: ExternalLine; action: 'ISSUE' | 'PROJECT_RETURN' | 'OWNER_RETURN' };
export function ExternalTransferDetailPage() {
  const { id = '' } = useParams(); const { role } = useAuth();
  const [mode, setMode] = useState<ActionMode | null>(null);
  const orderQuery = useQuery({ queryKey: ['external-transfer', id], queryFn: () => externalTransfers.detail(id), enabled: canReadExternalTransfers(role) });
  if (!canReadExternalTransfers(role)) return <p>You do not have access to external warehouse transfers.</p>;
  if (orderQuery.isError) return <div role="alert"><p>{orderQuery.error.message}</p><Button variant="secondary" onClick={() => void orderQuery.refetch()}>Retry</Button><Link to="/inventory/external-transfers">Back to transfers</Link></div>;
  const order = orderQuery.data;
  if (!order) return <p role="status">Loading move order…</p>;
  const borrowed = order.ownership === 'BORROWED';
  return <div className="operations-reference external-transfers grid gap-4">
    <Button variant="ghost" className="justify-self-start" asChild><Link to="/inventory/external-transfers"><ArrowLeft size={16} />External transfers</Link></Button>
    <PageToolbar title={`Move order MO-${order.id}`} subtitle={`${order.sender} · ${order.reference}`}>
      {canReceive(role) && !order.closed && order.lines.some(l => Number(l.remaining) > 0) && <Button onClick={() => setMode({ kind: 'receive' })}>Confirm arrival</Button>}
      {role === 'admin' && !order.closed && <Button variant="secondary" onClick={() => setMode({ kind: 'close' })}>Close to receipts</Button>}
    </PageToolbar>
    <section className="external-summary">
      <div><span>Ownership</span><strong>{borrowed ? 'Borrowed — remains sender-owned' : 'Permanent — company-owned after posting'}</strong></div>
      <div><span>Destination</span><strong>{order.warehouse_name}</strong></div><div><span>Stage</span><strong>{order.status}</strong></div>
      <div><span>{borrowed ? 'Return due' : 'Expected arrival'}</span><strong>{formatDate(borrowed ? order.return_due_date : order.expected_date)}</strong></div>
    </section>
    <p className="external-guidance">{borrowed ? 'Borrowed quantities are excluded from owned inventory, project costs and normal MR stock availability. Issuing them does not clear the obligation to return them.' : 'Accepted quantities enter the normal warehouse inventory at the admin-approved value. Issue them through an approved material request. No payable is generated.'}</p>
    {order.notes && <p className="text-sm">{order.notes}</p>}
    <section className="ops-register"><div className="ops-register-head"><h2>Materials & balances</h2></div><DataTable data={order.lines} columns={[
      { header: 'Material', cell: ({ row }) => <div><strong>{row.original.material_name}</strong><p className="text-sm text-muted">{row.original.material_code} · {row.original.unit}{row.original.bin_code ? ` · Bin ${row.original.bin_code}` : ''}</p></div> },
      { id: 'actions', header: 'Actions', cell: ({ row }) => role === 'admin' ? <div className="external-actions">{borrowed && Number(row.original.held) > 0 && <Button size="sm" onClick={() => setMode({ kind: 'stock', line: row.original, action: 'ISSUE' })}>Issue borrowed</Button>}{borrowed && Object.keys(row.original.projects).length > 0 && <Button size="sm" variant="secondary" onClick={() => setMode({ kind: 'stock', line: row.original, action: 'PROJECT_RETURN' })}>Return from project</Button>}{Number(borrowed ? row.original.held : Number(row.original.received) - Number(row.original.returned)) > 0 && <Button size="sm" variant="secondary" onClick={() => setMode({ kind: 'stock', line: row.original, action: 'OWNER_RETURN' })}>Return to sender</Button>}</div> : 'Admin controls issues and returns' },
      ...(borrowed ? [{ header: 'Borrowed on hand', accessorKey: 'held' }, { header: 'Still owed', accessorKey: 'outstanding' }] : []),
      { header: 'Expected', cell: ({ row }) => formatNumber(row.original.quantity) },
      { header: 'Posted receipts', cell: ({ row }) => formatNumber(row.original.received) },
      { header: 'Awaiting approval', cell: ({ row }) => formatNumber(row.original.pending) },
      ...(!borrowed ? [{ header: 'Unit value', cell: ({ row }: { row: { original: ExternalLine } }) => <span>{formatUGX(row.original.unit_cost)}<small className="block text-muted">{Number(row.original.received) > 0 ? 'Latest approved value' : 'Proposed value'}</small></span> }] : []),
      { header: 'Returned to sender', cell: ({ row }) => formatNumber(row.original.returned) },
    ]} /></section>
    <section className="ops-register"><div className="ops-register-head"><h2>Receipts & approval</h2><span className="text-sm text-muted">Only accepted quantities enter stock.</span></div>
      {!order.receipts.length && <p className="p-4 text-sm text-muted">No arrivals confirmed. Storekeepers can record a partial or full delivery.</p>}
      {order.receipts.map(receipt => <article className="external-receipt" key={receipt.id}><div className="external-receipt-head"><div><h3>{receipt.reference}</h3><p className="text-sm text-muted">{formatDate(receipt.received_date)} · Received by {receipt.received_by}</p></div><Badge tone={receipt.status === 'POSTED' ? 'success' : receipt.status === 'PENDING' ? 'warning' : 'neutral'}>{receipt.status === 'PENDING' ? 'Awaiting admin approval' : receipt.status}</Badge><div className="external-actions">{role === 'admin' && receipt.status === 'PENDING' && <Button onClick={() => setMode({ kind: 'review', receipt })}>Review & post</Button>}{role === 'admin' && receipt.status === 'POSTED' && <Button variant="secondary" size="sm" onClick={() => setMode({ kind: 'reverse', receipt })}>Reverse receipt</Button>}</div></div>
        <ul className="external-receipt-lines">{receipt.lines.map(line => <li key={line.order_line}><strong>{order.lines.find(l => l.id === line.order_line)?.material_name}</strong><span>Accepted {line.accepted} · Damaged {line.damaged} · Rejected {line.rejected}{line.posted_unit_cost !== null ? ` · Unit value ${formatUGX(line.posted_unit_cost)}` : ''}</span></li>)}</ul>
        {receipt.notes && <p className="text-sm">Count notes: {receipt.notes}</p>}{receipt.reviewed_by && <p className="text-sm text-muted">Reviewed by {receipt.reviewed_by}: {receipt.review_reason}</p>}
      </article>)}
    </section>
    <section className="ops-register"><div className="ops-register-head"><h2>Custody & return history</h2></div><div className="p-4 grid gap-3">
      {order.lines.every(l => !l.events.length) && <p className="text-sm text-muted">Stock history appears after approval.</p>}
      {order.lines.map(line => line.events.map(event => <div className="external-history" key={event.id}><strong>{event.action} · {event.quantity} {line.unit} · {line.material_name}</strong><span>{event.project_name || order.warehouse_name} · {event.actor} · {new Date(event.created_at).toLocaleString()}</span><p>{event.reason}</p></div>))}
    </div></section>
    {mode && <TransferAction key={`${mode.kind}-${'receipt' in mode ? mode.receipt.id : 'line' in mode ? mode.line.id : ''}`} order={order} mode={mode} onClose={() => setMode(null)} />}
  </div>;
}

function TransferAction({ order, mode, onClose }: { order: ExternalOrder; mode: ActionMode; onClose: () => void }) {
  const client = useQueryClient(); const toast = useToast();
  const [reason, setReason] = useState(''); const [reference, setReference] = useState(''); const [date, setDate] = useState(today());
  const [decision, setDecision] = useState('post'); const [quantity, setQuantity] = useState(''); const [project, setProject] = useState('');
  const [requestKey] = useState(() => crypto.randomUUID());
  const [counts, setCounts] = useState<Record<number, { accepted: string; damaged: string; rejected: string }>>(() => Object.fromEntries(order.lines.map(l => [l.id, { accepted: '', damaged: '0', rejected: '0' }])));
  const [costs, setCosts] = useState<Record<number, string>>(() => Object.fromEntries(order.lines.map(l => [l.id, l.unit_cost])));
  const projects = useQuery({ queryKey: ['projects', 'external-choices'], queryFn: () => allChoices<Project>('/api/projects/'), enabled: mode.kind === 'stock' && mode.action !== 'OWNER_RETURN' });
  const title = mode.kind === 'receive' ? 'Confirm physical arrival' : mode.kind === 'review' ? 'Review external receipt' : mode.kind === 'reverse' ? 'Reverse posted receipt' : mode.kind === 'close' ? 'Close move order to receipts' : mode.action === 'ISSUE' ? 'Issue borrowed materials to project' : mode.action === 'PROJECT_RETURN' ? 'Return borrowed materials from project' : 'Return materials to sender';
  const mutation = useMutation({ mutationFn: () => {
    if (mode.kind === 'receive') return externalTransfers.action(order.id, 'receive', { reference, received_date: date, notes: reason, lines: order.lines.filter(l => Object.values(counts[l.id]).some(v => Number(v) > 0)).map(l => ({ order_line: l.id, accepted: counts[l.id].accepted || '0', damaged: counts[l.id].damaged || '0', rejected: counts[l.id].rejected || '0' })) });
    if (mode.kind === 'review') return externalTransfers.action(order.id, 'review', { receipt_id: mode.receipt.id, decision, reason, costs });
    if (mode.kind === 'reverse') return externalTransfers.action(order.id, 'reverse', { receipt_id: mode.receipt.id, reason });
    if (mode.kind === 'close') return externalTransfers.action(order.id, 'close', { reason });
    return externalTransfers.action(order.id, 'stock-action', { line_id: mode.line.id, action: mode.action, quantity, project: project ? Number(project) : null, reason, request_key: requestKey });
  }, onSuccess: () => { void client.invalidateQueries(); toast.push({ title: mode.kind === 'receive' ? 'Receipt sent to admin for approval' : 'Move order updated', tone: 'success' }); onClose(); } });
  return <FormModal open title={title} onClose={onClose}><form className="grid gap-4" onSubmit={e => { e.preventDefault(); mutation.mutate(); }}>
    {mode.kind === 'receive' && <><p className="text-sm text-muted">Enter counted quantities only. Damaged and rejected materials are excluded from available stock. Leave undelivered lines empty.</p><div className="external-form-grid"><Field label="Delivery / receipt reference" required><input required maxLength={100} className={inputClass} value={reference} onChange={e => setReference(e.target.value)} /></Field><Field label="Received date" required><input required type="date" max={today()} className={inputClass} value={date} onChange={e => setDate(e.target.value)} /></Field></div>{order.lines.filter(l => Number(l.remaining) > 0).map(line => <fieldset className="external-line-form" key={line.id}><legend>{line.material_name} · {line.remaining} {line.unit} remaining</legend><div className="external-count-grid">{(['accepted', 'damaged', 'rejected'] as const).map(field => <Field label={`${field[0].toUpperCase()}${field.slice(1)}`} key={field}><input type="number" min="0" max={line.remaining} step="0.01" className={inputClass} value={counts[line.id][field]} onChange={e => setCounts(prev => ({ ...prev, [line.id]: { ...prev[line.id], [field]: e.target.value } }))} /></Field>)}</div></fieldset>)}</>}
    {mode.kind === 'review' && <><p className="text-sm">Check the physical count against {mode.receipt.reference}. {order.ownership === 'BORROWED' ? 'Approved quantities remain sender-owned, with no change to owned-stock value.' : 'Confirm the unit values below. Zero means a deliberately unvalued transfer and must be explained.'}</p><Field label="Decision"><select className={inputClass} value={decision} onChange={e => setDecision(e.target.value)}><option value="post">Approve and post accepted stock</option><option value="reject">Reject confirmation — request a new count</option></select></Field>{mode.receipt.lines.map(item => { const line = order.lines.find(l => l.id === item.order_line)!; return <div className="external-line-form" key={line.id}><strong>{line.material_name}</strong><p className="text-sm">Accepted {item.accepted} · Damaged {item.damaged} · Rejected {item.rejected}</p>{order.ownership === 'PERMANENT' && decision === 'post' && Number(item.accepted) > 0 && <Field label="Approved unit value (UGX)" required><input required className={inputClass} type="number" min="0" step="0.01" value={costs[line.id]} onChange={e => setCosts(prev => ({ ...prev, [line.id]: e.target.value }))} /></Field>}</div>; })}</>}
    {mode.kind === 'reverse' && <p className="text-sm">This removes the posted quantities and value using compensating entries. Reversal is blocked when later stock or custody activity exists; use a return to sender in that case. History is kept.</p>}
    {mode.kind === 'close' && <p className="text-sm">Stops further arrivals against this reference. Existing stock remains available and borrowed return obligations remain open. Incorrect unreceived orders can be closed and replaced.</p>}
    {mode.kind === 'stock' && <><p className="text-sm">{mode.line.material_name} · {order.sender}{order.ownership === 'BORROWED' ? ` · In warehouse: ${mode.line.held} ${mode.line.unit} · Still owed: ${mode.line.outstanding}` : '. Returned stock is valued at the current warehouse average cost, with no payable generated.'}</p>{mode.action !== 'OWNER_RETURN' && <Field label="Project" required><select required className={inputClass} value={project} onChange={e => setProject(e.target.value)}><option value="">Select project</option>{projects.data?.filter(p => mode.action !== 'PROJECT_RETURN' || Number(mode.line.projects[String(p.id)]) > 0).map(p => <option key={p.id} value={p.id}>{p.name}{mode.action === 'PROJECT_RETURN' ? ` — ${mode.line.projects[String(p.id)]} held` : ''}</option>)}</select></Field>}{projects.isError && <p role="alert">Project choices could not load. Reopen the form to retry.</p>}<Field label={`Quantity (${mode.line.unit})`} required><input required className={inputClass} min="0.01" step="0.01" type="number" value={quantity} onChange={e => setQuantity(e.target.value)} /></Field></>}
    <Field label={mode.kind === 'receive' ? 'Count notes / exceptions' : 'Authorization / reason'} required={mode.kind !== 'receive'}><textarea className={inputClass} required={mode.kind !== 'receive'} minLength={mode.kind === 'receive' ? undefined : 10} maxLength={4000} value={reason} onChange={e => setReason(e.target.value)} /></Field>
    {mutation.isError && <p role="alert" className="text-critical">{mutation.error.message}</p>}
    <div className="external-actions"><Button type="button" variant="secondary" onClick={onClose} disabled={mutation.isPending}>Cancel</Button><Button disabled={mutation.isPending || (mode.kind === 'receive' && !Object.values(counts).some(c => Object.values(c).some(v => Number(v) > 0)))}>{mutation.isPending ? 'Saving…' : mode.kind === 'receive' ? 'Confirm & send to admin' : mode.kind === 'review' ? decision === 'post' ? 'Approve & post' : 'Reject confirmation' : 'Confirm'}</Button></div>
  </form></FormModal>;
}
