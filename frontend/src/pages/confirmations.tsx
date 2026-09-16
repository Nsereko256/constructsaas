import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ClipboardCheck, Clock3, ExternalLink, FileCheck2, History, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import type { WorkflowConfirmation } from '@/api/types';
import { useAuth } from '@/auth/auth-context';
import { Pagination } from '@/components/common/pagination';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatDate } from '@/lib/utils';

const filters = [
  ['Pending', 'PENDING'],
  ['Confirmed', 'CONFIRMED'],
  ['Returned', 'RETURNED'],
  ['All history', ''],
] as const;

export function ConfirmationsPage() {
  const { role, user } = useAuth();
  const [status, setStatus] = useState('PENDING');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<WorkflowConfirmation | null>(null);
  const [decision, setDecision] = useState<'approve' | 'return'>('approve');
  const [comments, setComments] = useState('Reviewed against the submitted source records.');
  const [overrideReason, setOverrideReason] = useState('');
  const params = { page, page_size: 10, ...(status ? { status } : {}) };
  const query = useQuery({ queryKey: qk.workflowConfirmations(params), queryFn: () => api.workflowConfirmations(params) });
  const queryClient = useQueryClient();
  const toast = useToast();
  const approve = useMutation({
    mutationFn: (task: WorkflowConfirmation) => api.approveOpeningStockImport(task.id, comments, overrideReason),
    onSuccess: (result) => {
      toast.push({ title: 'Opening stock confirmed and posted', message: `${result.opening_balances} opening balances were posted.`, tone: 'success' });
      setSelected(null);
      void queryClient.invalidateQueries({ queryKey: ['workflow-confirmations'] });
      void queryClient.invalidateQueries({ queryKey: ['materials'] });
      void queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    },
    onError: (error: Error) => toast.push({ title: 'Confirmation failed', message: error.message, tone: 'danger' }),
  });
  const returnTask = useMutation({
    mutationFn: (task: WorkflowConfirmation) => api.returnWorkflowConfirmation(task.id, comments, overrideReason),
    onSuccess: () => {
      toast.push({ title: 'Returned for correction', message: 'The preparer can correct and resubmit a new version.', tone: 'success' });
      setSelected(null);
      void queryClient.invalidateQueries({ queryKey: ['workflow-confirmations'] });
    },
    onError: (error: Error) => toast.push({ title: 'Return failed', message: error.message, tone: 'danger' }),
  });
  const tasks = query.data?.results || [];
  const pendingMine = tasks.filter((task) => task.status === 'PENDING' && task.is_my_action).length;

  return <div className="operations-reference grid gap-3">
    <header className="ops-page-head">
      <div className="ops-page-titlebar"><div><p className="text-[11px] font-black uppercase tracking-[0.14em] text-primary">Controlled handoffs</p><h1>Confirmation queue</h1><p>Review records prepared by another responsible person before they move to the next stage.</p></div></div>
    </header>

    <section className="grid gap-3 sm:grid-cols-3">
      <Summary icon={ClipboardCheck} label="My pending actions" value={pendingMine} detail="Assigned to your role" />
      <Summary icon={ShieldCheck} label="Control" value="Maker–checker" detail="The preparer cannot self-confirm" />
      <Summary icon={History} label="Audit evidence" value="Immutable" detail="Snapshot, decision and actor retained" />
    </section>

    <section className="ops-register overflow-hidden">
      <div className="ops-register-head"><div><h2>Responsibility register</h2><p className="text-xs text-muted">Act only on tasks marked as yours; other entries remain visible for tracking.</p></div></div>
      <div className="ops-register-tabs">{filters.map(([label, value]) => <button key={label} className={status === value ? 'active' : ''} onClick={() => { setStatus(value); setPage(1); }}>{label}</button>)}</div>
      <div className="divide-y divide-border">
        {tasks.map((task) => <article key={task.id} className="grid gap-3 p-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(220px,.75fr)_auto] lg:items-center">
          <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong className="truncate text-sm">{task.object_label}</strong><Badge tone={statusTone(task.status)}>{task.status_display}</Badge><Badge tone="info">{task.stage_display}</Badge>{task.version > 1 ? <Badge>Version {task.version}</Badge> : null}</div><p className="mt-1 text-xs text-muted">{task.document_type_display} · submitted {formatDate(task.submitted_at)}</p>{task.return_reason ? <p className="mt-2 rounded-md bg-critical/5 px-2 py-1.5 text-xs font-semibold text-critical">Returned: {task.return_reason}</p> : null}</div>
          <div className="grid gap-1 text-xs"><span className="text-muted">Prepared by <strong className="text-foreground">{task.submitted_by_name}</strong></span><span className="text-muted">Responsible <strong className="text-foreground">{task.assigned_to_name || task.required_role_display}</strong></span>{task.confirmed_by_name ? <span className="text-muted">Decided by <strong className="text-foreground">{task.confirmed_by_name}</strong></span> : null}</div>
          <div className="flex flex-wrap gap-2 lg:justify-end">{task.action_url ? <Button asChild size="sm" variant="secondary"><Link to={task.action_url}>Open record <ExternalLink className="h-3.5 w-3.5" /></Link></Button> : null}{task.status === 'PENDING' && task.is_my_action && task.document_type === 'OPENING_STOCK' ? <><Button size="sm" variant="secondary" onClick={() => { setDecision('return'); setComments(''); setSelected(task); }}>Return</Button><Button size="sm" onClick={() => { setDecision('approve'); setComments('Reviewed against the submitted source records.'); setSelected(task); }}><CheckCircle2 className="h-4 w-4" />Confirm & post</Button></> : null}</div>
        </article>)}
        {!query.isLoading && !tasks.length ? <div className="grid place-items-center gap-2 p-10 text-center"><FileCheck2 className="h-8 w-8 text-primary" /><strong>No confirmations in this view</strong><p className="text-sm text-muted">New handoffs will appear here when a responsible party submits a record.</p></div> : null}
      </div>
      <Pagination page={page} setPage={setPage} data={query.data} />
    </section>

    <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}><DialogContent title={decision === 'approve' ? 'Confirm opening stock' : 'Return opening stock'} description={decision === 'approve' ? 'Compare the immutable snapshot with the signed onboarding count before posting.' : 'Explain exactly what the preparer must correct before resubmitting.'} variant="form">
      {selected ? <div className="grid gap-4"><div className="rounded-md border border-border bg-surface p-3 text-sm"><strong>{selected.object_label}</strong><p className="mt-1 text-xs text-muted">Prepared by {selected.submitted_by_name} · {String((selected.submitted_snapshot.rows as unknown[] | undefined)?.length || 0)} rows · opening date {String(selected.submitted_snapshot.opening_date || '—')}</p></div><Field label={decision === 'approve' ? 'Confirmation note' : 'Correction required'} required><textarea className={inputClass} rows={3} value={comments} onChange={(event) => setComments(event.target.value)} /></Field>{role === 'admin' && selected.submitted_by === user?.id ? <div><Field label="Admin override reason" required><textarea className={inputClass} rows={2} value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} /></Field><p className="mt-1 text-xs text-muted">Required because you prepared this submission.</p></div> : null}<div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => setSelected(null)}>Cancel</Button><Button disabled={approve.isPending || returnTask.isPending || comments.trim().length < 5 || (selected.submitted_by === user?.id && overrideReason.trim().length < 10)} onClick={() => decision === 'approve' ? approve.mutate(selected) : returnTask.mutate(selected)}>{decision === 'approve' ? (approve.isPending ? 'Posting…' : 'Confirm and post stock') : (returnTask.isPending ? 'Returning…' : 'Return for correction')}</Button></div></div> : null}
    </DialogContent></Dialog>
  </div>;
}

function Summary({ icon: Icon, label, value, detail }: { icon: typeof Clock3; label: string; value: string | number; detail: string }) {
  return <div className="flex items-center gap-3 rounded-lg border border-border bg-white p-4 shadow-panel"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Icon className="h-5 w-5" /></div><div><p className="text-xs font-semibold text-muted">{label}</p><strong className="block text-lg">{value}</strong><small className="text-muted">{detail}</small></div></div>;
}
