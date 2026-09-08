import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Clock3, Coins, Download, Eye, Mail, MapPin, PackageCheck, Pencil, Phone, Plus, Star, Trash2, Truck, Users } from 'lucide-react';
import { FormEvent, useMemo, useState, type ReactNode } from 'react';
import { api } from '@/api/services';
import type { Supplier } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { Pagination } from '@/components/common/pagination';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatUGX } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import './operations-reference.css';

export function SuppliersPage() {
  const { role } = useAuth();
  const list = useListState({ rating: '', is_active: '', is_preferred: '' });
  const [open, setOpen] = useState<Supplier | true | null>(null);
  const [view, setView] = useState<'all' | 'active' | 'preferred' | 'inactive'>('all');
  const [selected, setSelected] = useState<Supplier | null>(null);
  const suppliers = useQuery({ queryKey: qk.suppliers(list.query), queryFn: () => api.suppliers(list.query) });
  const allSuppliers = useQuery({ queryKey: qk.suppliers({ page_size: 100, directory_summary: true }), queryFn: () => api.suppliers({ page_size: 100 }) });
  const orders = useQuery({ queryKey: qk.purchaseOrders({ page_size: 100, supplier_summary: true }), queryFn: () => api.purchaseOrders({ page_size: 100 }) });
  const receipts = useQuery({ queryKey: qk.goodsReceivedNotes({ page_size: 100, supplier_summary: true }), queryFn: () => api.goodsReceivedNotes({ page_size: 100 }) });
  const queryClient = useQueryClient();
  const toast = useToast();
  const allowed = can.manageSuppliers(role);
  const directory = allSuppliers.data?.results || [];
  const active = directory.filter((supplier) => supplier.is_active);
  const preferred = active.filter((supplier) => supplier.is_preferred);
  const averageRating = active.length ? active.reduce((total, supplier) => total + Number(supplier.rating), 0) / active.length : 0;
  const allOrders = useMemo(() => orders.data?.results || [], [orders.data?.results]);
  const allReceipts = useMemo(() => receipts.data?.results || [], [receipts.data?.results]);
  const openOrders = allOrders.filter((order) => !['RECEIVED', 'CANCELLED'].includes(order.status));
  const receivedWithDates = allOrders.filter((order) => order.status === 'RECEIVED' && order.received_at && (order.revised_delivery_date || order.expected_delivery_date));
  const onTimeOrders = receivedWithDates.filter((order) => new Date(order.received_at!).getTime() <= new Date(order.revised_delivery_date || order.expected_delivery_date!).setHours(23, 59, 59, 999));
  const overallOnTime = receivedWithDates.length ? Math.round(onTimeOrders.length / receivedWithDates.length * 100) : null;
  const visibleSuppliers = suppliers.data?.results || [];
  const focused = selected || visibleSuppliers[0] || active[0] || null;
  const supplierMetrics = useMemo(() => getSupplierMetrics(focused, allOrders, allReceipts), [focused, allOrders, allReceipts]);
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
    { header: 'Contact', cell: ({ row }) => <div>{row.original.contact_person || 'Not provided'}<p className="text-xs text-muted">{row.original.phone || row.original.email || 'No contact details'}</p></div> },
    { header: 'Open POs', cell: ({ row }) => allOrders.filter((order) => order.supplier === row.original.id && !['RECEIVED','CANCELLED'].includes(order.status)).length },
    { header: 'Order value', cell: ({ row }) => formatUGX(allOrders.filter((order) => order.supplier === row.original.id).reduce((total, order) => total + Number(order.total_cost), 0)) },
    { header: 'On-time', cell: ({ row }) => { const metric = getSupplierMetrics(row.original, allOrders, allReceipts); return metric.onTime === null ? '—' : `${metric.onTime}%`; } },
    { header: 'Quality', cell: ({ row }) => { const metric = getSupplierMetrics(row.original, allOrders, allReceipts); return metric.quality === null ? '—' : `${metric.quality}%`; } },
    { header: 'Rating', cell: ({ row }) => <span className="font-bold text-warning">★ {Number(row.original.rating).toFixed(1)} / 5</span> },
    { header: 'Status', cell: ({ row }) => <Badge tone={row.original.is_active ? 'success' : 'neutral'}>{row.original.is_active ? row.original.is_preferred ? 'Preferred' : 'Active' : 'Inactive'}</Badge> },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) =>
        <div className="ops-row-actions"><Button variant="ghost" size="sm" onClick={() => setSelected(row.original)}><Eye className="h-4 w-4" />View</Button>{allowed ? <><Button variant="ghost" size="sm" onClick={() => setOpen(row.original)}><Pencil className="h-4 w-4" />Edit</Button>{row.original.is_active ? <Button variant="ghost" size="sm" onClick={() => { if (window.confirm(`Deactivate ${row.original.name}? Existing procurement history will remain available.`)) deactivate.mutate(row.original.id); }}><Trash2 className="h-4 w-4" />Deactivate</Button> : null}</> : null}</div>,
    },
  ];

  return (
    <div className="operations-reference suppliers-reference grid gap-3">
      <header className="ops-page-head"><div className="ops-page-titlebar"><div><h1>Suppliers</h1><p>Manage approved vendors, contact details and delivery performance.</p></div><div className="ops-actions"><Button variant="secondary" onClick={() => exportSuppliers(directory)}><Download className="h-4 w-4" />Export</Button>{allowed ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New supplier</Button> : null}</div></div></header>
      <section className="ops-kpis" aria-label="Supplier summary"><OpsKpi icon={Users} label="Total suppliers" value={directory.length} tone="blue" /><OpsKpi icon={CheckCircle2} label="Active suppliers" value={active.length} /><OpsKpi icon={Star} label="Average rating" value={`${averageRating.toFixed(1)} / 5`} tone="amber" /><OpsKpi icon={PackageCheck} label="Open purchase orders" value={openOrders.length} tone="blue" /><OpsKpi icon={Truck} label="On-time delivery" value={overallOnTime === null ? 'No data' : `${overallOnTime}%`} /></section>
      <div className="ops-workspace"><section className="ops-register"><div className="ops-register-head"><h2>Supplier directory</h2></div><div className="ops-register-tabs"><button className={view === 'all' ? 'active' : ''} onClick={() => { setView('all'); list.setFilter('is_active', ''); list.setFilter('is_preferred', ''); }}>All <small>{directory.length}</small></button><button className={view === 'active' ? 'active' : ''} onClick={() => { setView('active'); list.setFilter('is_active', 'true'); list.setFilter('is_preferred', ''); }}>Active <small>{active.length}</small></button><button className={view === 'preferred' ? 'active' : ''} onClick={() => { setView('preferred'); list.setFilter('is_active', 'true'); list.setFilter('is_preferred', 'true'); }}>Preferred <small>{preferred.length}</small></button><button className={view === 'inactive' ? 'active' : ''} onClick={() => { setView('inactive'); list.setFilter('is_active', 'false'); list.setFilter('is_preferred', ''); }}>Inactive <small>{directory.length - active.length}</small></button></div><div className="ops-filters"><input aria-label="Search suppliers" className={inputClass} value={list.search} onChange={(event) => list.setSearch(event.target.value)} placeholder="Search supplier, contact or address" /><select aria-label="Filter suppliers by rating" className={inputClass} value={list.filters.rating} onChange={(event) => list.setFilter('rating', event.target.value)}><option value="">All ratings</option>{[5,4,3,2,1].map((rating) => <option key={rating} value={rating}>{rating} stars</option>)}</select><select aria-label="Filter suppliers by activity" className={inputClass} value={list.filters.is_active} onChange={(event) => { const value = event.target.value; setView(value === 'true' ? 'active' : value === 'false' ? 'inactive' : 'all'); list.setFilter('is_preferred', ''); list.setFilter('is_active', value); }}><option value="">All statuses</option><option value="true">Active</option><option value="false">Inactive</option></select></div><DataTable columns={columns} data={visibleSuppliers} mobileSummaryCells={2} emptyTitle={suppliers.isLoading ? 'Loading suppliers...' : 'No suppliers found'} /><Pagination page={list.page} setPage={list.setPage} data={suppliers.data} /></section>
        <aside className="ops-aside">{focused ? <><section className="ops-panel"><div className="ops-panel-head"><h2>Supplier performance</h2></div><div className="ops-panel-body"><p className="mb-1 text-xs font-bold">{focused.name}</p><OpsRow icon={PackageCheck} label="Deliveries" value={supplierMetrics.deliveries} /><OpsRow icon={Clock3} label="On-time delivery" value={supplierMetrics.onTime === null ? 'Not measured' : `${supplierMetrics.onTime}%`} /><OpsRow icon={CheckCircle2} label="Receipt acceptance" value={supplierMetrics.quality === null ? 'Not measured' : `${supplierMetrics.quality}%`} /><OpsRow icon={Truck} label="Configured lead time" value={focused.lead_time_days ? `${focused.lead_time_days} days` : 'Not set'} /></div></section><section className="ops-panel"><div className="ops-panel-head"><h2>Procurement activity</h2></div><div className="ops-panel-body"><OpsRow icon={PackageCheck} label="Purchase orders" value={supplierMetrics.orders} /><OpsRow icon={Clock3} label="Open orders" value={supplierMetrics.openOrders} /><OpsRow icon={Coins} label="Total order value" value={formatUGX(supplierMetrics.orderValue)} /></div></section><section className="ops-panel"><div className="ops-panel-head"><h2>Profile completeness</h2></div><div className="ops-panel-body"><OpsRow icon={Phone} label="Phone number" value={focused.phone ? 'Provided' : 'Missing'} /><OpsRow icon={Mail} label="Email address" value={focused.email ? 'Provided' : 'Missing'} /><OpsRow icon={MapPin} label="Address" value={focused.address ? 'Provided' : 'Missing'} /><OpsRow icon={CheckCircle2} label="Compliance record" value={focused.compliance_reference ? 'Provided' : 'Missing'} /><div className="mt-3 flex items-center justify-between text-xs"><span>Completion</span><strong>{profileCompleteness(focused)}%</strong></div><div className="ops-progress mt-1"><span style={{ width: `${profileCompleteness(focused)}%` }} /></div>{allowed ? <Button className="mt-3 w-full" variant="secondary" size="sm" onClick={() => setOpen(focused)}>Complete profile</Button> : null}</div></section></> : <section className="ops-panel"><div className="ops-panel-body text-xs text-muted">Select a supplier to review performance.</div></section>}</aside>
      </div>
      <SupplierModal key={open && open !== true ? open.id : open ? 'new' : 'closed'} open={!!open} supplier={open === true ? null : open} onClose={() => setOpen(null)} />
    </div>
  );
}

function OpsKpi({ icon: Icon, label, value, tone = '' }: { icon: typeof Users; label: string; value: ReactNode; tone?: string }) { return <div className={`ops-kpi ${tone}`}><div className="ops-kpi-icon"><Icon /></div><div><p>{label}</p><strong>{value}</strong></div></div>; }
function OpsRow({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: ReactNode }) { return <div className="ops-stat-row"><Icon /><span>{label}</span><strong>{value}</strong></div>; }

function getSupplierMetrics(supplier: Supplier | null, orders: Awaited<ReturnType<typeof api.purchaseOrders>>['results'], grns: Awaited<ReturnType<typeof api.goodsReceivedNotes>>['results']) {
  if (!supplier) return { orders: 0, openOrders: 0, deliveries: 0, onTime: null as number | null, quality: null as number | null, orderValue: 0 };
  const supplierOrders = orders.filter((order) => order.supplier === supplier.id);
  const received = supplierOrders.filter((order) => order.status === 'RECEIVED');
  const dated = received.filter((order) => order.received_at && (order.revised_delivery_date || order.expected_delivery_date));
  const onTime = dated.filter((order) => new Date(order.received_at!).getTime() <= new Date(order.revised_delivery_date || order.expected_delivery_date!).setHours(23,59,59,999));
  const orderIds = new Set(supplierOrders.map((order) => order.id));
  const receiptLines = grns.filter((grn) => orderIds.has(grn.purchase_order) && grn.status === 'ACCEPTED').flatMap((grn) => grn.items);
  const accepted = receiptLines.reduce((total, line) => total + Number(line.accepted_quantity), 0);
  const inspected = receiptLines.reduce((total, line) => total + Number(line.accepted_quantity) + Number(line.rejected_quantity) + Number(line.damaged_quantity), 0);
  return { orders: supplierOrders.length, openOrders: supplierOrders.filter((order) => !['RECEIVED','CANCELLED'].includes(order.status)).length, deliveries: received.length, onTime: dated.length ? Math.round(onTime.length / dated.length * 100) : null, quality: inspected ? Math.round(accepted / inspected * 100) : null, orderValue: supplierOrders.reduce((total, order) => total + Number(order.total_cost), 0) };
}
function profileCompleteness(supplier: Supplier) { return Math.round([supplier.phone, supplier.email, supplier.address, supplier.compliance_reference].filter(Boolean).length / 4 * 100); }
function exportSuppliers(suppliers: Supplier[]) { const rows = [['Supplier','Contact','Phone','Email','Rating','Status'], ...suppliers.map((supplier) => [supplier.name, supplier.contact_person, supplier.phone, supplier.email, String(supplier.rating), supplier.is_active ? 'Active' : 'Inactive'])]; const csv = rows.map((row) => row.map((cell) => `"${String(cell || '').replace(/"/g, '""')}"`).join(',')).join('\n'); const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'supplier-directory.csv'; anchor.click(); URL.revokeObjectURL(url); }

function SupplierModal({ open, supplier, onClose }: { open: boolean; supplier: Supplier | null; onClose: () => void }) {
  const [form, setForm] = useState({ name: supplier?.name || '', contact_person: supplier?.contact_person || '', phone: supplier?.phone || '', email: supplier?.email || '', address: supplier?.address || '', rating: String(supplier?.rating || 3), lead_time_days: String(supplier?.lead_time_days || 0), is_preferred: supplier?.is_preferred || false, compliance_reference: supplier?.compliance_reference || '', compliance_expiry_date: supplier?.compliance_expiry_date || '', notes: supplier?.notes || '' });
  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const queryClient = useQueryClient();
  const toast = useToast();
  const mutation = useMutation({
    mutationFn: () => api.saveSupplier({
      ...form,
      rating: Number(form.rating), lead_time_days: Number(form.lead_time_days), compliance_expiry_date: form.compliance_expiry_date || null,
    } as Partial<Supplier>, supplier?.id),
    onSuccess: () => {
      toast.push({ title: 'Supplier saved', tone: 'success' });
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    },
    onError: (error: Error) => toast.push({ title: 'Could not save supplier', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title={supplier ? `Edit ${supplier.name}` : 'Register supplier'} onClose={onClose}>
      <form className="grid gap-3 md:grid-cols-2" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
        <Field label="Supplier name" required><input className={inputClass} value={form.name} onChange={(event) => set('name', event.target.value)} /></Field>
        <Field label="Contact person"><input className={inputClass} value={form.contact_person} onChange={(event) => set('contact_person', event.target.value)} /></Field>
        <Field label="Phone"><input className={inputClass} value={form.phone} onChange={(event) => set('phone', event.target.value)} /></Field>
        <Field label="Email"><input className={inputClass} type="email" value={form.email} onChange={(event) => set('email', event.target.value)} /></Field>
        <Field label="Rating"><input className={inputClass} type="number" min="1" max="5" value={form.rating} onChange={(event) => set('rating', event.target.value)} /></Field>
        <Field label="Lead time (days)"><input className={inputClass} type="number" min="0" value={form.lead_time_days} onChange={(event) => set('lead_time_days', event.target.value)} /></Field>
        <Field label="Address"><input className={inputClass} value={form.address} onChange={(event) => set('address', event.target.value)} /></Field>
        <Field label="Compliance reference"><input className={inputClass} value={form.compliance_reference} onChange={(event) => set('compliance_reference', event.target.value)} /></Field>
        <Field label="Compliance expiry"><input className={inputClass} type="date" value={form.compliance_expiry_date} onChange={(event) => set('compliance_expiry_date', event.target.value)} /></Field>
        <label className="flex items-center gap-2 self-end rounded-md border border-border p-2.5 text-sm font-semibold"><input type="checkbox" checked={form.is_preferred} onChange={(event) => setForm((current) => ({ ...current, is_preferred: event.target.checked }))} />Preferred supplier</label>
        <Field label="Notes" className="md:col-span-2"><textarea className={inputClass} value={form.notes} onChange={(event) => set('notes', event.target.value)} /></Field>
        <Button className="md:col-span-2" disabled={!form.name || mutation.isPending}>{supplier ? 'Save changes' : 'Save supplier'}</Button>
      </form>
    </FormModal>
  );
}
