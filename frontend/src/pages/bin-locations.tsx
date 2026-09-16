import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { api } from '@/api/services';
import { FormModal } from '@/components/common/form-modal';
import { PageToolbar } from '@/components/common/page-toolbar';
import { InventoryTabs } from '@/components/common/inventory-tabs';
import { DataTable } from '@/components/ui/data-table';
import './operations-reference.css';
import './inventory-registers.css';
import { Pagination } from '@/components/common/pagination';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';

export function BinLocationsPage() {
  const toast = useToast();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const bins = useQuery({ queryKey: ['bin-locations', page], queryFn: () => api.binLocations({ page, page_size: 20 }) });
  const warehouses = useQuery({ queryKey: ['warehouses', 'bin-form'], queryFn: () => api.warehouses({ page_size: 100, is_active: true }) });
  const [form, setForm] = useState({ warehouse: '', code: '', description: '' });
  const save = useMutation({
    mutationFn: () => api.saveBinLocation({ warehouse: Number(form.warehouse), code: form.code, description: form.description, is_active: true }),
    onSuccess: () => {
      toast.push({ title: 'Bin location saved', tone: 'success' });
      void client.invalidateQueries({ queryKey: ['bin-locations'] });
      setOpen(false);
      setForm({ warehouse: '', code: '', description: '' });
    },
    onError: (error: Error) => toast.push({ title: 'Could not save bin', message: error.message, tone: 'danger' }),
  });

  return <div className="operations-reference inventory-register-page grid gap-4">
    <PageToolbar title="Bin locations" subtitle="Controlled rack, shelf, and bin locations for warehouse and project-site stores.">
      <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New bin location</Button>
    </PageToolbar>
    <InventoryTabs />
    <section className="ops-register">
      <div className="ops-register-head"><h2>Location directory</h2><span className="text-sm text-muted">{bins.data ? `${bins.data.count} locations` : 'Warehouse and site stores'}</span></div>
      {bins.isError ? <div className="p-4" role="alert"><p>Could not load bin locations.</p><Button variant="secondary" onClick={() => void bins.refetch()}>Retry</Button></div> : bins.isLoading ? <p className="p-4 text-sm text-muted" role="status">Loading bin locations…</p> : <DataTable columns={[
        { header: 'Bin / rack', cell: ({ row }) => <strong>{row.original.code}</strong> },
        { header: 'Warehouse / site store', accessorKey: 'warehouse_name' },
        { header: 'Description', cell: ({ row }) => row.original.description || '—' },
        { header: 'Status', cell: ({ row }) => <Badge tone={row.original.is_active ? 'success' : 'neutral'}>{row.original.is_active ? 'Active' : 'Inactive'}</Badge> },
      ]} data={bins.data?.results || []} emptyTitle="No bin locations yet" emptyMessage="Add a rack, shelf or bin to organise your store." />}
    <Pagination page={page} setPage={setPage} data={bins.data} />
    </section>
    <FormModal open={open} title="Add bin location" onClose={() => setOpen(false)}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); save.mutate(); }}><Field label="Warehouse or site store" required><select className={inputClass} value={form.warehouse} onChange={(event) => setForm({ ...form, warehouse: event.target.value })}><option value="">Select location</option>{(warehouses.data?.results || []).map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}</select></Field><Field label="Bin / rack code" required><input className={inputClass} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></Field><Field label="Description"><input className={inputClass} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></Field><Button disabled={!form.warehouse || !form.code || save.isPending}>Save bin location</Button></form></FormModal>
  </div>;
}
