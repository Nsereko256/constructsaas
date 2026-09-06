import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Boxes, CheckCircle2, Coins, Download, Eye, PackageCheck, PackageOpen, Pencil, Plus, ReceiptText, Route, Trash2, TrendingUp } from 'lucide-react';
import { FormEvent, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/api/services';
import type { Material } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { Pagination } from '@/components/common/pagination';
import { FormModal } from '@/components/common/form-modal';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';
import { WorkspaceTabs } from '@/components/common/workspace-hub';
import './operations-reference.css';

const units = ['bag', 'ton', 'kg', 'litre', 'piece', 'metre', 'sqm', 'cbm'];

export function InventoryPage() {
  const { role } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const list = useListState({ category: '', low_stock: '', is_active: 'true' });
  const [materialOpen, setMaterialOpen] = useState<Material | true | null>(null);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [selected, setSelected] = useState<Material | null>(null);
  const materials = useQuery({ queryKey: qk.materials(list.query), queryFn: () => api.materials(list.query) });
  const allMaterials = useQuery({ queryKey: qk.materials({ page_size: 100, inventory_summary: true }), queryFn: () => api.materials({ page_size: 100 }) });
  const movements = useQuery({ queryKey: qk.movements({ page_size: 8, inventory_summary: true }), queryFn: () => api.movements({ page_size: 8, ordering: '-date' }) });
  const dashboard = useQuery({ queryKey: qk.dashboard, queryFn: api.dashboard });
  const categories = useQuery({ queryKey: qk.categories(), queryFn: () => api.categories() });
  const allowed = can.manageMaterials(role);
  const canDeactivate = can.deactivateMaterials(role);
  const summaryMaterials = allMaterials.data?.results || [];
  const activeMaterials = summaryMaterials.filter((material) => material.is_active);
  const lowStock = activeMaterials.filter((material) => material.is_low_stock);
  const healthy = activeMaterials.length - lowStock.length;
  const inventoryValue = activeMaterials.reduce((total, material) => total + Number(material.stock_value), 0);
  const focused = selected || materials.data?.results[0] || activeMaterials[0] || null;
  const latestLocation = focused ? movements.data?.results.find((movement) => movement.material === focused.id)?.warehouse_name : null;

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
    { header: 'On hand', cell: ({ row }) => <strong>{formatNumber(row.original.current_stock)}</strong> },
    { header: 'Minimum', cell: ({ row }) => formatNumber(row.original.min_stock_level) },
    { header: 'Average cost', cell: ({ row }) => formatUGX(row.original.unit_price) },
    { header: 'Stock value', cell: ({ row }) => formatUGX(row.original.stock_value) },
    { header: 'Status', cell: ({ row }) => <Badge tone={row.original.is_low_stock ? 'warning' : 'success'}>{row.original.is_low_stock ? 'Low stock' : 'Healthy'}</Badge> },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) =>
        <div className="flex flex-wrap justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => setSelected(row.original)}><Eye className="h-4 w-4" />View</Button>{allowed ? <Button variant="ghost" size="sm" onClick={() => setMaterialOpen(row.original)}><Pencil className="h-4 w-4" />Edit</Button> : null}{canDeactivate ? <Button variant="ghost" size="sm" onClick={() => { if (window.confirm(`Deactivate ${row.original.name}? Existing stock history will be preserved.`)) deactivate.mutate(row.original.id); }}><Trash2 className="h-4 w-4" />Deactivate</Button> : null}</div>,
    },
  ];

  return (
    <div className="operations-reference grid gap-3">
      <header className="ops-page-head"><div className="ops-page-titlebar"><div><h1>Inventory</h1><p>Control material balances, locations, stock movements and site custody.</p></div><div className="ops-actions"><Button variant="secondary" onClick={() => void download('xlsx')}><Download className="h-4 w-4" />Export</Button>{['storekeeper', 'admin'].includes(role || '') ? <Button asChild><Link to="/procurement/requests?action_queue=my_requests"><PackageOpen className="h-4 w-4" />Issue stock</Link></Button> : null}{allowed ? <><Button variant="secondary" onClick={() => setCategoryOpen(true)}><Plus className="h-4 w-4" />Category</Button><Button onClick={() => setMaterialOpen(true)}><Plus className="h-4 w-4" />Material</Button></> : null}</div></div><div className="ops-tabs"><WorkspaceTabs links={[{ href: '/inventory', label: 'Stock', icon: Boxes }, { href: '/inventory/bin-locations', label: 'Bin locations', icon: ReceiptText }, { href: '/inventory/movements', label: 'Movements', icon: Route }, { href: '/inventory/site-custody', label: 'Site custody', icon: ReceiptText }]} /></div></header>
      {lowStock.length ? <div className="ops-alert"><span className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-warning" /><strong>{lowStock.length} stock action{lowStock.length === 1 ? '' : 's'} require attention.</strong></span><button className="ops-link" onClick={() => list.setFilter('low_stock', 'true')}>View stock queue →</button></div> : null}
      <section className="ops-kpis" aria-label="Inventory summary"><OpsKpi icon={PackageCheck} label="Active materials" value={activeMaterials.length} /><OpsKpi icon={Coins} label="Inventory value" value={formatUGX(inventoryValue)} tone="blue" /><OpsKpi icon={CheckCircle2} label="Healthy items" value={healthy} /><OpsKpi icon={AlertTriangle} label="Low-stock items" value={lowStock.length} tone="amber" /><OpsKpi icon={TrendingUp} label="Stock received today" value={formatNumber(dashboard.data?.stock_in_today || 0)} tone="teal" /></section>
      <div className="ops-workspace"><section className="ops-register"><div className="ops-register-head"><h2>Stock register</h2>{['storekeeper', 'admin'].includes(role || '') ? <Button size="sm" asChild><Link to="/inventory/movements"><Boxes className="h-4 w-4" />Stock transaction</Link></Button> : null}</div><div className="ops-register-tabs"><button className={!list.filters.low_stock && list.filters.is_active === 'true' ? 'active' : ''} onClick={() => { list.setFilter('low_stock', ''); list.setFilter('is_active', 'true'); }}>All <small>{activeMaterials.length}</small></button><button className={list.filters.low_stock === 'false' ? 'active' : ''} onClick={() => { list.setFilter('low_stock', 'false'); list.setFilter('is_active', 'true'); }}>Healthy <small>{healthy}</small></button><button className={list.filters.low_stock === 'true' ? 'active' : ''} onClick={() => { list.setFilter('low_stock', 'true'); list.setFilter('is_active', 'true'); }}>Low stock <small>{lowStock.length}</small></button><button className={list.filters.is_active === 'false' ? 'active' : ''} onClick={() => { list.setFilter('is_active', 'false'); list.setFilter('low_stock', ''); }}>Inactive</button></div><div className="ops-filters"><input className={inputClass} value={list.search} onChange={(event) => list.setSearch(event.target.value)} placeholder="Search material, code or category" /><select className={inputClass} value={list.filters.category} onChange={(event) => list.setFilter('category', event.target.value)}><option value="">All categories</option>{(categories.data?.results || []).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select><select className={inputClass} value={list.filters.low_stock} onChange={(event) => list.setFilter('low_stock', event.target.value)}><option value="">All stock levels</option><option value="true">Low stock only</option><option value="false">Healthy only</option></select><select className={inputClass} value={list.filters.is_active} onChange={(event) => list.setFilter('is_active', event.target.value)}><option value="true">Active</option><option value="false">Inactive</option><option value="">All records</option></select></div><DataTable columns={columns} data={materials.data?.results || []} mobileSummaryCells={2} emptyTitle={materials.isLoading ? 'Loading materials...' : 'No materials found'} /><Pagination page={list.page} setPage={list.setPage} data={materials.data} /></section>
        <aside className="ops-aside"><section className="ops-panel"><div className="ops-panel-head"><h2>Stock health</h2></div><div className="ops-panel-body ops-donut-wrap"><div className="ops-donut" style={{ background: `conic-gradient(var(--ops-green) 0 ${activeMaterials.length ? healthy / activeMaterials.length * 100 : 0}%, var(--ops-amber) 0)` }}><div className="ops-donut-label"><strong>{activeMaterials.length}</strong>Total</div></div><div className="ops-legend"><span><i style={{ background: 'var(--ops-green)' }} />Healthy <strong>{healthy}</strong></span><span><i style={{ background: 'var(--ops-amber)' }} />Low stock <strong>{lowStock.length}</strong></span></div></div></section>{focused ? <section className="ops-panel"><div className="ops-panel-head"><h2>{focused.name}</h2></div><div className="ops-panel-body"><OpsRow icon={Boxes} label="On hand" value={`${formatNumber(focused.current_stock)} ${focused.unit_display}`} /><OpsRow icon={AlertTriangle} label="Minimum" value={`${formatNumber(focused.min_stock_level)} ${focused.unit_display}`} /><OpsRow icon={Coins} label="Stock value" value={formatUGX(focused.stock_value)} /><OpsRow icon={Route} label="Latest location" value={latestLocation || 'Not recorded'} /></div></section> : null}<section className="ops-panel"><div className="ops-panel-head"><h2>Recent movements</h2><Link className="ops-link" to="/inventory/movements">View all →</Link></div><div className="ops-panel-body">{(movements.data?.results || []).slice(0, 4).map((movement) => <div className="ops-stat-row" key={movement.id}><Boxes /><span><strong className="block !text-left">{movement.movement_type_display} {formatNumber(movement.quantity)}</strong><small>{movement.material_name}</small></span><small>{formatDate(movement.date)}</small></div>)}{!movements.data?.results.length ? <p className="text-xs text-muted">No movements recorded.</p> : null}</div></section></aside>
      </div>
      <MaterialModal key={materialOpen && materialOpen !== true ? materialOpen.id : materialOpen ? 'new' : 'closed'} open={!!materialOpen} material={materialOpen === true ? null : materialOpen} onClose={() => setMaterialOpen(null)} />
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

function OpsKpi({ icon: Icon, label, value, tone = '' }: { icon: typeof Boxes; label: string; value: ReactNode; tone?: string }) { return <div className={`ops-kpi ${tone}`}><div className="ops-kpi-icon"><Icon /></div><div><p>{label}</p><strong>{value}</strong></div></div>; }
function OpsRow({ icon: Icon, label, value }: { icon: typeof Boxes; label: string; value: ReactNode }) { return <div className="ops-stat-row"><Icon /><span>{label}</span><strong>{value}</strong></div>; }

function MaterialModal({ open, material, onClose }: { open: boolean; material: Material | null; onClose: () => void }) {
  const categories = useQuery({ queryKey: qk.categories(), queryFn: () => api.categories() });
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({
    category: material ? String(material.category) : '',
    name: material?.name || '',
    code: material?.code || '',
    unit: material?.unit || 'bag',
    unit_price: material?.unit_price || '',
    min_stock_level: material?.min_stock_level || '0',
    description: material?.description || '',
  });
  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const mutation = useMutation({
    mutationFn: () => api.saveMaterial({
      ...form,
      category: Number(form.category),
    } as Partial<Material>, material?.id),
    onSuccess: () => {
      toast.push({ title: material ? 'Material updated' : 'Material created', tone: 'success' });
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['materials'] });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    },
    onError: (error: Error) => toast.push({ title: 'Could not save material', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title={material ? `Edit ${material.name}` : 'Create material'} onClose={onClose}>
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
        <Button className="md:col-span-2" disabled={!form.category || !form.name || !form.code || mutation.isPending}>{material ? 'Save changes' : 'Save material'}</Button>
      </form>
    </FormModal>
  );
}
