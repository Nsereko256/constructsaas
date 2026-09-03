import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pencil, PackageCheck } from 'lucide-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '@/modules/procurement/api';
import type { SupplierClaim } from '@/modules/procurement/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { ExportButton } from '@/components/common/export-button';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatDate } from '@/lib/utils';

const statuses = ['OPEN', 'AWAITING_SUPPLIER', 'RETURN_PENDING', 'REPLACEMENT_PENDING', 'REPLACEMENT_RECEIVED', 'CREDIT_PENDING', 'RESOLVED', 'CANCELLED'];

export function SupplierClaimsPage() {
  const { role } = useAuth();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('');
  const [editing, setEditing] = useState<SupplierClaim | null>(null);
  const actionQueue = searchParams.get('action_queue') || '';
  const claimParams = { status, action_queue: actionQueue };
  const claims = useQuery({ queryKey: actionQueue ? qk.supplierClaimActionQueue(claimParams) : qk.supplierClaims(claimParams), queryFn: () => api.supplierClaims({ ...(status ? { status } : {}), ...(actionQueue ? { action_queue: actionQueue } : {}) }) });
  return <div className="grid gap-3 sm:gap-4">
    <PageToolbar title="Supplier claims" subtitle="Track rejected or damaged delivery lines through replacement, return, credit, or closure.">
      <select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All claim statuses</option>{statuses.map((item) => <option key={item} value={item}>{item.split('_').join(' ')}</option>)}</select>
      <ExportButton label="PDF" onClick={() => void api.downloadSupplierClaims('pdf', { ...(status ? { status } : {}), ...(actionQueue ? { action_queue: actionQueue } : {}) })} />
      <ExportButton label="Excel" onClick={() => void api.downloadSupplierClaims('xlsx', { ...(status ? { status } : {}), ...(actionQueue ? { action_queue: actionQueue } : {}) })} />
    </PageToolbar>
    <div className="grid gap-2 sm:gap-3">
      {(claims.data?.results || []).map((claim) => <Card key={claim.id}><CardContent className="grid gap-2.5 p-3 sm:grid-cols-[1fr_auto] sm:p-4">
        <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><strong>{claim.material_name}</strong><Badge tone={statusTone(claim.status)}>{claim.status_display}</Badge></div>
          <p className="mt-1 text-sm text-muted">{claim.purchase_order_number} · {claim.grn_number} · {claim.supplier_name || 'Supplier not set'}</p>
          <p className="mt-1 text-sm">{claim.notes}</p>
          <p className="mt-1 text-xs text-muted">Due {claim.due_date ? formatDate(claim.due_date) : 'not set'} · Reported by {claim.reported_by_name || 'Unknown'}{claim.assigned_to_name ? ` · Assigned to ${claim.assigned_to_name}` : ''}</p>
          {claim.resolution_notes ? <p className="mt-2 border-l-2 border-success pl-2 text-sm">{claim.resolution_notes}</p> : null}
        </div>
        <div className="flex flex-wrap gap-2">{claim.status === 'REPLACEMENT_PENDING' && can.receivePo(role) ? <Button asChild size="sm"><Link to={`/procurement/deliveries?replacement_claim=${claim.id}`}><PackageCheck className="h-4 w-4" />Receive replacement</Link></Button> : null}{can.createPo(role) ? <Button size="sm" variant="secondary" onClick={() => setEditing(claim)}><Pencil className="h-4 w-4" />Manage</Button> : null}</div>
      </CardContent></Card>)}
      {!claims.isLoading && !(claims.data?.results || []).length ? <Card><CardContent className="p-6 text-center text-sm text-muted">No supplier claims need attention.</CardContent></Card> : null}
    </div>
    <ClaimModal key={editing?.id || 'empty'} claim={editing} onClose={() => setEditing(null)} />
  </div>;
}

function ClaimModal({ claim, onClose }: { claim: SupplierClaim | null; onClose: () => void }) {
  const [form, setForm] = useState({ status: claim?.status || 'OPEN', due_date: claim?.due_date || '', supplier_reference: claim?.supplier_reference || '', resolution_notes: claim?.resolution_notes || '' });
  const queryClient = useQueryClient(); const toast = useToast();
  const mutation = useMutation({ mutationFn: () => api.updateSupplierClaim(claim!.id, form), onSuccess: () => { toast.push({ title: 'Supplier claim updated', tone: 'success' }); void queryClient.invalidateQueries({ queryKey: ['supplier-claims'] }); onClose(); }, onError: (error: Error) => toast.push({ title: 'Could not update claim', message: error.message, tone: 'danger' }) });
  return <FormModal open={!!claim} title={`Manage supplier claim #${claim?.id || ''}`} onClose={onClose}><form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
    <Field label="Commercial status"><select className={inputClass} value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>{statuses.map((item) => <option key={item} value={item}>{item.split('_').join(' ')}</option>)}</select></Field>
    <Field label="Supplier reference"><input className={inputClass} value={form.supplier_reference} onChange={(event) => setForm({ ...form, supplier_reference: event.target.value })} /></Field>
    <Field label="Resolution due date"><input className={inputClass} type="date" value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></Field>
    <Field label="Resolution notes" required={form.status === 'RESOLVED'}><textarea className={inputClass} value={form.resolution_notes} onChange={(event) => setForm({ ...form, resolution_notes: event.target.value })} /></Field>
    <Button disabled={mutation.isPending || (form.status === 'RESOLVED' && !form.resolution_notes.trim())}><Check className="h-4 w-4" />Save claim</Button>
  </form></FormModal>;
}
