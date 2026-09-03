import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Send, Undo2, Wrench } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { api } from '@/api/services';
import type { SiteTransfer, StockMovement } from '@/api/types';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { MaterialLookup } from '@/components/common/material-lookup';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatDate, formatNumber } from '@/lib/utils';

type Mode = 'dispatch' | 'consume' | 'return' | null;
export function SiteCustodyPage() {
  const { role } = useAuth(); const toast = useToast(); const client = useQueryClient(); const [mode, setMode] = useState<Mode>(null);
  const transfers = useQuery({ queryKey: ['site-transfers'], queryFn: api.siteTransfers });
  const refresh = () => { void client.invalidateQueries({ queryKey: ['site-transfers'] }); void client.invalidateQueries({ queryKey: ['stock-movements'] }); void client.invalidateQueries({ queryKey: ['materials'] }); };
  const acknowledge = useMutation({ mutationFn: api.acknowledgeSiteTransfer, onSuccess: () => { toast.push({ title: 'Transfer acknowledged into site custody', tone: 'success' }); refresh(); }, onError: (e: Error) => toast.push({ title: 'Acknowledgement failed', message: e.message, tone: 'danger' }) });
  const canDispatch = ['storekeeper', 'admin'].includes(role || '');
  const canUseSite = ['site_engineer', 'project_manager', 'admin'].includes(role || '');
  const columns: ColumnDef<SiteTransfer>[] = [
    { header: 'Project / material', cell: ({ row }) => <div><strong>{row.original.project_name}</strong><p className="text-xs text-muted">{row.original.material_name}</p></div> },
    { header: 'Route', cell: ({ row }) => <span className="text-sm">{row.original.source_warehouse_name} → {row.original.destination_store_name}</span> },
    { header: 'Quantity', cell: ({ row }) => formatNumber(row.original.quantity) },
    { header: 'Status', cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status}</Badge> },
    { header: 'Dispatched', cell: ({ row }) => formatDate(row.original.dispatched_at) },
    { id: 'action', header: '', cell: ({ row }) => row.original.status === 'DISPATCHED' && canUseSite ? <Button size="sm" onClick={() => acknowledge.mutate(row.original.id)}><Check className="h-4 w-4" />Acknowledge</Button> : null },
  ];
  return <div className="grid gap-4"><PageToolbar title="Site custody" subtitle="Track material custody from warehouse dispatch to site acknowledgement, use, and return.">
    {canDispatch ? <Button onClick={() => setMode('dispatch')}><Send className="h-4 w-4" />Dispatch to site</Button> : null}
    {canUseSite ? <Button variant="secondary" onClick={() => setMode('consume')}><Wrench className="h-4 w-4" />Record consumption</Button> : null}
    {canDispatch ? <Button variant="secondary" onClick={() => setMode('return')}><Undo2 className="h-4 w-4" />Return to warehouse</Button> : null}
  </PageToolbar><DataTable columns={columns} data={transfers.data || []} emptyTitle={transfers.isLoading ? 'Loading transfers...' : 'No site transfers recorded'} />
  <SiteCustodyModal mode={mode} onClose={() => setMode(null)} onDone={refresh} /></div>;
}

function SiteCustodyModal({ mode, onClose, onDone }: { mode: Mode; onClose: () => void; onDone: () => void }) {
  const toast = useToast(); const projects = useQuery({ queryKey: ['projects', 'site-custody'], queryFn: () => api.projects({ page_size: 100, is_active: true }) }); const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: () => api.warehouses({ page_size: 100, is_active: true }) });
  const [material, setMaterial] = useState({ id: '', label: '' }); const [form, setForm] = useState({ project: '', warehouse: '', quantity: '', date: new Date().toISOString().slice(0, 10), reason: '' }); const set = (key: keyof typeof form, value: string) => setForm((v) => ({ ...v, [key]: value }));
  const mutation = useMutation<SiteTransfer | StockMovement>({ mutationFn: () => { const body = { material: Number(material.id), project: Number(form.project), warehouse: form.warehouse ? Number(form.warehouse) : undefined, quantity: form.quantity, date: form.date, reason: form.reason }; if (mode === 'dispatch') return api.dispatchToSite(body); if (mode === 'consume') return api.consumeSiteStock(body); return api.returnSiteStock(body); }, onSuccess: () => { toast.push({ title: mode === 'dispatch' ? 'Transfer dispatched for acknowledgement' : mode === 'consume' ? 'Site consumption recorded' : 'Stock returned to warehouse', tone: 'success' }); onDone(); onClose(); }, onError: (e: Error) => toast.push({ title: 'Site custody action failed', message: e.message, tone: 'danger' }) });
  const title = mode === 'dispatch' ? 'Dispatch to site' : mode === 'consume' ? 'Record site consumption' : 'Return unused site stock';
  return <FormModal open={!!mode} title={title} onClose={onClose}><form className="grid gap-3 md:grid-cols-2" onSubmit={(e: FormEvent) => { e.preventDefault(); mutation.mutate(); }}><Field label="Project" required><select className={inputClass} value={form.project} onChange={(e) => set('project', e.target.value)}><option value="">Select project</option>{(projects.data?.results || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field><Field label="Material" required><MaterialLookup label={material.label} materialId={material.id} required onChange={(id, label) => setMaterial({ id, label })} /></Field>{mode !== 'consume' ? <Field label={mode === 'dispatch' ? 'Source warehouse' : 'Return warehouse'} required><select className={inputClass} value={form.warehouse} onChange={(e) => set('warehouse', e.target.value)}><option value="">Select warehouse</option>{(warehouses.data?.results || []).filter((w) => !w.project).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field> : null}<Field label="Quantity" required><input className={inputClass} type="number" min="0.01" step="0.01" value={form.quantity} onChange={(e) => set('quantity', e.target.value)} /></Field><Field label="Date"><input className={inputClass} type="date" value={form.date} onChange={(e) => set('date', e.target.value)} /></Field><Field label={mode === 'consume' ? 'Work area / purpose' : 'Reason'} required className="md:col-span-2"><textarea className={inputClass} value={form.reason} onChange={(e) => set('reason', e.target.value)} /></Field><Button className="md:col-span-2" disabled={!material.id || !form.project || !form.quantity || !form.reason || (mode !== 'consume' && !form.warehouse) || mutation.isPending}>{title}</Button></form></FormModal>;
}
