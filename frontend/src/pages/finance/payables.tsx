import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Download, Eye, Plus, Scale, Send, Trash2, Upload, X } from 'lucide-react';
import { FormEvent, useMemo, useState } from 'react';
import { financeApi, idempotencyKey } from '@/modules/finance/api';
import type { MatchRun, SupplierInvoice } from '@/modules/finance/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { api } from '@/api/services';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { Pagination } from '@/components/common/pagination';
import { RecordContext } from '@/components/common/record-context';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatMoney } from '@/lib/utils';
import { FinanceActivityTimeline, FinancePage, Status } from './components';

type ReasonAction = { invoice: SupplierInvoice; action: 'reject' | 'approve-exception' | 'reject-exception' | 'reverse' } | null;

export function FinancePayablesPage() {
  const { role } = useAuth();
  const list = useListState({ status: '', supplier: '', project: '' });
  const [creating, setCreating] = useState(false);
  const [creatingDirect, setCreatingDirect] = useState(false);
  const [selected, setSelected] = useState<SupplierInvoice | null>(null);
  const [reasonAction, setReasonAction] = useState<ReasonAction>(null);
  const client = useQueryClient();
  const toast = useToast();
  const invoices = useQuery({ queryKey: qk.financeInvoices(list.query), queryFn: () => financeApi.invoices(list.query) });
  const refresh = () => Promise.all([
    client.invalidateQueries({ queryKey: ['finance'] }),
    client.invalidateQueries({ queryKey: qk.workflowBadges }),
  ]);
  const command = useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: string; body?: unknown }) => financeApi.invoiceCommand(id, action, body),
    onSuccess: async (_, variables) => { toast.push({ title: `Invoice action completed: ${variables.action.replace(/-/g, ' ')}`, tone: 'success' }); await refresh(); setReasonAction(null); },
    onError: (error: Error) => toast.push({ title: 'Invoice action failed', message: error.message, tone: 'danger' }),
  });
  const deleteDraft = useMutation({
    mutationFn: financeApi.deleteInvoice,
    onSuccess: async () => { toast.push({ title: 'Draft invoice deleted', tone: 'success' }); await refresh(); },
    onError: (error: Error) => toast.push({ title: 'Could not delete invoice', message: error.message, tone: 'danger' }),
  });
  const columns: ColumnDef<SupplierInvoice>[] = [
    { header: 'Invoice', cell: ({ row }) => <div><strong>{row.original.internal_number}</strong><p className="mt-0.5 text-xs font-semibold text-foreground">{row.original.supplier_name}</p><p className="text-xs text-muted">Supplier ref: {row.original.invoice_number}</p></div> },
    { header: 'Status', cell: ({ row }) => <Status value={row.original.status} /> },
    { header: 'Supplier / PO', cell: ({ row }) => <div><strong>{row.original.supplier_name}</strong><p className="text-xs text-muted">{row.original.purchase_order_number} / {row.original.project_name || 'Overhead'}</p></div> },
    { header: 'Dates', cell: ({ row }) => <div>{formatDate(row.original.invoice_date)}<p className="text-xs text-muted">Due {formatDate(row.original.due_date)}</p></div> },
    { header: 'Total', cell: ({ row }) => formatMoney(row.original.total_amount, row.original.currency) },
    { header: 'Balance', cell: ({ row }) => <strong>{formatMoney(row.original.balance, row.original.currency)}</strong> },
    { id: 'actions', header: '', cell: ({ row }) => <InvoiceActions invoice={row.original} role={role} pendingAction={command.isPending && command.variables?.id === row.original.id ? command.variables.action : null} view={() => setSelected(row.original)} run={(action, body) => command.mutate({ id: row.original.id, action, body })} reason={(action) => setReasonAction({ invoice: row.original, action })} deleteDraft={() => { if (window.confirm(`Delete ${row.original.internal_number}? This draft will be removed and audited.`)) deleteDraft.mutate(row.original.id); }} /> },
  ];
  return <FinancePage eyebrow="Accounts payable" title="Supplier invoices" description="Capture supplier invoices, run three-way matching, authorize exceptions, and post verified liabilities." actions={can.prepareFinance(role) || role === 'admin' ? <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => setCreatingDirect(true)}><Plus className="h-4 w-4" />Work-order invoice</Button><Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" />New invoice</Button></div> : undefined}>
    {role === 'finance_viewer' ? <div className="border border-info/20 bg-info/5 px-3 py-2.5 text-sm text-foreground"><strong>Oversight mode.</strong> You can review invoice status, matching and balances here; preparation, approval and posting remain with the finance team.</div> : null}
    <div className="grid gap-2 border border-border bg-white p-2.5 shadow-panel"><div className="flex gap-2 overflow-x-auto pb-0.5"><Button size="sm" variant={!list.filters.status ? 'default' : 'ghost'} onClick={() => list.setFilter('status', '')}>All</Button>{[['DRAFT', 'Prepare'], ['SUBMITTED', 'Run match'], ['MATCH_EXCEPTION', 'Exceptions'], ['MATCHED', 'Approve'], ['APPROVED', 'Post'], ['PARTIALLY_PAID', 'Part-paid']].map(([value, label]) => <Button key={value} size="sm" variant={list.filters.status === value ? 'default' : 'ghost'} onClick={() => list.setFilter('status', value)}>{label}</Button>)}</div><div className="flex flex-col gap-2 sm:flex-row"><input className={`${inputClass} w-full sm:max-w-md`} value={list.search} onChange={(event) => list.setSearch(event.target.value)} placeholder="Invoice, supplier, PO or project" aria-label="Search supplier invoices" /><select className={`${inputClass} w-full sm:w-auto`} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}><option value="">All statuses</option>{['DRAFT','SUBMITTED','MATCHED','MATCH_EXCEPTION','VERIFIED','APPROVED','POSTED','PARTIALLY_PAID','PAID','REJECTED','REVERSED'].map((value) => <option key={value}>{value}</option>)}</select></div></div>
    <DataTable columns={columns} data={invoices.data?.results || []} mobileSummaryCells={2} emptyTitle={invoices.isLoading ? 'Loading invoices...' : 'No supplier invoices found'} />
    <Pagination page={list.page} setPage={list.setPage} data={invoices.data} />
    <InvoiceModal open={creating} onClose={() => setCreating(false)} />
    <DirectWorkOrderInvoiceModal open={creatingDirect} onClose={() => setCreatingDirect(false)} />
    <InvoiceDetail invoice={selected} onClose={() => setSelected(null)} />
    <ReasonModal state={reasonAction} pending={command.isPending && command.variables?.id === reasonAction?.invoice.id} onClose={() => setReasonAction(null)} onConfirm={(reason) => reasonAction && command.mutate({ id: reasonAction.invoice.id, action: reasonAction.action, body: reasonAction.action === 'reverse' ? { reason, idempotency_key: idempotencyKey('invoice-reverse') } : { reason } })} />
  </FinancePage>;
}

function DirectWorkOrderInvoiceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const suppliers = useQuery({ queryKey: ['suppliers', 'work-order-invoice'], queryFn: () => api.suppliers({ page_size: 100, is_active: true }) });
  const workOrders = useQuery({ queryKey: ['work-orders', 'invoiceable'], queryFn: () => api.workOrders({ page_size: 100, status: 'CLOSED' }) });
  const currencies = useQuery({ queryKey: ['finance', 'currencies'], queryFn: () => financeApi.currencies({ page_size: 100, is_active: true }) });
  const [supplier, setSupplier] = useState('');
  const [workOrder, setWorkOrder] = useState('');
  const [site, setSite] = useState('');
  const [form, setForm] = useState({ invoice_number: '', invoice_date: new Date().toISOString().slice(0, 10), due_date: '', currency: 'UGX', exchange_rate: '1', amount: '', notes: '' });
  const selectedOrder = workOrders.data?.results.find((item) => item.id === Number(workOrder));
  const toast = useToast();
  const client = useQueryClient();
  const mutation = useMutation({ mutationFn: () => {
    if (!supplier || !selectedOrder || !form.amount) throw new Error('Select a supplier, closed work order, and amount.');
    return financeApi.createInvoice({ invoice_number: form.invoice_number, invoice_date: form.invoice_date, due_date: form.due_date || null, currency: form.currency, exchange_rate: form.exchange_rate, supplier: Number(supplier), purchase_order: null, work_order: selectedOrder.id, work_order_site: site ? Number(site) : null, notes: form.notes, idempotency_key: idempotencyKey('work-order-invoice'), items: [{ description: selectedOrder.title, quantity: '1', unit_price: form.amount, taxes: [] }] });
  }, onSuccess: () => { toast.push({ title: 'Work-order invoice draft created', tone: 'success' }); void client.invalidateQueries({ queryKey: ['finance'] }); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not create work-order invoice', message: error.message, tone: 'danger' }) });
  return <FormModal open={open} title="Capture work-order invoice" onClose={onClose}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
    <p className="border border-info/30 bg-info/5 p-3 text-sm">Use this for contractor or service costs that belong directly to a completed work order and do not have a purchase-order receipt.</p>
    <Field label="Supplier / contractor" required><select className={inputClass} value={supplier} onChange={(event) => setSupplier(event.target.value)}><option value="">Select supplier</option>{suppliers.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
    <Field label="Completed work order" required><select className={inputClass} value={workOrder} onChange={(event) => { setWorkOrder(event.target.value); setSite(''); }}><option value="">Select closed work order</option>{workOrders.data?.results.map((item) => <option key={item.id} value={item.id}>{item.number} · {item.title}</option>)}</select></Field>
    {selectedOrder?.site_packages.length ? <Field label="Site package"><select className={inputClass} value={site} onChange={(event) => setSite(event.target.value)}><option value="">Whole work order</option>{selectedOrder.site_packages.map((item) => <option key={item.id} value={item.id}>{item.project_site_name}</option>)}</select></Field> : null}
    <div className="grid gap-3 md:grid-cols-3"><Field label="Supplier invoice number" required><input className={inputClass} value={form.invoice_number} onChange={(event) => setForm({ ...form, invoice_number: event.target.value })} /></Field><Field label="Invoice date" required><input className={inputClass} type="date" value={form.invoice_date} onChange={(event) => setForm({ ...form, invoice_date: event.target.value })} /></Field><Field label="Due date"><input className={inputClass} type="date" min={form.invoice_date} value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></Field></div>
    <div className="grid gap-3 md:grid-cols-3"><Field label="Amount" required><input className={inputClass} type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} /></Field><Field label="Currency" required><select className={inputClass} value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })}>{currencies.data?.results.map((item) => <option key={item.id} value={item.code}>{item.code} / {item.name}</option>)}</select></Field><Field label="Exchange rate" required><input className={inputClass} type="number" min="0.000001" step="0.000001" value={form.exchange_rate} onChange={(event) => setForm({ ...form, exchange_rate: event.target.value })} /></Field></div>
    <Field label="Notes"><textarea className={inputClass} rows={3} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Field><Button loading={mutation.isPending} loadingLabel="Saving draft" disabled={!supplier || !workOrder || !form.invoice_number || !form.amount}>Save work-order invoice</Button>
  </form></FormModal>;
}

function InvoiceActions({ invoice, role, pendingAction, view, run, reason, deleteDraft }: { invoice: SupplierInvoice; role: ReturnType<typeof useAuth>['role']; pendingAction: string | null; view: () => void; run: (action: string, body?: unknown) => void; reason: (action: NonNullable<ReasonAction>['action']) => void; deleteDraft: () => void }) {
  const pending = pendingAction !== null;
  return <div className="flex flex-wrap justify-end gap-1.5"><Button size="sm" variant="ghost" onClick={view}><Eye className="h-3.5 w-3.5" />View</Button>
    {(can.prepareFinance(role) || role === 'admin') && invoice.status === 'DRAFT' ? <Button size="sm" loading={pendingAction === 'submit'} loadingLabel="Submitting" onClick={() => run('submit')} disabled={pending}><Send className="h-3.5 w-3.5" />Submit</Button> : null}
    {(can.prepareFinance(role) || role === 'admin') && invoice.status === 'DRAFT' ? <Button size="sm" variant="ghost" onClick={deleteDraft} disabled={pending}><Trash2 className="h-3.5 w-3.5" />Delete draft</Button> : null}
    {(can.prepareFinance(role) || role === 'admin') && ['SUBMITTED', 'MATCH_EXCEPTION'].includes(invoice.status) ? <Button size="sm" loading={pendingAction === 'run-match'} loadingLabel="Matching" onClick={() => run('run-match', { idempotency_key: idempotencyKey('match') })} disabled={pending}><Scale className="h-3.5 w-3.5" />{invoice.status === 'MATCH_EXCEPTION' ? 'Run match again' : 'Run match'}</Button> : null}
    {role === 'finance_manager' && invoice.status === 'MATCH_EXCEPTION' ? <><Button size="sm" disabled={pending} onClick={() => reason('approve-exception')}><Check className="h-3.5 w-3.5" />Override</Button><Button size="sm" variant="secondary" disabled={pending} onClick={() => reason('reject-exception')}><X className="h-3.5 w-3.5" />Reject exception</Button></> : null}
    {can.manageFinance(role) && ['MATCHED','VERIFIED'].includes(invoice.status) ? <Button size="sm" loading={pendingAction === 'approve'} loadingLabel="Approving" disabled={pending} onClick={() => run('approve')}><Check className="h-3.5 w-3.5" />Approve</Button> : null}
    {can.manageFinance(role) && invoice.status === 'APPROVED' ? <Button size="sm" loading={pendingAction === 'post'} loadingLabel="Posting" disabled={pending} onClick={() => run('post', { idempotency_key: idempotencyKey('invoice-post') })}><Upload className="h-3.5 w-3.5" />Post</Button> : null}
    {can.manageFinance(role) && ['SUBMITTED','MATCH_EXCEPTION','MATCHED','VERIFIED'].includes(invoice.status) ? <Button size="sm" variant="ghost" disabled={pending} onClick={() => reason('reject')}><X className="h-3.5 w-3.5" />Reject</Button> : null}
  </div>;
}

function InvoiceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const orders = useQuery({ queryKey: qk.purchaseOrders({ page_size: 100 }), queryFn: () => api.purchaseOrders({ page_size: 100, ordering: '-created_at' }) });
  const receipts = useQuery({ queryKey: ['goods-received-notes', 'invoiceable'], queryFn: () => api.goodsReceivedNotes({ page_size: 100, ordering: '-receipt_date' }) });
  const existingInvoices = useQuery({ queryKey: qk.financeInvoices({ page_size: 100 }), queryFn: () => financeApi.invoices({ page_size: 100 }) });
  const currencies = useQuery({ queryKey: ['finance', 'currencies'], queryFn: () => financeApi.currencies({ page_size: 100, is_active: true }) });
  const replacementClaims = useQuery({ queryKey: qk.supplierClaims({ page_size: 100 }), queryFn: () => api.supplierClaims({ page_size: 100 }) });
  const [poId, setPoId] = useState('');
  const invoiceableOrders = useMemo(() => {
    const countedStatuses = new Set(['VERIFIED', 'MATCHED', 'APPROVED', 'POSTED', 'PARTIALLY_PAID', 'PAID']);
    const receiptQuantities = new Map<number, { accepted: number; rejected: number; damaged: number }>();
    receipts.data?.results.filter((receipt) => receipt.status === 'ACCEPTED').forEach((receipt) => receipt.items.forEach((item) => {
      const current = receiptQuantities.get(item.purchase_order_item) || { accepted: 0, rejected: 0, damaged: 0 };
      receiptQuantities.set(item.purchase_order_item, {
        accepted: current.accepted + Number(item.accepted_quantity),
        rejected: current.rejected + Number(item.rejected_quantity),
        damaged: current.damaged + Number(item.damaged_quantity),
      });
    }));
    const replacementsByItem = new Map<number, { quantity: number; grns: string[] }>();
    replacementClaims.data?.results.filter((claim) => claim.replacement_grn_item).forEach((claim) => {
      const current = replacementsByItem.get(claim.purchase_order_item) || { quantity: 0, grns: [] };
      replacementsByItem.set(claim.purchase_order_item, { quantity: current.quantity + Number(claim.replacement_quantity), grns: [...current.grns, claim.replacement_grn_number || `claim #${claim.id}`] });
    });
    return (orders.data?.results || []).filter((po) => po.supplier).map((po) => {
      const priorQuantities = new Map<number, number>();
      existingInvoices.data?.results.filter((invoice) => invoice.purchase_order === po.id && countedStatuses.has(invoice.status)).forEach((invoice) => invoice.items.forEach((item) => {
        if (item.purchase_order_item) priorQuantities.set(item.purchase_order_item, (priorQuantities.get(item.purchase_order_item) || 0) + Number(item.quantity));
      }));
      const items = po.items.map((item) => {
        const received = receiptQuantities.get(item.id) || { accepted: 0, rejected: 0, damaged: 0 };
        const alreadyInvoiced = priorQuantities.get(item.id) || 0;
        return {
          ...item,
          quantity: String(Math.max(received.accepted - alreadyInvoiced, 0)),
          acceptedQuantity: received.accepted,
          rejectedQuantity: received.rejected,
          damagedQuantity: received.damaged,
          alreadyInvoiced,
          replacementQuantity: replacementsByItem.get(item.id)?.quantity || 0,
          replacementGrns: replacementsByItem.get(item.id)?.grns || [],
        };
      }).filter((item) => Number(item.quantity) > 0);
      return { ...po, items };
    }).filter((po) => po.items.length);
  }, [existingInvoices.data, orders.data, receipts.data, replacementClaims.data]);
  const selectedPo = useMemo(() => invoiceableOrders.find((po) => po.id === Number(poId)) || null, [invoiceableOrders, poId]);
  const [form, setForm] = useState({ invoice_number: '', invoice_date: new Date().toISOString().slice(0, 10), due_date: '', currency: 'UGX', exchange_rate: '1', discount_amount: '0', freight_amount: '0', other_charges_amount: '0', withholding_amount: '0', notes: '' });
  const [lines, setLines] = useState<Record<number, { quantity: string; unit_price: string }>>({});
  const [attachment, setAttachment] = useState<File | null>(null);
  const toast = useToast();
  const client = useQueryClient();
  const selectAttachment = (file: File | null, input: HTMLInputElement) => {
    if (file?.type.startsWith('image/') && file.size > 1024 * 1024) {
      input.value = '';
      setAttachment(null);
      toast.push({ title: 'Image too large', message: 'Images must be 1 MB or smaller.', tone: 'danger' });
      return;
    }
    setAttachment(file);
  };
  const selectPo = (value: string) => { setPoId(value); const po = invoiceableOrders.find((item) => item.id === Number(value)); setLines(Object.fromEntries((po?.items || []).map((item) => [item.id, { quantity: item.quantity, unit_price: item.unit_price }]))); };
  const mutation = useMutation({ mutationFn: async () => {
    if (!selectedPo?.supplier) throw new Error('Select a purchase order with a supplier.');
    const invoice = await financeApi.createInvoice({ ...form, supplier: selectedPo.supplier, purchase_order: selectedPo.id, due_date: form.due_date || null, idempotency_key: idempotencyKey('invoice'), items: selectedPo.items.map((item) => ({ purchase_order_item: item.id, description: item.material_name, quantity: lines[item.id]?.quantity, unit_price: lines[item.id]?.unit_price, taxes: [] })) });
    if (attachment) await financeApi.uploadInvoiceAttachment(invoice.id, attachment);
    return invoice;
  }, onSuccess: () => { toast.push({ title: 'Invoice draft created', tone: 'success' }); void client.invalidateQueries({ queryKey: ['finance'] }); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not create invoice', message: error.message, tone: 'danger' }) });
  return <FormModal open={open} title="Capture supplier invoice" onClose={onClose}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
    <Field label="Purchase order" required><select className={inputClass} value={poId} onChange={(event) => selectPo(event.target.value)}><option value="">Select PO with invoiceable receipts</option>{invoiceableOrders.map((po) => <option key={po.id} value={po.id}>{po.number} / {po.supplier_name} / {po.status}</option>)}</select></Field>
    {!invoiceableOrders.length && !orders.isLoading && !receipts.isLoading ? <p className="border border-warning/30 bg-warning/10 p-3 text-sm">No accepted, uninvoiced receipt quantities are available. Rejected and damaged goods cannot be invoiced; receive accepted replacement goods or create a credit note where appropriate.</p> : null}
    <div className="grid gap-3 md:grid-cols-3"><Field label="Supplier invoice number" required><input className={inputClass} value={form.invoice_number} onChange={(event) => setForm({ ...form, invoice_number: event.target.value })} /></Field><Field label="Invoice date" required><input className={inputClass} type="date" value={form.invoice_date} onChange={(event) => setForm({ ...form, invoice_date: event.target.value })} /></Field><Field label="Due date"><input className={inputClass} type="date" min={form.invoice_date} value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></Field><Field label="Currency" required><select className={inputClass} value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })}>{currencies.data?.results.map((currency) => <option key={currency.id} value={currency.code}>{currency.code} / {currency.name}</option>)}</select></Field><Field label="Exchange rate" required><input className={inputClass} type="number" min="0.000001" step="0.000001" value={form.exchange_rate} onChange={(event) => setForm({ ...form, exchange_rate: event.target.value })} /></Field></div>
    {selectedPo ? <Card><CardHeader><CardTitle>Accepted quantities available to invoice</CardTitle></CardHeader><CardContent className="grid gap-2 p-2.5 sm:p-3">{selectedPo.items.map((item) => <div key={item.id} className="grid items-end gap-2 border-b border-border pb-2 md:grid-cols-[1fr_130px_160px]"><div><strong className="text-sm">{item.material_name}</strong><p className="text-xs text-muted">Accepted {item.acceptedQuantity} / already invoiced {item.alreadyInvoiced} / available {item.quantity}</p>{item.replacementQuantity > 0 ? <p className="text-xs text-success">Includes {item.replacementQuantity} supplier replacement unit{item.replacementQuantity === 1 ? '' : 's'} received on {item.replacementGrns.join(', ')}.</p> : null}{item.rejectedQuantity > 0 || item.damagedQuantity > 0 ? <p className="text-xs text-warning">Excluded from invoicing: {item.rejectedQuantity} rejected, {item.damagedQuantity} damaged.</p> : null}<p className="text-xs text-muted">Confirmed price {formatMoney(item.unit_price)}</p></div><Field label="Invoice quantity"><input className={inputClass} type="number" min="0.01" max={item.quantity} step="0.01" value={lines[item.id]?.quantity || ''} onChange={(event) => setLines({ ...lines, [item.id]: { ...lines[item.id], quantity: event.target.value } })} /></Field><Field label="Confirmed unit price"><input className={inputClass} type="number" min="0" step="0.01" value={lines[item.id]?.unit_price || ''} onChange={(event) => setLines({ ...lines, [item.id]: { ...lines[item.id], unit_price: event.target.value } })} /></Field></div>)}</CardContent></Card> : null}
    <div className="grid gap-3 md:grid-cols-4">{(['discount_amount','freight_amount','other_charges_amount','withholding_amount'] as const).map((key) => <Field key={key} label={key.replace(/_/g, ' ')}><input className={inputClass} type="number" min="0" step="0.01" value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} /></Field>)}</div>
    <Field label="Supplier invoice or supporting document"><input className={inputClass} type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(event) => selectAttachment(event.target.files?.[0] || null, event.currentTarget)} /><p className="mt-1 text-xs text-muted">Images must be 1 MB or smaller. PDFs remain subject to the existing evidence limit.</p></Field><Field label="Notes"><textarea className={inputClass} rows={3} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Field><Button loading={mutation.isPending} loadingLabel="Saving draft" disabled={!selectedPo || !form.invoice_number}>Save invoice draft</Button>
  </form></FormModal>;
}

function InvoiceDetail({ invoice, onClose }: { invoice: SupplierInvoice | null; onClose: () => void }) {
  const matches = useQuery({ queryKey: ['finance', 'matches', invoice?.id], queryFn: () => financeApi.matchResults(invoice!.id), enabled: !!invoice });
  const cumulative = useQuery({ queryKey: ['purchase-order', invoice?.purchase_order, 'three-way-summary'], queryFn: () => api.purchaseOrderThreeWaySummary(invoice!.purchase_order!), enabled: !!invoice?.purchase_order });
  const latest: MatchRun | undefined = matches.data?.[0];
  return <FormModal open={!!invoice} title={invoice ? `${invoice.internal_number} / ${invoice.supplier_name}` : 'Invoice'} onClose={onClose}>{invoice ? <div className="grid gap-3 sm:gap-4"><div className="flex justify-end"><Button variant="secondary" size="sm" onClick={() => void financeApi.downloadInvoicePdf(invoice.id, invoice.internal_number)}><Download className="h-4 w-4" />PDF record</Button></div><RecordContext items={[{ label: 'Supplier reference', value: invoice.invoice_number }, { label: invoice.purchase_order ? 'Purchase order' : 'Work order', value: invoice.purchase_order_number || invoice.work_order_number || '-' }, { label: 'Status', value: invoice.status }, { label: 'Total', value: formatMoney(invoice.total_amount, invoice.currency) }, { label: 'Paid / credited', value: `${formatMoney(invoice.amount_paid, invoice.currency)} / ${formatMoney(invoice.credit_amount, invoice.currency)}` }, { label: 'Balance', value: formatMoney(invoice.balance, invoice.currency) }]} /><FinanceActivityTimeline objectType="SupplierInvoice" objectId={invoice.id} />{cumulative.data ? <Card><CardHeader><CardTitle>Cumulative PO control</CardTitle></CardHeader><CardContent className="grid gap-2 p-2.5 sm:p-3">{cumulative.data.items.map((item) => <div key={item.purchase_order_item} className="border-b border-border pb-2 text-xs"><strong>{item.material_code} / {item.material_name}</strong><p className="text-muted">Ordered {item.ordered_quantity} / Accepted {item.accepted_quantity} / Invoiced {item.invoiced_quantity} / Paid {item.paid_quantity}</p><p>Available to invoice {item.remaining_invoiceable_quantity} / Remaining to pay {item.remaining_payable_quantity}</p></div>)}</CardContent></Card> : null}<Card><CardHeader><CardTitle>Invoice lines</CardTitle></CardHeader><CardContent className="grid gap-2 p-0">{invoice.items.map((item) => <div key={item.id} className="grid grid-cols-[1fr_auto] gap-2 border-b border-border px-2.5 py-2 text-sm sm:gap-3 sm:px-3 sm:py-2.5"><div><strong>{item.material_code || 'Work-order service'}</strong><p className="text-xs text-muted">{item.description || 'Service cost'} · {item.quantity} at {formatMoney(item.unit_price, invoice.currency)}</p></div><strong>{formatMoney(item.total, invoice.currency)}</strong></div>)}</CardContent></Card>{latest ? <Card><CardHeader><CardTitle>Latest match result / <Status value={latest.status} /></CardTitle></CardHeader><CardContent className="grid gap-2 p-2.5 sm:p-3">{latest.item_results.map((item) => <div key={item.id} className="border border-border p-2.5 text-sm sm:p-3"><div className="flex justify-between"><strong>{item.material_code}</strong><Status value={item.status} /></div><p className="mt-1 text-xs text-muted">{item.explanation}</p><p className="mt-2 text-xs">Ordered {item.ordered_quantity} / Accepted {item.accepted_quantity} / Previous invoice {item.previously_invoiced_quantity} / Current {item.current_invoice_quantity}</p></div>)}</CardContent></Card> : invoice.purchase_order ? <p className="text-sm text-muted">No three-way match has been run.</p> : <p className="border border-info/30 bg-info/5 p-3 text-sm">Direct work-order invoice: three-way PO matching is not required.</p>}</div> : null}</FormModal>;
}

function ReasonModal({ state, pending, onClose, onConfirm }: { state: ReasonAction; pending: boolean; onClose: () => void; onConfirm: (reason: string) => void }) {
  const [reason, setReason] = useState('');
  return <FormModal open={!!state} title={`${state?.action.replace(/-/g, ' ') || 'Review'} invoice`} onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onConfirm(reason); }}><Field label="Reason" required><textarea className={inputClass} rows={4} value={reason} onChange={(event) => setReason(event.target.value)} /></Field><Button loading={pending} loadingLabel="Applying action" variant={state?.action.includes('reject') ? 'warning' : 'default'} disabled={!reason}>Confirm action</Button></form></FormModal>;
}
