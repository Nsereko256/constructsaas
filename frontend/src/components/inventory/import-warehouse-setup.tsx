import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '@/api/services';
import { useAuth } from '@/auth/auth-context';
import { Pagination } from '@/components/common/pagination';
import { Button } from '@/components/ui/button';
import { inputClass } from '@/components/ui/field';
import { WarehouseForm } from './warehouse-form';

export function ImportWarehouseSetup({ onCreated }: { onCreated: () => void }) {
  const { role } = useAuth();
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [savedCode, setSavedCode] = useState('');
  const warehouses = useQuery({ queryKey: ['warehouses', 'import', page, search], queryFn: () => api.companyWarehouses({ is_active: true, page, page_size: 5, search }) });
  return <section aria-label="Warehouse setup" className="rounded-lg border border-border bg-white p-3" data-pagination-region>
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold">1. Confirm your warehouse</h3>{role === 'admin' && !creating ? <Button variant="secondary" onClick={() => setCreating(true)}>New warehouse</Button> : null}</div>
    <p className="mt-1 text-sm text-muted">Use a code below in column E of the workbook. The list includes active warehouses across your company, regardless of the site filter.</p>
    {savedCode ? <p role="status" className="mt-2 text-sm">Warehouse registered. Use <strong>{savedCode}</strong> in Excel, or download the template again for the updated warehouse reference.</p> : null}
    {creating ? <div className="mt-3 rounded-md border border-border p-3"><WarehouseForm defaultWarehouse={!search && warehouses.data?.count === 0} onCancel={() => setCreating(false)} onSaved={(warehouse) => { setSavedCode(warehouse.code); setCreating(false); onCreated(); }} /></div> : <>
      <input aria-label="Find warehouse code" className={`${inputClass} mt-3`} placeholder="Search warehouse name or code" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
      {warehouses.isError ? <div role="alert" className="mt-2"><p>Could not load warehouse codes.</p><Button variant="secondary" onClick={() => void warehouses.refetch()}>Retry warehouses</Button></div> : warehouses.isLoading ? <p role="status" className="mt-2 text-sm">Loading warehouses…</p> : warehouses.data?.count ? <ul className="mt-2 divide-y divide-border">{warehouses.data.results.map((warehouse) => <li key={warehouse.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"><span>{warehouse.name}{warehouse.is_default ? ' (default)' : ''}</span><code className="font-bold">{warehouse.code}</code></li>)}</ul> : <p role="status" className="mt-3 text-sm font-semibold">{search ? 'No matching active warehouse. Check the code or clear the search.' : role === 'admin' ? 'No active warehouses. Register one before importing opening stock.' : 'No active warehouses. Ask an Admin to register one before importing opening stock.'}</p>}
      <Pagination page={page} setPage={setPage} data={warehouses.data} loading={warehouses.isFetching} pageSize={5} itemLabel="warehouses" />
    </>}
  </section>;
}
