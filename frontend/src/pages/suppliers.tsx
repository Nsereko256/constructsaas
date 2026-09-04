import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileWarning, Plus, Trash2, Users } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { api } from '@/api/services';
import type { Supplier } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { WorkspaceTabs } from '@/components/common/workspace-hub';

export function SuppliersPage() {
  const { role } = useAuth();
  const list = useListState({ rating: '', is_active: 'true' });
  const [open, setOpen] = useState(false);
  const suppliers = useQuery({ queryKey: qk.suppliers(list.query), queryFn: () => api.suppliers(list.query) });
  const queryClient = useQueryClient();
  const toast = useToast();
  const allowed = can.manageSuppliers(role);
  const deactivate = useMutation({
    mutationFn: (id: number) => api.saveSupplier({ is_active: false }, id),
    onSuccess: () => {
      toast.push({ title: 'Supplier deactivated', tone: 'success' });
      void queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    },
    onError: (error: Error) => toast.push({ title: 'Could not update supplier', message: error.message, tone: 'danger' }),
  });
  const columns: ColumnDef<Supplier>[] = [
    {
      header: 'Supplier',
      cell: ({ row }) => (
        <div>
          <strong>{row.original.name}</strong>
          <p className="text-xs text-muted">{row.original.contact_person || 'No contact person'}</p>
        </div>
      ),
    },
    { header: 'Phone', cell: ({ row }) => row.original.phone || '-' },
    { header: 'Email', cell: ({ row }) => row.original.email || '-' },
    { header: 'Rating', cell: ({ row }) => `${row.original.rating}/5` },
    { header: 'Type', cell: ({ row }) => row.original.is_contractor ? `Contractor${row.original.contractor_specialty ? ` · ${row.original.contractor_specialty}` : ''}` : 'Supplier' },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) =>
        allowed ? (
          <Button variant="ghost" size="sm" onClick={() => deactivate.mutate(row.original.id)}>
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="grid gap-4">
      <WorkspaceTabs links={[{ href: '/suppliers', label: 'Suppliers & contractors', description: 'Vendor directory', icon: Users }, { href: '/procurement/supplier-claims', label: 'Claims', description: 'Supplier issues', icon: FileWarning }]} />
      <PageToolbar title="Suppliers" subtitle="Approved vendor contacts and performance notes." search={list.search} onSearch={list.setSearch}>
        <select className={inputClass} value={list.filters.rating} onChange={(event) => list.setFilter('rating', event.target.value)}>
          <option value="">All ratings</option>
          {[5, 4, 3, 2, 1].map((rating) => <option key={rating} value={rating}>{rating} stars</option>)}
        </select>
        {allowed ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Supplier / contractor</Button> : null}
      </PageToolbar>
      <DataTable columns={columns} data={suppliers.data?.results || []} emptyTitle={suppliers.isLoading ? 'Loading suppliers...' : 'No suppliers found'} />
      <Pagination page={list.page} setPage={list.setPage} data={suppliers.data} />
      <SupplierModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function SupplierModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form, setForm] = useState({ name: '', contact_person: '', phone: '', email: '', address: '', rating: '3', is_contractor: false, contractor_specialty: '', notes: '' });
  const set = (key: Exclude<keyof typeof form, 'is_contractor'>, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const queryClient = useQueryClient();
  const toast = useToast();
  const mutation = useMutation({
    mutationFn: () => api.saveSupplier({
      ...form,
      rating: Number(form.rating),
    } as Partial<Supplier>),
    onSuccess: () => {
      toast.push({ title: 'Supplier saved', tone: 'success' });
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    },
    onError: (error: Error) => toast.push({ title: 'Could not save supplier', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title="Register supplier or contractor" onClose={onClose}>
      <form className="grid gap-3 md:grid-cols-2" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
        <Field label="Supplier name" required><input className={inputClass} value={form.name} onChange={(event) => set('name', event.target.value)} /></Field>
        <Field label="Contact person"><input className={inputClass} value={form.contact_person} onChange={(event) => set('contact_person', event.target.value)} /></Field>
        <Field label="Phone"><input className={inputClass} value={form.phone} onChange={(event) => set('phone', event.target.value)} /></Field>
        <Field label="Email"><input className={inputClass} type="email" value={form.email} onChange={(event) => set('email', event.target.value)} /></Field>
        <Field label="Rating"><input className={inputClass} type="number" min="1" max="5" value={form.rating} onChange={(event) => set('rating', event.target.value)} /></Field>
        <Field label="Address"><input className={inputClass} value={form.address} onChange={(event) => set('address', event.target.value)} /></Field>
        <Field label="Organisation type" className="md:col-span-2"><label className="flex items-center gap-2 rounded-lg border border-border p-3 text-sm"><input type="checkbox" checked={form.is_contractor} onChange={(event) => setForm((current) => ({ ...current, is_contractor: event.target.checked }))} />This supplier is also an approved work-order contractor.</label></Field>
        {form.is_contractor ? <Field label="Contractor trade / speciality" required className="md:col-span-2"><input className={inputClass} required value={form.contractor_specialty} onChange={(event) => set('contractor_specialty', event.target.value)} placeholder="e.g. Electrical, plumbing, civil works" /></Field> : null}
        <Field label="Notes" className="md:col-span-2"><textarea className={inputClass} value={form.notes} onChange={(event) => set('notes', event.target.value)} /></Field>
        <Button className="md:col-span-2" disabled={!form.name || mutation.isPending}>Save supplier</Button>
      </form>
    </FormModal>
  );
}
