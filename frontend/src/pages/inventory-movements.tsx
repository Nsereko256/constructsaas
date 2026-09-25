import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Plus } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { api } from '@/api/services';
import type { StockMovement } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { MaterialLookup } from '@/components/common/material-lookup';
import { PageToolbar } from '@/components/common/page-toolbar';
import { InventoryTabs } from '@/components/common/inventory-tabs';
import { RegisterFilters } from '@/components/common/register-filters';
import './operations-reference.css';
import './inventory-registers.css';
import { Pagination } from '@/components/common/pagination';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';

export function InventoryMovementsPage() {
  const { role } = useAuth();
  const canSeeMaterialCosts = role !== 'site_engineer';
  const list = useListState({ movement_type: '', project: '', material: '', date_from: '', date_to: '' });
  const [open, setOpen] = useState(false);
  const movements = useQuery({ queryKey: qk.movements(list.query), queryFn: () => api.movements(list.query) });
  const allowed = can.createMovement(role);
  const toast = useToast();
  const download = async (kind: 'pdf' | 'xlsx') => {
    try { await (kind === 'pdf' ? api.downloadMovementsPdf(list.filters) : api.downloadMovementsXlsx(list.filters)); toast.push({ title: `Movement ${kind === 'xlsx' ? 'Excel' : 'PDF'} prepared`, tone: 'success' }); }
    catch (error) { toast.push({ title: 'Movement export failed', message: (error as Error).message, tone: 'danger' }); }
  };
  const columns: ColumnDef<StockMovement>[] = [
    { header: 'Date', cell: ({ row }) => formatDate(row.original.date) },
    { header: 'Material', cell: ({ row }) => <strong>{row.original.material_name}</strong> },
    { header: 'Project', cell: ({ row }) => row.original.project_name || 'Warehouse' },
    { header: 'Type', cell: ({ row }) => <Badge tone={statusTone(row.original.movement_type)}>{row.original.movement_type_display}</Badge> },
    { header: 'Qty', cell: ({ row }) => formatNumber(row.original.quantity) },
    ...(canSeeMaterialCosts ? [{ header: 'Unit price', cell: ({ row }: { row: { original: StockMovement } }) => formatUGX(row.original.unit_price) }] : []),
    { header: 'Source', cell: ({ row }) => row.original.source_display },
  ];

  return (
    <div className="operations-reference inventory-register-page grid gap-4">
      <PageToolbar title="Stock movements" subtitle="Track receipts, issues and adjustments across your stores.">
        <Button variant="secondary" onClick={() => void download('pdf')}><Download className="h-4 w-4" />PDF</Button>
        <Button variant="secondary" onClick={() => void download('xlsx')}><Download className="h-4 w-4" />Excel</Button>
        {allowed ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Record stock entry</Button> : null}
      </PageToolbar>
      <InventoryTabs />
      <section className="ops-register">
      <div className="ops-register-head"><h2>Movement history</h2><span className="text-sm text-muted">{movements.data ? `${movements.data.count} records` : 'Stock audit trail'}</span></div>
      <RegisterFilters className="inventory-history-filters" activeCount={[list.search, ...Object.values(list.filters)].filter(Boolean).length} onClear={() => { list.setSearch(''); Object.keys(list.filters).forEach((key) => list.setFilter(key, '')); }}>
        <input aria-label="Search movements" className={inputClass} value={list.search} onChange={event => list.setSearch(event.target.value)} placeholder="Search movements" />
        <Field label="Movement type"><select className={inputClass} value={list.filters.movement_type} onChange={(event) => list.setFilter('movement_type', event.target.value)}>
          <option value="">All movement types</option>
          <option value="IN">Stock in</option>
          <option value="OUT">Stock out</option>
          <option value="ADJUST_IN">Adjustment in</option>
          <option value="ADJUST_OUT">Adjustment out</option>
        </select></Field>
        <Field label="From date"><input className={inputClass} type="date" value={list.filters.date_from} onChange={(event) => list.setFilter('date_from', event.target.value)} /></Field>
        <Field label="To date"><input className={inputClass} type="date" min={list.filters.date_from || undefined} value={list.filters.date_to} onChange={(event) => list.setFilter('date_to', event.target.value)} /></Field>
      </RegisterFilters>
      {movements.isError ? <div className="p-4" role="alert"><p>Could not load movement history.</p><Button variant="secondary" onClick={() => void movements.refetch()}>Retry</Button></div> : <DataTable columns={columns} data={movements.data?.results || []} loading={movements.isLoading} emptyTitle="No movements found" />}
      <Pagination page={list.page} setPage={list.setPage} data={movements.data} />
      </section>
      <MovementModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function MovementModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [material, setMaterial] = useState({ id: '', label: '' });
  const [form, setForm] = useState({ movement_type: 'IN', source: 'INTERNAL', project: '', quantity: '', unit_price: '', date: new Date().toISOString().slice(0, 10), notes: '' });
  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const mutation = useMutation({
    mutationFn: () => api.createMovement({
      ...form,
      material: Number(material.id),
      project: form.project || null,
    } as Partial<StockMovement>),
    onSuccess: () => {
      toast.push({ title: 'Stock movement recorded', tone: 'success' });
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
      void queryClient.invalidateQueries({ queryKey: ['materials'] });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    },
    onError: (error: Error) => toast.push({ title: 'Movement rejected', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title="Record non-purchase stock entry" onClose={onClose}>
      <form className="grid gap-3 md:grid-cols-2" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
        <p className="border border-border bg-background p-3 text-sm md:col-span-2">
          Purchased stock must be received from a finance-approved PO. Project stock exits are issued from a finance-approved request.
        </p>
        <Field label="Search material" required>
          <MaterialLookup
            label={material.label}
            materialId={material.id}
            required
            onChange={(id, label) => setMaterial({ id, label })}
          />
        </Field>
        <Field label="Movement type" required>
          <select className={inputClass} value={form.movement_type} onChange={(event) => set('movement_type', event.target.value)}>
            <option value="IN">Stock in</option>
            <option value="ADJUST_IN">Adjustment in</option>
          </select>
        </Field>
        <Field label="Source" required>
          <select className={inputClass} value={form.source} onChange={(event) => set('source', event.target.value)}>
            <option value="INTERNAL">Internal</option>
            <option value="ADJUSTMENT">Adjustment</option>
          </select>
        </Field>
        <Field label="Quantity" required><input className={inputClass} type="number" min="0.01" step="0.01" value={form.quantity} onChange={(event) => set('quantity', event.target.value)} /></Field>
        <Field label="Unit price"><input className={inputClass} type="number" min="0" step="0.01" value={form.unit_price} onChange={(event) => set('unit_price', event.target.value)} /></Field>
        <Field label="Date"><input className={inputClass} type="date" value={form.date} onChange={(event) => set('date', event.target.value)} /></Field>
        <Field label="Notes" className="md:col-span-2"><textarea className={inputClass} value={form.notes} onChange={(event) => set('notes', event.target.value)} /></Field>
        <Button className="md:col-span-2" loading={mutation.isPending} loadingLabel="Saving movement…" disabled={!material.id || Number(form.quantity) <= 0}>Save movement</Button>
      </form>
    </FormModal>
  );
}
