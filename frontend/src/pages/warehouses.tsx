import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/api/services';
import type { Warehouse } from '@/api/types';
import { useAuth } from '@/auth/auth-context';
import { InventoryTabs } from '@/components/common/inventory-tabs';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { FormModal } from '@/components/common/form-modal';
import { WarehouseForm } from '@/components/inventory/warehouse-form';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { inputClass } from '@/components/ui/field';
import './operations-reference.css';

export function WarehousesPage() {
  const { role } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Warehouse | 'new' | null>(null);
  const [saved, setSaved] = useState<Warehouse | null>(null);
  const warehouses = useQuery({ queryKey: ['warehouses', 'directory', page, search], queryFn: () => api.companyWarehouses({ page, page_size: 10, search }) });
  return <div className="operations-reference grid gap-4">
    <PageToolbar title="Warehouses" subtitle="Company-wide receiving locations and the codes used in Excel imports.">
      {role === 'admin' ? <Button onClick={() => setEditing('new')}><Plus className="h-4 w-4" />New warehouse</Button> : null}
    </PageToolbar>
    <InventoryTabs />
    <div className="rounded-lg border border-border bg-white p-4 text-sm">
      <p>For onboarding: register a warehouse, download the opening-stock template, and enter its code in column E.</p>
      <p className="mt-1 text-muted">Only Admins can register or edit warehouses. Stock stays unchanged until an Admin approves and posts the opening-stock import.</p>
      {['admin', 'storekeeper'].includes(role || '') ? <Button asChild variant="secondary" className="mt-3"><Link to="/inventory?import=opening-stock">Import opening stock</Link></Button> : null}
    </div>
    {saved ? <p role="status" className="rounded-md border border-primary/20 bg-white p-3">Warehouse saved. Use <strong>{saved.code}</strong> in your Excel workbook.</p> : null}
    <section className="ops-register" data-pagination-region>
      <div className="ops-register-head"><h2>Warehouse directory</h2><input aria-label="Search warehouses" className={`${inputClass} max-w-sm`} placeholder="Search name, code or location" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} /></div>
      {warehouses.isError ? <div role="alert" className="p-4"><p>Could not load warehouses.</p><Button variant="secondary" onClick={() => void warehouses.refetch()}>Retry</Button></div> : warehouses.isLoading ? <p role="status" className="p-4">Loading warehouses…</p> : <DataTable<Warehouse> data={warehouses.data?.results || []} columns={[
        { header: 'Warehouse', cell: ({ row }) => <strong>{row.original.name}</strong> },
        { header: 'Excel code', cell: ({ row }) => <code className="font-semibold">{row.original.code}</code> },
        { header: 'Location', cell: ({ row }) => row.original.location || '—' },
        { header: 'Status', cell: ({ row }) => <div className="flex flex-wrap gap-2"><Badge tone={row.original.is_active ? 'success' : 'neutral'}>{row.original.is_active ? 'Active' : 'Inactive'}</Badge>{row.original.is_default ? <Badge tone="info">Default</Badge> : null}{row.original.project || row.original.project_site ? <Badge tone="neutral">Site store</Badge> : null}</div> },
        ...(role === 'admin' ? [{ id: 'actions', header: 'Action', cell: ({ row }: { row: { original: Warehouse } }) => !row.original.project && !row.original.project_site ? <Button size="sm" variant="secondary" onClick={() => setEditing(row.original)}>Edit</Button> : null }] : []),
      ]} emptyTitle="No warehouses found" emptyMessage={role === 'admin' ? 'Register your receiving warehouse before preparing the Excel import.' : 'Ask an Admin to register a warehouse and share its Excel code.'} />}
      <Pagination page={page} setPage={setPage} data={warehouses.data} loading={warehouses.isFetching} pageSize={10} itemLabel="warehouses" />
    </section>
    <FormModal open={!!editing} title={editing === 'new' ? 'New warehouse' : 'Edit warehouse'} onClose={() => setEditing(null)}>
      {editing ? <WarehouseForm key={editing === 'new' ? 'new' : editing.id} warehouse={editing === 'new' ? undefined : editing} defaultWarehouse={!search && warehouses.data?.count === 0} onCancel={() => setEditing(null)} onSaved={(warehouse) => { setSaved(warehouse); setEditing(null); }} /> : null}
    </FormModal>
  </div>;
}
