import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Download, Link2, Plus, SearchX } from 'lucide-react';
import { FormEvent, useMemo, useState } from 'react';
import { financeApi } from '@/modules/finance/api';
import type { BankStatementLine } from '@/modules/finance/types';
import { qk } from '@/api/queryKeys';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatDate, formatMoney } from '@/lib/utils';
import { FinancePage, Status } from './components';

export function FinanceReconciliationPage() {
  const { role } = useAuth();
  const canPrepare = ['finance_officer', 'finance_manager', 'admin'].includes(role || '');
  const canConfirm = ['finance_manager', 'admin'].includes(role || '');
  const [status, setStatus] = useState('UNRECONCILED');
  const [newLine, setNewLine] = useState(false);
  const [importing, setImporting] = useState(false);
  const [matchLine, setMatchLine] = useState<BankStatementLine | null>(null);
  const toast = useToast();
  const client = useQueryClient();
  const lines = useQuery({ queryKey: qk.financeStatementLines({ status }), queryFn: () => financeApi.statementLines({ page_size: 100, status, ordering: '-statement_date' }) });
  const refresh = () => client.invalidateQueries({ queryKey: ['finance', 'statement-lines'] });
  const action = useMutation({
    mutationFn: ({ id, name, body }: { id: number; name: 'match' | 'unmatch' | 'ignore'; body?: unknown }) => financeApi.statementLineCommand(id, name, body),
    onSuccess: async (_, variables) => { toast.push({ title: `Statement line ${variables.name === 'match' ? 'matched' : variables.name + 'd'}`, tone: 'success' }); await refresh(); setMatchLine(null); },
    onError: (error: Error) => toast.push({ title: 'Reconciliation action failed', message: error.message, tone: 'danger' }),
  });
  const totals = useMemo(() => (lines.data?.results || []).reduce((result, line) => ({ count: result.count + 1, debits: result.debits + (Number(line.amount) < 0 ? Math.abs(Number(line.amount)) : 0), credits: result.credits + (Number(line.amount) > 0 ? Number(line.amount) : 0) }), { count: 0, debits: 0, credits: 0 }), [lines.data]);
  return <FinancePage eyebrow="Cash control" title="Bank & cash reconciliation" description="Record statement evidence, then independently match posted payments before treating them as cleared." actions={canPrepare ? <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => void financeApi.downloadStatementLines('pdf', { status })}><Download className="h-4 w-4" />PDF</Button><Button variant="secondary" onClick={() => void financeApi.downloadStatementLines('xlsx', { status })}><Download className="h-4 w-4" />Excel</Button><Button variant="secondary" onClick={() => setImporting(true)}>Import CSV</Button><Button onClick={() => setNewLine(true)}><Plus className="h-4 w-4" />Add statement line</Button></div> : undefined}>
    <div className="grid gap-3 sm:grid-cols-3"><Kpi label="Visible lines" value={String(totals.count)} /><Kpi label="Statement debits" value={formatMoney(totals.debits, 'UGX')} /><Kpi label="Statement credits" value={formatMoney(totals.credits, 'UGX')} /></div>
    <div className="flex flex-wrap gap-2 border border-border bg-white p-2.5 shadow-panel"><select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value)}><option value="UNRECONCILED">Needs review</option><option value="MATCHED">Matched</option><option value="IGNORED">Ignored</option></select><p className="self-center text-xs text-muted">A posted payment is not proof of bank clearance. Only a matched statement line provides that confirmation.</p></div>
    <div className="grid gap-2">{lines.isLoading ? <Card><CardContent className="p-4 text-sm text-muted">Loading statement lines…</CardContent></Card> : null}{!lines.isLoading && !lines.data?.results.length ? <Card><CardContent className="p-4 text-sm text-muted">No {status.toLowerCase()} statement lines. Add a manual line or import statement data through the API.</CardContent></Card> : null}{lines.data?.results.map((line) => <Card key={line.id}><CardContent className="grid gap-2 p-3 sm:grid-cols-[1fr_auto] sm:items-center"><div><div className="flex flex-wrap items-center gap-2"><strong>{line.reference}</strong><Status value={line.status} /></div><p className="mt-1 text-sm">{line.description || 'No description provided'}</p><p className="mt-1 text-xs text-muted">{line.cash_account_name} · {formatDate(line.statement_date)} · prepared by {line.imported_by_name}</p>{line.payment_number ? <p className="mt-1 text-xs text-primary">Matched to {line.payment_number}{line.payment_reference ? ` / ${line.payment_reference}` : ''}</p> : null}{line.match_notes ? <p className="mt-1 text-xs text-muted">{line.match_notes}</p> : null}</div><div className="flex flex-wrap items-center gap-2 sm:justify-end"><strong className={Number(line.amount) < 0 ? 'text-critical' : 'text-success'}>{formatMoney(line.amount, line.currency_code)}</strong>{canConfirm && line.status === 'UNRECONCILED' ? <><Button size="sm" onClick={() => setMatchLine(line)}><Link2 className="h-3.5 w-3.5" />Match payment</Button><Button size="sm" variant="ghost" onClick={() => action.mutate({ id: line.id, name: 'ignore', body: { match_notes: 'Non-payment bank movement; excluded from payment reconciliation.' } })}><SearchX className="h-3.5 w-3.5" />Ignore</Button></> : null}{canConfirm && line.status === 'MATCHED' ? <Button size="sm" variant="ghost" onClick={() => action.mutate({ id: line.id, name: 'unmatch', body: { match_notes: 'Returned to reconciliation queue for correction.' } })}>Unmatch</Button> : null}</div></CardContent></Card>)}</div>
    <StatementLineModal open={newLine} onClose={() => setNewLine(false)} />
    <ImportStatementModal open={importing} onClose={() => setImporting(false)} onSuccess={refresh} />
    <MatchModal line={matchLine} onClose={() => setMatchLine(null)} onMatch={(payment, match_notes) => matchLine && action.mutate({ id: matchLine.id, name: 'match', body: { payment, match_notes } })} pending={action.isPending} />
  </FinancePage>;
}

function ImportStatementModal({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess: () => Promise<unknown> }) {
  const accounts = useQuery({ queryKey: ['finance', 'cash-accounts', 'import'], queryFn: () => financeApi.cashAccounts({ page_size: 100, is_active: true }) });
  const toast = useToast(); const [cashAccount, setCashAccount] = useState(''); const [file, setFile] = useState<File | null>(null);
  const importFile = useMutation({ mutationFn: () => financeApi.importStatementCsv(Number(cashAccount), file!), onSuccess: async (result) => { toast.push({ title: `${result.created} statement line${result.created === 1 ? '' : 's'} imported`, message: result.skipped_duplicates ? `${result.skipped_duplicates} duplicate${result.skipped_duplicates === 1 ? '' : 's'} skipped.` : undefined, tone: result.errors.length ? 'warning' : 'success' }); await onSuccess(); setCashAccount(''); setFile(null); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not import statement', message: error.message, tone: 'danger' }) });
  return <FormModal open={open} title="Import bank statement CSV" onClose={onClose}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); importFile.mutate(); }}><Field label="Cash / bank account" required><select className={inputClass} required value={cashAccount} onChange={(event) => setCashAccount(event.target.value)}><option value="">Select account</option>{accounts.data?.results.map((account) => <option key={account.id} value={account.id}>{account.code} / {account.name}</option>)}</select></Field><Field label="CSV file" required><input className={inputClass} required type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} /><p className="mt-1 text-xs text-muted">Required columns: statement_date, reference, amount. Optional: description.</p></Field><Button loading={importFile.isPending} disabled={!cashAccount || !file}>Import for review</Button></form></FormModal>;
}

function Kpi({ label, value }: { label: string; value: string }) { return <Card><CardContent className="p-3"><p className="text-[10px] font-bold uppercase tracking-wide text-muted">{label}</p><strong className="mt-1 block text-lg">{value}</strong></CardContent></Card>; }

function StatementLineModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const accounts = useQuery({ queryKey: ['finance', 'cash-accounts'], queryFn: () => financeApi.cashAccounts({ page_size: 100, is_active: true }) });
  const toast = useToast(); const client = useQueryClient();
  const [form, setForm] = useState({ cash_account: '', statement_date: new Date().toISOString().slice(0, 10), reference: '', description: '', amount: '' });
  const create = useMutation({ mutationFn: () => financeApi.createStatementLine({ ...form, cash_account: Number(form.cash_account), amount: form.amount }), onSuccess: async () => { toast.push({ title: 'Statement line added for reconciliation', tone: 'success' }); await client.invalidateQueries({ queryKey: ['finance', 'statement-lines'] }); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not add statement line', message: error.message, tone: 'danger' }) });
  return <FormModal open={open} title="Add bank or cash statement line" onClose={onClose}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); create.mutate(); }}><Field label="Cash / bank account" required><select className={inputClass} value={form.cash_account} onChange={(e) => setForm({ ...form, cash_account: e.target.value })}><option value="">Select account</option>{accounts.data?.results.map((account) => <option key={account.id} value={account.id}>{account.code} / {account.name}</option>)}</select></Field><div className="grid gap-3 sm:grid-cols-2"><Field label="Statement date" required><input className={inputClass} type="date" value={form.statement_date} onChange={(e) => setForm({ ...form, statement_date: e.target.value })} /></Field><Field label="Statement reference" required><input className={inputClass} value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} /></Field><Field label="Amount" required><input className={inputClass} type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field></div><p className="-mt-2 text-xs text-muted">Use a negative amount for money paid out; positive for money received.</p><Field label="Description"><input className={inputClass} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field><Button loading={create.isPending} disabled={!form.cash_account || !form.reference || !form.amount}>Add for review</Button></form></FormModal>;
}

function MatchModal({ line, onClose, onMatch, pending }: { line: BankStatementLine | null; onClose: () => void; onMatch: (payment: number, notes: string) => void; pending: boolean }) {
  const payments = useQuery({ queryKey: ['finance', 'payments', 'posted'], queryFn: () => financeApi.payments({ page_size: 100, status: 'POSTED' }), enabled: !!line });
  const [payment, setPayment] = useState(''); const [notes, setNotes] = useState('');
  const candidates = (payments.data?.results || []).filter((item) => item.source_account === line?.cash_account_ledger && Number(item.amount) === Math.abs(Number(line?.amount)));
  return <FormModal open={!!line} title={`Match ${line?.reference || 'statement line'}`} onClose={onClose}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); onMatch(Number(payment), notes); }}><p className="text-sm text-muted">Only posted payments with the same cash account and exact debit amount are offered. This prevents accidental reconciliation.</p><Field label="Posted payment" required><select className={inputClass} value={payment} onChange={(e) => setPayment(e.target.value)}><option value="">Select matching payment</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.number} / {item.supplier_name} / {formatMoney(item.amount, item.currency_code)}</option>)}</select></Field>{!candidates.length ? <p className="text-sm text-warning">No eligible payment matches this statement amount and account.</p> : null}<Field label="Reconciliation note"><input className={inputClass} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field><Button loading={pending} disabled={!payment}><Check className="h-4 w-4" />Confirm match</Button></form></FormModal>;
}
