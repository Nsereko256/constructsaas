import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Boxes, Download, PackageOpen, Plus, ReceiptText, Route, Trash2 } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/api/services';
import type { Material } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { FormModal } from '@/components/common/form-modal';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatNumber, formatUGX } from '@/lib/utils';
import { WorkspaceTabs } from '@/components/common/workspace-hub';

const units = ['bag', 'ton', 'kg', 'litre', 'piece', 'metre', 'sqm', 'cbm'];

export function InventoryPage() {
  const { role } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const list = useListState({ category: '', low_stock: '', is_active: 'true' });
  const [materialOpen, setMaterialOpen] = useState(false);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const materials = useQuery({ queryKey: qk.materials(list.query), queryFn: () => api.materials(list.query) });
  const categories = useQuery({ queryKey: qk.categories(), queryFn: () => api.categories() });
  const allowed = can.manageMaterials(role);
  const canDeactivate = can.deactivateMaterials(role);

  const deactivate = useMutation({
    mutationFn: api.deleteMaterial,
    onSuccess: () => {
      toast.push({ title: 'Material deactivated', tone: 'success' });
      void queryClient.invalidateQueries({ queryKey: ['materials'] });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    },
    onError: (error: Error) => toast.push({ title: 'Could not deactivate material', message: error.message, tone: 'danger' }),
  });
  const download = async (kind: 'pdf' | 'xlsx') => {
    try { await (kind === 'pdf' ? api.downloadInventoryPdf(list.filters) : api.downloadInventoryXlsx(list.filters)); toast.push({ title: `Inventory ${kind === 'xlsx' ? 'Excel' : 'PDF'} prepared`, tone: 'success' }); }
    catch (error) { toast.push({ title: 'Inventory export failed', message: (error as Error).message, tone: 'danger' }); }
  };

  const columns: ColumnDef<Material>[] = [
    {
      header: 'Material',
      cell: ({ row }) => (
        <div>
          <strong>{row.original.name}</strong>
          <p className="text-xs text-muted">{row.original.code} / {row.original.category_name}</p>
        </div>
      ),
    },
    { header: 'Unit', cell: ({ row }) => row.original.unit_display },
    { header: 'Stock', cell: ({ row }) => <strong>{formatNumber(row.original.current_stock)}</strong> },
    { header: 'Min', cell: ({ row }) => formatNumber(row.original.min_stock_level) },
    { header: 'Value', cell: ({ row }) => formatUGX(row.original.stock_value) },
    { header: 'Status', cell: ({ row }) => <Badge tone={row.original.is_low_stock ? 'warning' : 'success'}>{row.original.is_low_stock ? 'Low stock' : 'Healthy'}</Badge> },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) =>
        canDeactivate ? (
          <Button variant="ghost" size="sm" onClick={() => deactivate.mutate(row.original.id)}>
            <Trash2 className="h-4 w-4" />
            Deactivate
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="grid gap-4">
      <WorkspaceTabs links={[{ href: '/inventory', label: 'Stock', description: 'Materials and valuation', icon: Boxes }, { href: '/inventory/bin-locations', label: 'Bin locations', description: 'Storage map', icon: ReceiptText }, { href: '/inventory/movements', label: 'Movements', description: 'Stock transfers', icon: Route }, { href: '/inventory/site-custody', label: 'Site custody', description: 'Dispatch and consumption', icon: ReceiptText }]} />
      <PageToolbar title="Inventory" subtitle="Materials, categories, stock thresholds and current valuation." search={list.search} onSearch={list.setSearch}>
        <select className={inputClass} value={list.filters.category} onChange={(event) => list.setFilter('category', event.target.value)}>
          <option value="">All categories</option>
          {(categories.data?.results || []).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
        </select>
        <select className={inputClass} value={list.filters.low_stock} onChange={(event) => list.setFilter('low_stock', event.target.value)}>
          <option value="">All stock levels</option>
          <option value="true">Low stock only</option>
          <option value="false">Healthy only</option>
        </select>
        <Button variant="secondary" onClick={() => void download('pdf')}><Download className="h-4 w-4" />PDF</Button>
        <Button variant="secondary" onClick={() => void download('xlsx')}><Download className="h-4 w-4" />Excel</Button>
        {['storekeeper', 'admin'].includes(role || '') ? <Button asChild><Link to="/procurement/requests?action_queue=my_requests"><PackageOpen className="h-4 w-4" />Issue stock</Link></Button> : null}
        {allowed ? (
          <>
            <Button variant="secondary" onClick={() => setCategoryOpen(true)}><Plus className="h-4 w-4" />Category</Button>
            <Button onClick={() => setMaterialOpen(true)}><Plus className="h-4 w-4" />Material</Button>
          </>
        ) : null}
      </PageToolbar>
      <DataTable columns={columns} data={materials.data?.results || []} emptyTitle={materials.isLoading ? 'Loading materials...' : 'No materials found'} />
      <Pagination page={list.page} setPage={list.setPage} data={materials.data} />
      <MaterialModal open={materialOpen} onClose={() => setMaterialOpen(false)} />
      <CategoryModal open={categoryOpen} onClose={() => setCategoryOpen(false)} />
    </div>
  );
}

function CategoryModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const queryClient = useQueryClient();
  const toast = useToast();
  const mutation = useMutation({
    mutationFn: () => api.createCategory({ name, description }),
    onSuccess: () => {
      toast.push({ title: 'Category created', tone: 'success' });
      setName('');
      setDescription('');
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['categories'] });
    },
    onError: (error: Error) => toast.push({ title: 'Could not create category', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title="Create material category" onClose={onClose}>
      <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
        <Field label="Category name" required><input className={inputClass} value={name} onChange={(event) => setName(event.target.value)} /></Field>
        <Field label="Description"><textarea className={inputClass} value={description} onChange={(event) => setDescription(event.target.value)} /></Field>
        <Button disabled={!name || mutation.isPending}>Save category</Button>
      </form>
    </FormModal>
  );
}

function MaterialModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const categories = useQuery({ queryKey: qk.categories(), queryFn: () => api.categories() });
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({
    category: '',
    name: '',
    code: '',
    unit: 'bag',
    unit_price: '',
    min_stock_level: '0',
    description: '',
  });
  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const mutation = useMutation({
    mutationFn: () => api.saveMaterial({
      ...form,
      category: Number(form.category),
    } as Partial<Material>),
    onSuccess: () => {
      toast.push({ title: 'Material created', tone: 'success' });
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['materials'] });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    },
    onError: (error: Error) => toast.push({ title: 'Could not save material', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title="Create material" onClose={onClose}>
      <form className="grid gap-3 md:grid-cols-2" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
        <Field label="Category" required>
          <select className={inputClass} value={form.category} onChange={(event) => set('category', event.target.value)}>
            <option value="">Select category</option>
            {(categories.data?.results || []).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
          </select>
        </Field>
        <Field label="Material name" required><input className={inputClass} value={form.name} onChange={(event) => set('name', event.target.value)} /></Field>
        <Field label="Code" required><input className={inputClass} value={form.code} onChange={(event) => set('code', event.target.value)} /></Field>
        <Field label="Unit" required>
          <select className={inputClass} value={form.unit} onChange={(event) => set('unit', event.target.value)}>
            {units.map((unit) => <option key={unit} value={unit}>{unit}</option>)}
          </select>
        </Field>
        <Field label="Unit price"><input className={inputClass} type="number" min="0" value={form.unit_price} onChange={(event) => set('unit_price', event.target.value)} /></Field>
        <Field label="Minimum stock"><input className={inputClass} type="number" min="0" value={form.min_stock_level} onChange={(event) => set('min_stock_level', event.target.value)} /></Field>
        <Field label="Description" className="md:col-span-2"><textarea className={inputClass} value={form.description} onChange={(event) => set('description', event.target.value)} /></Field>
        <Button className="md:col-span-2" disabled={!form.category || !form.name || !form.code || mutation.isPending}>Save material</Button>
      </form>
    </FormModal>
  );
}
