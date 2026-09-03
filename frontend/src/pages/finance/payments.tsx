import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronRight, Link2, Plus, Send, Upload, X } from 'lucide-react';
import { FormEvent, useState, type ReactNode } from 'react';
import { financeApi, idempotencyKey } from '@/modules/finance/api';
import type { Payment } from '@/modules/finance/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { api } from '@/api/services';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { Pagination } from '@/components/common/pagination';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { SearchableSelect } from '@/components/ui/searchable-select';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatMoney } from '@/lib/utils';
import { FinancePage, Status } from './components';

type PaymentReason = { payment: Payment; action: 'reject' | 'reverse' } | null;

export function FinancePaymentsPage() {
  const { role } = useAuth();
  const list = useListState({ status: '', supplier: '', method: '' });
  const [creating, setCreating] = useState(false);
  const [allocating, setAllocating] = useState<Payment | null>(null);
  const [reason, setReason] = useState<PaymentReason>(null);
  const client = useQueryClient();
  const toast = useToast();
  const payments = useQuery({ queryKey: qk.financePayments(list.query), queryFn: () => financeApi.payments(list.query) });
  const submittedPayments = useQuery({ queryKey: qk.financePayments({ status: 'SUBMITTED', page_size: 5 }), queryFn: () => financeApi.payments({ status: 'SUBMITTED', page_size: 5 }), enabled: can.manageFinance(role) });
  const approvedPayments = useQuery({ queryKey: qk.financePayments({ status: 'APPROVED', page_size: 5 }), queryFn: () => financeApi.payments({ status: 'APPROVED', page_size: 5 }), enabled: can.manageFinance(role) });
  const draftPayments = useQuery({ queryKey: qk.financePayments({ status: 'DRAFT', page_size: 5 }), queryFn: () => financeApi.payments({ status: 'DRAFT', page_size: 5 }), enabled: can.prepareFinance(role) && !can.manageFinance(role) });
  const refresh = () => Promise.all([
    client.invalidateQueries({ queryKey: ['finance'] }),
    client.invalidateQueries({ queryKey: qk.workflowBadges }),
  ]);
  const command = useMutation({ mutationFn: ({ id, action, body }: { id: number; action: string; body?: unknown }) => financeApi.paymentCommand(id, action, body), onSuccess: async (_, variables) => { toast.push({ title: `Payment action completed: ${variables.action}`, tone: 'success' }); await refresh(); setReason(null); }, onError: (error: Error) => toast.push({ title: 'Payment action failed', message: error.message, tone: 'danger' }) });
  const columns: ColumnDef<Payment>[] = [
    { header: 'Voucher', cell: ({ row }) => <div><strong>{row.original.number}</strong><p className="text-xs text-muted">{row.original.voucher_reference || row.original.reference || 'No reference'}</p></div> },
    { header: 'Supplier / account', cell: ({ row }) => <div><strong>{row.original.supplier_name || 'Supplier advance'}</strong><p className="text-xs text-muted">{row.original.source_account_name}</p></div> },
    { header: 'Date', cell: ({ row }) => formatDate(row.original.payment_date) },
    { header: 'Method', cell: ({ row }) => row.original.method.replace(/_/g, ' ') },
    { header: 'Status', cell: ({ row }) => <Status value={row.original.status} /> },
    { header: 'Amount', cell: ({ row }) => formatMoney(row.original.amount, row.original.currency_code) },
    { header: 'Allocated', cell: ({ row }) => <div>{formatMoney(row.original.allocated_amount, row.original.currency_code)}<p className="text-xs text-muted">Open {formatMoney(row.original.unallocated_amount, row.original.currency_code)}</p></div> },
    { id: 'actions', header: '', cell: ({ row }) => { const pendingAction = command.isPending && command.variables?.id === row.original.id ? command.variables.action : null; const pending = pendingAction !== null; return <div className="flex flex-wrap justify-end gap-1.5">{can.prepareFinance(role) && row.original.status === 'DRAFT' ? <><Button size="sm" variant="secondary" disabled={pending} onClick={() => setAllocating(row.original)}><Link2 className="h-3.5 w-3.5" />Allocate / partial pay</Button><Button size="sm" loading={pendingAction === 'submit'} loadingLabel="Submitting" disabled={pending} onClick={() => command.mutate({ id: row.original.id, action: 'submit' })}><Send className="h-3.5 w-3.5" />Submit</Button></> : null}{can.manageFinance(role) && row.original.status === 'SUBMITTED' ? <><Button size="sm" loading={pendingAction === 'approve'} loadingLabel="Approving" disabled={pending} onClick={() => command.mutate({ id: row.original.id, action: 'approve', body: { authorize_advance: false } })}><Check className="h-3.5 w-3.5" />Approve</Button><Button size="sm" variant="ghost" disabled={pending} onClick={() => setReason({ payment: row.original, action: 'reject' })}><X className="h-3.5 w-3.5" />Reject</Button></> : null}{can.manageFinance(role) && row.original.status === 'APPROVED' ? <Button size="sm" loading={pendingAction === 'post'} loadingLabel="Posting" disabled={pending} onClick={() => command.mutate({ id: row.original.id, action: 'post', body: { idempotency_key: idempotencyKey('payment-post') } })}><Upload className="h-3.5 w-3.5" />Post</Button> : null}{can.manageFinance(role) && row.original.status === 'POSTED' && !row.original.is_reversed ? <Button size="sm" variant="secondary" disabled={pending} onClick={() => setReason({ payment: row.original, action: 'reverse' })}>Reverse</Button> : null}</div>; } },
  ];
  return <FinancePage eyebrow="Cash control" title="Supplier payments" description="Prepare payment vouchers, allocate approved invoice balances, and enforce maker-checker posting." actions={can.prepareFinance(role) ? <Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" />New payment</Button> : undefined}>
    {can.manageFinance(role) ? <PaymentAttentionPanel
      submitted={submittedPayments.data?.results || []} submittedCount={submittedPayments.data?.count || 0}
      approved={approvedPayments.data?.results || []} approvedCount={approvedPayments.data?.count || 0}
      onShow={(status) => list.setFilter('status', status)}
      onApprove={(payment) => command.mutate({ id: payment.id, action: 'approve', body: { authorize_advance: false } })}
      onReject={(payment) => setReason({ payment, action: 'reject' })}
      onPost={(payment) => command.mutate({ id: payment.id, action: 'post', body: { idempotency_key: idempotencyKey('payment-post') } })}
      pendingId={command.isPending ? command.variables?.id : null}
    /> : null}
    {can.prepareFinance(role) && !can.manageFinance(role) ? <DraftAttentionPanel drafts={draftPayments.data?.results || []} count={draftPayments.data?.count || 0} onShow={() => list.setFilter('status', 'DRAFT')} /> : null}
    <div className="flex flex-wrap gap-2 border border-border bg-white p-3 shadow-panel"><input className={inputClass} value={list.search} onChange={(event) => list.setSearch(event.target.value)} placeholder="Voucher, supplier or reference" aria-label="Search payments" /><select className={inputClass} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}><option value="">All statuses</option>{['DRAFT','SUBMITTED','APPROVED','POSTED','REJECTED','REVERSED'].map((value) => <option key={value}>{value}</option>)}</select><select className={inputClass} value={list.filters.method} onChange={(event) => list.setFilter('method', event.target.value)}><option value="">All methods</option><option>BANK</option><option>MOBILE_MONEY</option><option>CHEQUE</option><option>CASH</option></select></div>
    <DataTable columns={columns} data={payments.data?.results || []} emptyTitle={payments.isLoading ? 'Loading payments...' : 'No supplier payments found'} /><Pagination page={list.page} setPage={list.setPage} data={payments.data} />
    <PaymentModal open={creating} onClose={() => setCreating(false)} /><AllocationModal payment={allocating} onClose={() => setAllocating(null)} /><ReasonModal state={reason} pending={command.isPending && command.variables?.id === reason?.payment.id} onClose={() => setReason(null)} onConfirm={(text) => reason && command.mutate({ id: reason.payment.id, action: reason.action, body: reason.action === 'reverse' ? { reason: text, idempotency_key: idempotencyKey('payment-reverse') } : { reason: text } })} />
  </FinancePage>;
}

function PaymentAttentionPanel({ submitted, submittedCount, approved, approvedCount, onShow, onApprove, onReject, onPost, pendingId }: { submitted: Payment[]; submittedCount: number; approved: Payment[]; approvedCount: number; onShow: (status: string) => void; onApprove: (payment: Payment) => void; onReject: (payment: Payment) => void; onPost: (payment: Payment) => void; pendingId: number | null | undefined }) {
  return <section className="overflow-hidden border border-primary/25 bg-white shadow-panel">
    <div className="flex flex-wrap items-start justify-between gap-2 border-b border-primary/15 bg-primary/5 px-3 py-2.5 sm:px-4"><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-primary">Action required</p><h3 className="mt-0.5 font-black">Your payment decisions</h3><p className="mt-0.5 text-xs text-muted">Approve prepared vouchers first; then post the approved vouchers to the ledger.</p></div><strong className="rounded-full bg-primary px-2.5 py-1 text-xs text-white">{submittedCount + approvedCount} open</strong></div>
    <div className="grid divide-y divide-border lg:grid-cols-2 lg:divide-x lg:divide-y-0">
      <AttentionLane title="Awaiting your approval" count={submittedCount} empty="No submitted payment vouchers need approval." onShow={() => onShow('SUBMITTED')}>{submitted.map((payment) => <div key={payment.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-2 first:border-t-0"><div><strong className="text-sm">{payment.number}</strong><p className="text-xs text-muted">{payment.supplier_name || 'Supplier advance'} · {formatMoney(payment.amount, payment.currency_code)}</p></div><div className="flex gap-1"><Button size="sm" loading={pendingId === payment.id} loadingLabel="Approving" onClick={() => onApprove(payment)}><Check className="h-3.5 w-3.5" />Approve</Button><Button size="sm" variant="ghost" disabled={pendingId !== null} onClick={() => onReject(payment)}><X className="h-3.5 w-3.5" />Reject</Button></div></div>)}</AttentionLane>
      <AttentionLane title="Approved - post to ledger" count={approvedCount} empty="No approved payment vouchers are waiting to be posted." onShow={() => onShow('APPROVED')}>{approved.map((payment) => <div key={payment.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-2 first:border-t-0"><div><strong className="text-sm">{payment.number}</strong><p className="text-xs text-muted">{payment.supplier_name || 'Supplier advance'} · {formatMoney(payment.amount, payment.currency_code)}</p></div><Button size="sm" loading={pendingId === payment.id} loadingLabel="Posting" onClick={() => onPost(payment)}><Upload className="h-3.5 w-3.5" />Post</Button></div>)}</AttentionLane>
    </div>
  </section>;
}

function AttentionLane({ title, count, empty, onShow, children }: { title: string; count: number; empty: string; onShow: () => void; children: ReactNode }) {
  return <div className="p-3"><div className="mb-2 flex items-center justify-between gap-2"><strong className="text-sm">{title}</strong><Button size="sm" variant="ghost" onClick={onShow}>View all <ChevronRight className="h-3.5 w-3.5" /></Button></div>{count ? <><div className="grid gap-1.5">{children}</div>{count > 5 ? <p className="mt-2 text-xs text-muted">Showing 5 of {count} vouchers.</p> : null}</> : <p className="text-sm text-muted">{empty}</p>}</div>;
}

function DraftAttentionPanel({ drafts, count, onShow }: { drafts: Payment[]; count: number; onShow: () => void }) {
  return <section className="flex flex-wrap items-center justify-between gap-3 border border-warning/25 bg-warning/5 p-3 shadow-panel"><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-warning">Action required</p><strong className="mt-0.5 block">{count} payment draft{count === 1 ? '' : 's'} need preparation</strong><p className="mt-0.5 text-xs text-muted">Allocate to posted invoices where applicable, then submit each voucher for Finance Manager approval.</p>{drafts.slice(0, 3).map((payment) => <p key={payment.id} className="mt-1 text-xs text-muted">{payment.number} · {payment.supplier_name || 'Supplier advance'} · {formatMoney(payment.amount, payment.currency_code)}</p>)}</div><Button size="sm" variant="secondary" onClick={onShow}>Open drafts <ChevronRight className="h-3.5 w-3.5" /></Button></section>;
}

function PaymentModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const suppliers = useQuery({ queryKey: qk.suppliers({ page_size: 100 }), queryFn: () => api.suppliers({ page_size: 100, is_active: true }) });
  const accounts = useQuery({ queryKey: qk.financeAccounts({ page_size: 100, account_type: 'ASSET' }), queryFn: () => financeApi.accounts({ page_size: 100, account_type: 'ASSET', is_active: true }) });
  const currencies = useQuery({ queryKey: ['finance', 'currencies'], queryFn: () => financeApi.currencies({ page_size: 100, is_active: true }) });
  const [form, setForm] = useState({ supplier: '', source_account: '', currency: '', exchange_rate: '1', amount: '', payment_date: new Date().toISOString().slice(0, 10), method: 'BANK', reference: '', voucher_reference: '', notes: '' });
  const client = useQueryClient(); const toast = useToast();
  const mutation = useMutation({ mutationFn: () => financeApi.createPayment({ ...form, supplier: Number(form.supplier), source_account: Number(form.source_account), currency: Number(form.currency), idempotency_key: idempotencyKey('payment') }), onSuccess: () => { toast.push({ title: 'Payment voucher draft created', tone: 'success' }); void client.invalidateQueries({ queryKey: ['finance'] }); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not create payment', message: error.message, tone: 'danger' }) });
  return <FormModal open={open} title="Prepare supplier payment" onClose={onClose}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}><div className="grid gap-3 md:grid-cols-2"><Field label="Supplier" required><SearchableSelect required value={form.supplier} onChange={(supplier) => setForm({ ...form, supplier })} options={(suppliers.data?.results || []).map((supplier) => ({ value: supplier.id, label: supplier.name }))} placeholder="Search supplier" /></Field><Field label="Cash or bank account" required><SearchableSelect required value={form.source_account} onChange={(source_account) => setForm({ ...form, source_account })} options={(accounts.data?.results || []).map((account) => ({ value: account.id, label: `${account.code} / ${account.name}` }))} placeholder="Search account" /></Field><Field label="Currency" required><SearchableSelect required value={form.currency} onChange={(currency) => setForm({ ...form, currency })} options={(currencies.data?.results || []).map((currency) => ({ value: currency.id, label: `${currency.code} / ${currency.name}` }))} placeholder="Search currency" /></Field><Field label="Exchange rate" required><input className={inputClass} type="number" min="0.000001" step="0.000001" value={form.exchange_rate} onChange={(event) => setForm({ ...form, exchange_rate: event.target.value })} /></Field><Field label="Amount" required><input className={inputClass} type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} /></Field><Field label="Payment date" required><input className={inputClass} type="date" value={form.payment_date} onChange={(event) => setForm({ ...form, payment_date: event.target.value })} /></Field><Field label="Method"><select className={inputClass} value={form.method} onChange={(event) => setForm({ ...form, method: event.target.value })}><option value="BANK">Bank transfer</option><option value="MOBILE_MONEY">Mobile money</option><option value="CHEQUE">Cheque</option><option value="CASH">Cash</option></select></Field><Field label="Transaction reference"><input className={inputClass} value={form.reference} onChange={(event) => setForm({ ...form, reference: event.target.value })} /></Field><Field label="Voucher reference"><input className={inputClass} value={form.voucher_reference} onChange={(event) => setForm({ ...form, voucher_reference: event.target.value })} /></Field></div><Field label="Notes"><textarea className={inputClass} rows={3} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Field><Button loading={mutation.isPending} loadingLabel="Creating draft" disabled={!form.supplier || !form.source_account || !form.currency || !form.amount}>Create payment draft</Button></form></FormModal>;
}

function AllocationModal({ payment, onClose }: { payment: Payment | null; onClose: () => void }) {
  const invoices = useQuery({ queryKey: qk.financeInvoices({ supplier: payment?.supplier, page_size: 100 }), queryFn: () => financeApi.invoices({ supplier: payment!.supplier, page_size: 100 }), enabled: !!payment });
  const [invoice, setInvoice] = useState(''); const [amount, setAmount] = useState(''); const client = useQueryClient(); const toast = useToast();
  const selectedInvoice = invoices.data?.results.find((item) => item.id === Number(invoice));
  const remainingAfterAllocation = selectedInvoice ? Math.max(Number(selectedInvoice.balance) - (Number(amount) || 0), 0) : null;
  const mutation = useMutation({ mutationFn: () => financeApi.paymentCommand(payment!.id, 'allocate', { invoice: Number(invoice), amount }), onSuccess: () => { toast.push({ title: 'Invoice allocation added', tone: 'success' }); void client.invalidateQueries({ queryKey: ['finance'] }); onClose(); }, onError: (error: Error) => toast.push({ title: 'Allocation failed', message: error.message, tone: 'danger' }) });
  return <FormModal open={!!payment} title={`Pay invoice in full or partially / ${payment?.number || 'payment'}`} onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}><p className="border border-border bg-background p-3 text-sm">Available to allocate: <strong>{formatMoney(payment?.unallocated_amount, payment?.currency_code)}</strong></p><p className="text-sm text-muted">Apply any amount up to the invoice balance. The invoice remains <strong>Partially paid</strong> until its balance reaches zero.</p><Field label="Posted supplier invoice" required><SearchableSelect required value={invoice} onChange={setInvoice} options={(invoices.data?.results || []).filter((item) => ['POSTED','PARTIALLY_PAID'].includes(item.status) && Number(item.balance) > 0).map((item) => ({ value: item.id, label: `${item.internal_number} / balance ${formatMoney(item.balance, item.currency)}` }))} placeholder="Search invoice" /></Field><Field label="Amount to apply now" required><input className={inputClass} type="number" min="0.01" step="0.01" max={payment?.unallocated_amount} value={amount} onChange={(event) => setAmount(event.target.value)} /></Field>{selectedInvoice && remainingAfterAllocation !== null ? <p className="border border-primary/20 bg-primary/5 p-3 text-sm">Invoice balance after this payment: <strong>{formatMoney(remainingAfterAllocation, selectedInvoice.currency)}</strong></p> : null}<Button loading={mutation.isPending} loadingLabel="Allocating" disabled={!invoice || !amount || (selectedInvoice !== undefined && Number(amount) > Number(selectedInvoice.balance))}>Save payment allocation</Button></form></FormModal>;
}

function ReasonModal({ state, pending, onClose, onConfirm }: { state: PaymentReason; pending: boolean; onClose: () => void; onConfirm: (reason: string) => void }) { const [text, setText] = useState(''); return <FormModal open={!!state} title={`${state?.action || 'Review'} payment`} onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onConfirm(text); }}><Field label="Reason" required><textarea className={inputClass} rows={4} value={text} onChange={(event) => setText(event.target.value)} /></Field><Button loading={pending} loadingLabel="Applying action" variant={state?.action === 'reject' ? 'warning' : 'default'} disabled={!text}>Confirm</Button></form></FormModal>; }
