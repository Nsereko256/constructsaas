import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRightLeft, Check, Plus, Send, SlidersHorizontal, X } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { financeApi } from '@/modules/finance/api';
import type { ProjectBudget } from '@/modules/finance/types';
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
import { formatMoney } from '@/lib/utils';
import { FinancePage, Status } from './components';

type Decision = { budget: ProjectBudget; action: 'approve' | 'reject' } | null;
type Adjustment = { budget: ProjectBudget; mode: 'revise' | 'transfer' } | null;

export function FinanceBudgetsPage() {
  const { role } = useAuth();
  const list = useListState({ status: '', project: '' });
  const [creating, setCreating] = useState(false);
  const [decision, setDecision] = useState<Decision>(null);
  const [adjustment, setAdjustment] = useState<Adjustment>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const budgets = useQuery({ queryKey: qk.financeBudgets(list.query), queryFn: () => financeApi.budgets(list.query) });
  const refresh = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ['finance'] }),
    queryClient.invalidateQueries({ queryKey: qk.workflowBadges }),
  ]);
  const action = useMutation({
    mutationFn: ({ id, command, comments }: { id: number; command: string; comments?: string }) => financeApi.budgetCommand(id, command, comments === undefined ? undefined : { comments }),
    onSuccess: async (_, variables) => { toast.push({ title: `Budget ${variables.command.replace(/e$/, '')}ed`, tone: 'success' }); await refresh(); setDecision(null); },
    onError: (error: Error) => toast.push({ title: 'Budget action failed', message: error.message, tone: 'danger' }),
  });
  const columns: ColumnDef<ProjectBudget>[] = [
    { header: 'Project budget', cell: ({ row }) => <div><strong>{row.original.project_code} / {row.original.name}</strong><p className="text-xs text-muted">{row.original.project_name}</p></div> },
    { header: 'Status', cell: ({ row }) => <Status value={row.original.status} /> },
    { header: 'Original', cell: ({ row }) => formatMoney(row.original.original_budget) },
    { header: 'Revised', cell: ({ row }) => formatMoney(row.original.revised_budget) },
    { header: 'Committed', cell: ({ row }) => formatMoney(row.original.open_commitments) },
    { header: 'Actual', cell: ({ row }) => formatMoney(row.original.actual_expenditure) },
    { header: 'Available', cell: ({ row }) => <strong>{formatMoney(row.original.available_balance)}</strong> },
    { id: 'actions', header: '', cell: ({ row }) => { const pending = action.isPending && action.variables?.id === row.original.id; return <div className="flex justify-end gap-2">{can.prepareFinance(role) && row.original.status === 'DRAFT' ? <Button size="sm" loading={pending && action.variables?.command === 'submit'} loadingLabel="Submitting" disabled={pending} onClick={() => action.mutate({ id: row.original.id, command: 'submit' })}><Send className="h-3.5 w-3.5" />Submit</Button> : null}{can.manageFinance(role) && row.original.status === 'SUBMITTED' ? <><Button size="sm" disabled={pending} onClick={() => setDecision({ budget: row.original, action: 'approve' })}><Check className="h-3.5 w-3.5" />Approve</Button><Button size="sm" variant="secondary" disabled={pending} onClick={() => setDecision({ budget: row.original, action: 'reject' })}><X className="h-3.5 w-3.5" />Reject</Button></> : null}{can.manageFinance(role) && row.original.status === 'APPROVED' ? <><Button size="sm" variant="secondary" onClick={() => setAdjustment({ budget: row.original, mode: 'revise' })}><SlidersHorizontal className="h-3.5 w-3.5" />Adjust</Button><Button size="sm" variant="ghost" onClick={() => setAdjustment({ budget: row.original, mode: 'transfer' })}><ArrowRightLeft className="h-3.5 w-3.5" />Transfer</Button></> : null}</div>; } },
  ];
  return <FinancePage eyebrow="Project controls" title="Budgets and commitments" description="Approve cost envelopes, monitor purchasing commitments, and protect available project balances." actions={can.prepareFinance(role) ? <Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" />New budget</Button> : undefined}>
    <div className="flex flex-wrap gap-2 border border-border bg-white p-3 shadow-panel">
      <input className={inputClass} value={list.search} onChange={(event) => list.setSearch(event.target.value)} placeholder="Search project or budget" aria-label="Search budgets" />
      <select className={inputClass} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}><option value="">All statuses</option><option>DRAFT</option><option>SUBMITTED</option><option>APPROVED</option><option>REJECTED</option></select>
    </div>
    <DataTable columns={columns} data={budgets.data?.results || []} emptyTitle={budgets.isLoading ? 'Loading budgets...' : 'No project budgets found'} />
    <Pagination page={list.page} setPage={list.setPage} data={budgets.data} />
    <BudgetModal key={creating ? 'open' : 'closed'} open={creating} onClose={() => setCreating(false)} canManageCategories={can.manageFinance(role)} />
    <DecisionModal decision={decision} pending={action.isPending && action.variables?.id === decision?.budget.id} onClose={() => setDecision(null)} onConfirm={(comments) => decision && action.mutate({ id: decision.budget.id, command: decision.action, comments })} />
    <BudgetAdjustmentModal key={adjustment ? `${adjustment.budget.id}-${adjustment.mode}` : 'closed'} adjustment={adjustment} onClose={() => setAdjustment(null)} onComplete={refresh} />
  </FinancePage>;
}

function BudgetAdjustmentModal({ adjustment, onClose, onComplete }: { adjustment: Adjustment; onClose: () => void; onComplete: () => Promise<unknown> }) {
  const [lineId, setLineId] = useState('');
  const [fromLineId, setFromLineId] = useState('');
  const [toLineId, setToLineId] = useState('');
  const [amount, setAmount] = useState('');
  const [comments, setComments] = useState('');
  const [override, setOverride] = useState(false);
  const toast = useToast();
  const budget = adjustment?.budget;
  const mode = adjustment?.mode;
  const selectedLine = budget?.lines.find((line) => String(line.id) === lineId);
  const sourceLine = budget?.lines.find((line) => String(line.id) === fromLineId);
  const numericAmount = Number(amount || 0);
  const needsOverride = mode === 'revise'
    ? !!selectedLine && Number(selectedLine.available_balance) + numericAmount < 0
    : !!sourceLine && numericAmount > Number(sourceLine.available_balance);
  const mutation = useMutation({
    mutationFn: () => mode === 'revise'
      ? financeApi.budgetCommand(budget!.id, 'revise', { budget_line: Number(lineId), amount: numericAmount, comments, override })
      : financeApi.budgetCommand(budget!.id, 'transfer', { from_line: Number(fromLineId), to_line: Number(toLineId), amount: numericAmount, comments, override }),
    onSuccess: async () => { toast.push({ title: mode === 'revise' ? 'Budget adjusted' : 'Funds transferred', tone: 'success' }); await onComplete(); onClose(); },
    onError: (error: Error) => toast.push({ title: 'Budget adjustment failed', message: error.message, tone: 'danger' }),
  });
  const valid = !!budget && !!comments.trim() && numericAmount !== 0 && (mode === 'revise' ? !!lineId : !!fromLineId && !!toLineId && fromLineId !== toLineId) && (!needsOverride || override);
  return <FormModal open={!!adjustment} title={mode === 'transfer' ? 'Transfer budget funds' : 'Adjust approved budget'} onClose={onClose}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
      <p className="text-sm text-muted">{mode === 'transfer' ? 'Move available funds between approved budget lines.' : 'Record a positive increase or negative reduction against an approved budget line.'}</p>
      {mode === 'transfer' ? <div className="grid gap-3 md:grid-cols-2"><Field label="From line" required><select className={inputClass} value={fromLineId} onChange={(event) => setFromLineId(event.target.value)}><option value="">Select source line</option>{budget?.lines.map((line) => <option key={line.id} value={line.id}>{line.category_code} / {line.description || line.category_name}</option>)}</select></Field><Field label="To line" required><select className={inputClass} value={toLineId} onChange={(event) => setToLineId(event.target.value)}><option value="">Select destination line</option>{budget?.lines.map((line) => <option key={line.id} value={line.id}>{line.category_code} / {line.description || line.category_name}</option>)}</select></Field></div> : <Field label="Budget line" required><select className={inputClass} value={lineId} onChange={(event) => setLineId(event.target.value)}><option value="">Select budget line</option>{budget?.lines.map((line) => <option key={line.id} value={line.id}>{line.category_code} / {line.description || line.category_name} — available {formatMoney(line.available_balance)}</option>)}</select></Field>}
      <Field label={mode === 'revise' ? 'Adjustment amount' : 'Transfer amount'} required><input className={inputClass} type="number" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder={mode === 'revise' ? 'Use a negative amount to reduce' : 'Amount to transfer'} /></Field>
      {needsOverride ? <label className="flex items-start gap-2 rounded-md border border-warning-border bg-warning/10 p-3 text-sm"><input type="checkbox" checked={override} onChange={(event) => setOverride(event.target.checked)} className="mt-1" /><span><strong>Approve with exception</strong><br />Authorize the budget exception because this adjustment exceeds the available balance.</span></label> : null}
      <Field label="Reason / audit comments" required><textarea className={inputClass} rows={4} value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Explain the approved budget change" /></Field>
      <Button loading={mutation.isPending} loadingLabel="Saving adjustment" disabled={!valid}>{mode === 'transfer' ? 'Transfer funds' : 'Save budget adjustment'}</Button>
    </form>
  </FormModal>;
}

function BudgetModal({ open, onClose, canManageCategories }: { open: boolean; onClose: () => void; canManageCategories: boolean }) {
  const projects = useQuery({ queryKey: qk.projects({ page_size: 100 }), queryFn: () => api.projects({ page_size: 100 }) });
  const categories = useQuery({ queryKey: ['finance', 'budget-categories'], queryFn: () => financeApi.budgetCategories({ page_size: 100, is_active: true }) });
  const [form, setForm] = useState({ project: '', name: '', lines: [{ category: '', description: '', original_amount: '' }] });
  const [creatingCategory, setCreatingCategory] = useState(false);
  const client = useQueryClient();
  const toast = useToast();
  const mutation = useMutation({ mutationFn: () => financeApi.createBudget({ project: Number(form.project), name: form.name, lines: form.lines.map((line) => ({ ...line, category: Number(line.category) })) }), onSuccess: () => { toast.push({ title: 'Budget draft created', tone: 'success' }); void client.invalidateQueries({ queryKey: ['finance'] }); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not create budget', message: error.message, tone: 'danger' }) });
  const setLine = (index: number, key: string, value: string) => setForm((current) => ({ ...current, lines: current.lines.map((line, i) => i === index ? { ...line, [key]: value } : line) }));
  return <FormModal open={open} title="Create project budget" onClose={onClose}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
    <div className="grid gap-3 md:grid-cols-2"><Field label="Project" required><SearchableSelect required value={form.project} onChange={(project) => setForm({ ...form, project })} options={(projects.data?.results || []).map((project) => ({ value: project.id, label: `${project.code} / ${project.name}` }))} placeholder="Search project" /></Field><Field label="Budget name" required><input className={inputClass} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field></div>
    <div className="border border-border"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-background px-3 py-2"><strong className="text-sm">Budget lines</strong><div className="flex gap-2">{canManageCategories ? <Button type="button" size="sm" variant="ghost" onClick={() => setCreatingCategory(true)}><Plus className="h-3.5 w-3.5" />New category</Button> : null}<Button type="button" size="sm" variant="secondary" onClick={() => setForm((current) => ({ ...current, lines: [...current.lines, { category: '', description: '', original_amount: '' }] }))}>Add line</Button></div></div><div className="grid gap-2 p-3">{form.lines.map((line, index) => <div key={index} className="grid gap-2 border-b border-border pb-2 md:grid-cols-[1fr_1fr_160px_auto]"><SearchableSelect required value={line.category} onChange={(category) => setLine(index, 'category', category)} options={(categories.data?.results || []).map((category) => ({ value: category.id, label: `${category.code} / ${category.name}` }))} placeholder="Search budget category" /><input className={inputClass} placeholder="Description" value={line.description} onChange={(event) => setLine(index, 'description', event.target.value)} /><input className={inputClass} type="number" min="0" step="0.01" placeholder="Original amount" value={line.original_amount} onChange={(event) => setLine(index, 'original_amount', event.target.value)} required /><Button type="button" size="sm" variant="ghost" onClick={() => setForm((current) => ({ ...current, lines: current.lines.filter((_, i) => i !== index) }))}>Remove</Button></div>)}</div></div>
    <Button loading={mutation.isPending} loadingLabel="Creating draft" disabled={!form.project || !form.name || !form.lines.length || form.lines.some((line) => !line.category || !line.original_amount)}>Create draft budget</Button>
  </form><QuickCategoryModal open={creatingCategory} onClose={() => setCreatingCategory(false)} onCreated={(categoryId) => { setForm((current) => ({ ...current, lines: current.lines.map((line, index) => index === 0 && !line.category ? { ...line, category: String(categoryId) } : line) })); }} /></FormModal>;
}

function QuickCategoryModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (categoryId: number) => void }) {
  const [form, setForm] = useState({ code: '', name: '', description: '' });
  const client = useQueryClient();
  const toast = useToast();
  const mutation = useMutation({ mutationFn: () => financeApi.createReference<{ id: number }>('budget-categories', { ...form, is_active: true }), onSuccess: async (category) => { await client.invalidateQueries({ queryKey: ['finance', 'budget-categories'] }); toast.push({ title: 'Budget category created', tone: 'success' }); onCreated(category.id); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not create budget category', message: error.message, tone: 'danger' }) });
  return <FormModal open={open} title="Add budget category" onClose={onClose}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}><p className="text-sm text-muted">Use a category to group and track project budget lines. You can link it to a cost centre later in Finance setup.</p><div className="grid gap-3 md:grid-cols-2"><Field label="Code" required><input className={inputClass} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })} /></Field><Field label="Name" required><input className={inputClass} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field></div><Field label="Description"><textarea className={inputClass} rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></Field><Button loading={mutation.isPending} loadingLabel="Creating category" disabled={!form.code || !form.name}>Create category</Button></form></FormModal>;
}

function DecisionModal({ decision, pending, onClose, onConfirm }: { decision: Decision; pending: boolean; onClose: () => void; onConfirm: (comments: string) => void }) {
  const [comments, setComments] = useState('');
  return <FormModal open={!!decision} title={`${decision?.action === 'approve' ? 'Approve' : 'Reject'} ${decision?.budget.project_code || 'budget'}`} onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); onConfirm(comments); }}><Field label="Review comments" required={decision?.action === 'reject'}><textarea className={inputClass} rows={4} value={comments} onChange={(event) => setComments(event.target.value)} /></Field><Button loading={pending} loadingLabel={decision?.action === 'approve' ? 'Approving' : 'Rejecting'} variant={decision?.action === 'reject' ? 'warning' : 'default'} disabled={decision?.action === 'reject' && !comments}>{decision?.action === 'approve' ? 'Approve budget' : 'Reject budget'}</Button></form></FormModal>;
}
