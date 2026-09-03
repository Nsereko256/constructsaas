import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '@/api/services';
import type { WorkOrderSite } from '@/api/types';
import { FormModal } from '@/components/common/form-modal';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';

export function WorkOrderProgressPage() {
  const [selected, setSelected] = useState<WorkOrderSite | null>(null);
  const [status, setStatus] = useState('');
  const sites = useQuery({ queryKey: ['work-order-sites', status], queryFn: () => api.workOrderSites(status ? { status } : {}) });
  return <div className="grid gap-4">
    <PageToolbar title="Site work progress" subtitle="Update physical-site progress, record blockers, and see which work packages are falling behind.">
      <select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="ASSIGNED">Assigned</option><option value="IN_PROGRESS">In progress</option><option value="ON_HOLD">On hold</option></select>
      <Button variant="secondary" onClick={() => api.downloadWorkOrderProgress('xlsx', status ? { status } : {})}>Excel</Button><Button variant="secondary" onClick={() => api.downloadWorkOrderProgress('pdf', status ? { status } : {})}>PDF</Button>
    </PageToolbar>
    {sites.isError ? <Card><CardContent className="p-4 text-sm text-critical">Site progress could not be loaded. Refresh the page or try again.</CardContent></Card> : null}
    <div className="grid gap-3">{(sites.data?.results || []).map((site) => <Card key={site.id}><CardContent className="grid gap-3 p-3 sm:grid-cols-[1fr_auto] sm:p-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong>{site.project_name} · {site.project_site_name}</strong><Badge tone={statusTone(site.status)}>{site.status_display}</Badge></div><p className="mt-1 text-sm">{site.title || 'Work package'} · {site.progress_percent}% reported · {site.task_progress_percent}% tasks</p><div className="mt-2 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${site.progress_percent}%` }} /></div><div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4"><Metric label="Forecast" value={site.forecast_cost} /><Metric label="Committed" value={site.committed_cost} /><Metric label="Remaining" value={site.remaining_estimated_budget} /><Metric label="Close-out" value={`${site.closeout_completion_percent}%`} /></div><p className="mt-2 text-xs text-muted">{site.progress_notes || 'No progress note yet.'}</p></div><Button size="sm" variant="secondary" onClick={() => setSelected(site)}>Update progress</Button></CardContent></Card>)}{!sites.isLoading && !(sites.data?.results || []).length ? <Card><CardContent className="p-6 text-center text-sm text-muted">No site work packages match this view.</CardContent></Card> : null}</div>
    {selected ? <ProgressModal site={selected} onClose={() => setSelected(null)} /> : null}
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-border bg-background p-2"><span className="block text-[10px] font-bold uppercase tracking-wide text-muted">{label}</span><strong className="mt-0.5 block truncate">{value}</strong></div>; }

function ProgressModal({ site, onClose }: { site: WorkOrderSite; onClose: () => void }) {
  const toast = useToast(); const queryClient = useQueryClient(); const [percent, setPercent] = useState(String(site.progress_percent)); const [notes, setNotes] = useState(site.progress_notes);
  const save = useMutation({ mutationFn: () => api.updateWorkOrderSiteProgress(site.id, { progress_percent: Number(percent), progress_notes: notes }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['work-order-sites'] }); toast.push({ title: 'Site progress updated', tone: 'success' }); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not update progress', message: error.message, tone: 'danger' }) });
  return <FormModal open title={`Progress · ${site.project_site_name}`} onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}><p className="rounded-lg border border-info/20 bg-info/5 p-3 text-xs text-muted">Tasks currently average {site.task_progress_percent}%. Use the reported site percentage for physical completion and explain any difference.</p><Field label="Completion percentage" required><input className={inputClass} required type="number" min="0" max="100" value={percent} onChange={(event) => setPercent(event.target.value)} /></Field><Field label="Progress update" required><textarea className={inputClass} required value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Completed work, blockers, materials needed, and next step." /></Field><Button disabled={save.isPending}>Save progress update</Button></form></FormModal>;
}
