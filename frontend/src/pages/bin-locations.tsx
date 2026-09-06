import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { api } from '@/api/services';
import { FormModal } from '@/components/common/form-modal';
import { PageToolbar } from '@/components/common/page-toolbar';
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
    },
    onError: (error: Error) => toast.push({ title: 'Could not save bin', message: error.message, tone: 'danger' }),
  });

  return <div className="grid gap-4">
    <PageToolbar title="Bin locations" subtitle="Controlled rack, shelf, and bin locations for warehouse and project-site stores.">
      <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Bin location</Button>
    </PageToolbar>
    <div className="grid gap-2">
      {(bins.data?.results || []).map((bin) => <div key={bin.id} className="flex items-center justify-between rounded-xl border border-border bg-white p-3"><div><strong>{bin.code}</strong><p className="text-sm text-muted">{bin.warehouse_name}{bin.description ? ` · ${bin.description}` : ''}</p></div><Badge tone={bin.is_active ? 'success' : 'neutral'}>{bin.is_active ? 'Active' : 'Inactive'}</Badge></div>)}
      {!bins.data?.results.length ? <p className="rounded-xl border border-dashed border-border p-4 text-sm text-muted">No bin locations configured.</p> : null}
    </div>
    <Pagination page={page} setPage={setPage} data={bins.data} />
    <FormModal open={open} title="Add bin location" onClose={() => setOpen(false)}><form className="grid gap-3" onSubmit={(event: FormEvent) => { event.preventDefault(); save.mutate(); }}><Field label="Warehouse or site store" required><select className={inputClass} value={form.warehouse} onChange={(event) => setForm({ ...form, warehouse: event.target.value })}><option value="">Select location</option>{(warehouses.data?.results || []).map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}</select></Field><Field label="Bin / rack code" required><input className={inputClass} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></Field><Field label="Description"><input className={inputClass} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></Field><Button disabled={!form.warehouse || !form.code || save.isPending}>Save bin location</Button></form></FormModal>
  </div>;
}
