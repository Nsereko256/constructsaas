import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DashboardData } from '@/api/types';
import { connectSocket } from '@/api/ws';
import { AlertTriangle, Boxes, CalendarDays, ChevronRight, ClipboardCheck, ClipboardList, Clock3, FolderKanban, Gauge, PackageCheck, ReceiptText, TrendingUp, Truck, Wallet } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { Role, WorkflowBadges } from '@/api/types';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatUGX } from '@/lib/utils';
import { mergeDashboardUpdate, normalizeDashboardData } from '@/lib/dashboard';
import { useAuth } from '@/auth/auth-context';

const roleIntro = {
  admin: 'Portfolio control across projects, procurement, inventory and teams.',
  project_manager: 'Project delivery, approvals, budget health and site signals.',
  procurement_officer: 'Supplier ordering, purchase requests and dispatch control.',
  storekeeper: 'Warehouse stock, low-stock warnings and material movement workload.',
  site_engineer: 'Site requests, direct deliveries, messages and assigned project work.',
  finance_officer: 'Financial preparation, matching, payment allocation and expense control.',
  finance_manager: 'Approval governance, posting, reversals and company financial oversight.',
  finance_viewer: 'Read-only visibility across budgets, payables, costs and finance reports.',
};

const roleWorkspace: Record<Role, { title: string; queueHeading?: string; readOnlyQueue?: boolean; queue: Array<{ label: string; badge: keyof WorkflowBadges; href: string; empty: string }> }> = {
  site_engineer: { title: 'My site today', queue: [{ label: 'Direct deliveries to receive', badge: 'deliveries', href: '/procurement/deliveries', empty: 'No dispatched site deliveries require a GRN.' }, { label: 'Request follow-ups', badge: 'requests', href: '/procurement/requests', empty: 'No request follow-ups are waiting.' }] },
  storekeeper: { title: 'Warehouse control queue', queue: [{ label: 'Warehouse deliveries to receive', badge: 'deliveries', href: '/procurement/deliveries', empty: 'No warehouse deliveries are awaiting receipt.' }, { label: 'Low-stock materials', badge: 'inventory', href: '/inventory', empty: 'No low-stock materials need action.' }, { label: 'Stock issue requests', badge: 'requests', href: '/procurement/requests', empty: 'No approved stock issues are waiting.' }] },
  project_manager: { title: 'Project decision queue', queue: [{ label: 'Requests awaiting manager approval', badge: 'requests', href: '/procurement/requests', empty: 'No project requests are awaiting your approval.' }, { label: 'Budgets requiring attention', badge: 'budgets', href: '/finance/budgets', empty: 'No budget actions are waiting.' }] },
  procurement_officer: { title: 'Buying queue', queue: [{ label: 'Manager-approved requests to quote', badge: 'requests', href: '/procurement/requests', empty: 'No manager-approved requests are waiting for supplier pricing.' }, { label: 'Purchase orders to progress', badge: 'purchase_orders', href: '/procurement/purchase-orders', empty: 'No purchase orders need supplier follow-up or receipt coordination.' }, { label: 'Supplier invoice handoffs', badge: 'supplier_invoices', href: '/finance/payables', empty: 'No supplier invoice handoffs need attention.' }] },
  finance_officer: { title: 'Finance preparation queue', queue: [{ label: 'Quoted POs to prepare for Finance review', badge: 'requests', href: '/procurement/requests', empty: 'No quoted purchase orders need Finance preparation.' }, { label: 'Supplier invoices to prepare', badge: 'supplier_invoices', href: '/finance/payables', empty: 'No supplier invoices need preparation.' }, { label: 'Payment drafts', badge: 'payments', href: '/finance/payments', empty: 'No payment drafts need attention.' }] },
  finance_manager: { title: 'Finance decision queue', queue: [{ label: 'Quoted POs awaiting Finance decision', badge: 'requests', href: '/procurement/requests', empty: 'No quoted purchase orders need a Finance decision.' }, { label: 'Invoices requiring authorization', badge: 'supplier_invoices', href: '/finance/payables', empty: 'No supplier invoices need authorization.' }, { label: 'Payments requiring approval or posting', badge: 'payments', href: '/finance/payments', empty: 'No supplier payments need action.' }, { label: 'Draft journals', badge: 'ledger', href: '/finance/ledger', empty: 'No draft journals need action.' }] },
  finance_viewer: { title: 'Financial oversight', queueHeading: 'Monitoring signals', readOnlyQueue: true, queue: [{ label: 'Finance items in progress', badge: 'supplier_invoices', href: '/finance/payables', empty: 'No supplier invoice exceptions are open.' }, { label: 'Budget approvals in progress', badge: 'budgets', href: '/finance/budgets', empty: 'No budget approvals are in progress.' }] },
  admin: { title: 'Company control queue', queue: [{ label: 'Requests awaiting action', badge: 'requests', href: '/procurement/requests', empty: 'No purchase requests are waiting.' }, { label: 'Purchase orders awaiting action', badge: 'purchase_orders', href: '/procurement/purchase-orders', empty: 'No purchase orders are waiting.' }, { label: 'Finance approvals in progress', badge: 'supplier_invoices', href: '/finance/payables', empty: 'No supplier invoice approvals are waiting.' }, { label: 'Draft journals', badge: 'ledger', href: '/finance/ledger', empty: 'No draft journals are waiting.' }] },
};

export function DashboardPage() {
  const { role, user } = useAuth();
  const queryClient = useQueryClient();
  const dashboard = useQuery({ queryKey: qk.dashboard, queryFn: api.dashboard });
  const workflow = useQuery({ queryKey: qk.workflowBadges, queryFn: api.workflowBadges });

  useEffect(() => {
    const socket = connectSocket<{ type?: string; payload?: Partial<DashboardData> }>({
      path: '/ws/dashboard/',
      onMessage: (payload) => {
        if (payload.type === 'dashboard.update' && payload.payload) {
          queryClient.setQueryData<DashboardData>(
            qk.dashboard,
            (current) => mergeDashboardUpdate(current, payload.payload || {}),
          );
        }
      },
    });
    return () => socket.close();
  }, [queryClient]);

  if (dashboard.isLoading) return <Skeleton className="h-[540px]" />;
  if (dashboard.isError || !dashboard.data) throw dashboard.error;

  const data = normalizeDashboardData(dashboard.data);
  const workspace = role ? roleWorkspace[role] : roleWorkspace.admin;
  const primaryAction: Record<Role, { label: string; href: string }> = {
    admin: { label: 'Open action queue', href: '/procurement/requests' },
    project_manager: { label: 'Review approvals', href: '/procurement/requests?action_queue=my_requests' },
    procurement_officer: { label: 'Open buying queue', href: '/procurement/requests?action_queue=my_requests' },
    storekeeper: { label: 'Receive deliveries', href: '/procurement/deliveries?action_queue=warehouse_receipts' },
    site_engineer: { label: 'Update site work', href: '/work-orders/progress' },
    finance_officer: { label: 'Prepare finance review', href: '/finance/payables' },
    finance_manager: { label: 'Review finance approvals', href: '/finance/payables' },
    finance_viewer: { label: 'View finance position', href: '/finance' },
  };
  const isFieldRole = role === 'site_engineer' || role === 'storekeeper';
  const isFinanceRole = role?.startsWith('finance_');
  const kpis = isFieldRole ? [
    { label: 'Assigned projects', value: data.active_projects, icon: FolderKanban },
    { label: role === 'storekeeper' ? 'Low-stock alerts' : 'Open requests', value: role === 'storekeeper' ? data.low_stock_count : data.pending_purchase_requests, icon: role === 'storekeeper' ? AlertTriangle : ClipboardList },
    { label: 'Actions due', value: workflow.data?.[role === 'storekeeper' ? 'deliveries' : 'requests'] || 0, icon: role === 'storekeeper' ? ReceiptText : ClipboardCheck },
  ] : isFinanceRole ? [
    { label: 'Projects monitored', value: data.active_projects, icon: FolderKanban },
    { label: 'Requests in flow', value: data.pending_purchase_requests, icon: ClipboardList },
    { label: 'Invoice actions', value: workflow.data?.supplier_invoices || 0, icon: ReceiptText },
    { label: 'Payment actions', value: workflow.data?.payments || 0, icon: Wallet },
  ] : [
    { label: 'Active projects', value: data.active_projects, icon: FolderKanban },
    { label: 'Requests awaiting flow', value: data.pending_purchase_requests, icon: ClipboardList },
    { label: 'PO actions', value: workflow.data?.purchase_orders || 0, icon: PackageCheck },
    { label: 'Low-stock alerts', value: data.low_stock_count, icon: AlertTriangle },
  ];
  const budgetRows = data.project_budget_vs_actual.slice(0, 6).map((project) => {
    const budget = Number(project.budget || 0);
    const used = Number(project.actual_expenditure || 0) + Number(project.open_commitments || 0);
    return { ...project, used, utilization: budget ? Math.min(100, Math.round((used / budget) * 100)) : 0, atRisk: budget > 0 && used > budget };
  });
  const totalBudget = data.project_budget_vs_actual.reduce((total, project) => total + Number(project.budget || 0), 0);
  const totalUsed = data.project_budget_vs_actual.reduce((total, project) => total + Number(project.actual_expenditure || 0) + Number(project.open_commitments || 0), 0);
  const budgetChart = [{ name: 'Used', value: Math.min(totalUsed, totalBudget) }, { name: 'Available', value: Math.max(totalBudget - totalUsed, 0) }].filter((item) => item.value > 0);
  const inventoryChart = [{ name: 'Healthy', value: Math.max(data.total_active_materials - data.low_stock_count, 0) }, { name: 'Low stock', value: data.low_stock_count }].filter((item) => item.value > 0);
  const pipeline = [
    { label: 'Requests', count: data.pending_purchase_requests, href: '/procurement/requests', tone: 'warning', icon: ClipboardList },
    { label: 'POs', count: workflow.data?.purchase_orders || 0, href: '/procurement/purchase-orders', tone: 'info', icon: PackageCheck },
    { label: 'Deliveries', count: workflow.data?.deliveries || 0, href: '/procurement/deliveries', tone: 'info', icon: Truck },
    { label: 'Stock', count: data.low_stock_count, href: '/inventory', tone: 'critical', icon: Boxes },
    { label: 'Invoices', count: workflow.data?.supplier_invoices || 0, href: '/finance/payables', tone: 'success', icon: ReceiptText },
    { label: 'Payments', count: workflow.data?.payments || 0, href: '/finance/payments', tone: 'success', icon: Wallet },
  ] as const;
  const attentionItems = [
    { label: 'Requests awaiting approval', detail: 'Purchase requests', count: workflow.data?.requests || 0, href: '/procurement/requests', tone: 'warning', icon: ClipboardList },
    { label: 'Purchase orders to progress', detail: 'Supplier follow-up', count: workflow.data?.purchase_orders || 0, href: '/procurement/purchase-orders', tone: 'warning', icon: PackageCheck },
    { label: 'Deliveries to receive', detail: 'Warehouse and site receipts', count: workflow.data?.deliveries || 0, href: '/procurement/deliveries', tone: 'info', icon: Truck },
    { label: 'Low-stock materials', detail: 'Inventory alert', count: data.low_stock_count, href: '/inventory', tone: 'critical', icon: AlertTriangle },
  ] as const;

  return (
    <div className="grid gap-3 sm:gap-5">
      <section className="overflow-hidden rounded-2xl border border-border bg-white px-4 py-4 shadow-panel sm:px-6 sm:py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">ConstructSaaS</p><h2 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">Good day, {user?.first_name || user?.username || 'there'}</h2><p className="mt-1 max-w-2xl text-sm text-muted">{role ? roleIntro[role] : roleIntro.admin}</p></div>
          <div className="flex flex-wrap items-center justify-end gap-2"><div className="flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-2 text-xs font-semibold text-muted"><CalendarDays className="h-4 w-4 text-primary" />{new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date())}</div><Link className="rounded-xl bg-primary px-3 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-primary/90" to={(role && primaryAction[role] ? primaryAction[role] : primaryAction.admin).href}>{(role && primaryAction[role] ? primaryAction[role] : primaryAction.admin).label}</Link></div>
        </div>
      </section>
      <section className="grid grid-cols-2 gap-2 sm:gap-3 xl:grid-cols-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label} className="border-border bg-white">
            <CardContent className="flex items-center gap-3 p-3 sm:p-4"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary sm:h-12 sm:w-12"><kpi.icon className="h-5 w-5" /></span><div className="min-w-0"><p className="truncate text-[10px] font-bold uppercase tracking-wide text-muted sm:text-xs">{kpi.label}</p><strong className="block text-xl font-black sm:text-2xl">{kpi.value}</strong><span className="text-[11px] text-muted">Live position</span></div></CardContent>
          </Card>
        ))}
      </section>
      <section className="grid gap-3 sm:gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader><div className="flex items-center justify-between gap-3"><div><CardTitle>Projects overview</CardTitle><p className="mt-1 text-xs text-muted">Planned budget versus current committed and actual spend.</p></div><Link className="inline-flex items-center text-xs font-bold text-primary hover:underline" to="/projects">View all <ChevronRight className="h-3.5 w-3.5" /></Link></div></CardHeader>
          <CardContent className="grid gap-4 p-3 sm:p-4 lg:grid-cols-[1fr_190px]">
            <div className="grid gap-3">
            {budgetRows.map((project) => <div key={project.id}><div className="flex items-center justify-between gap-3 text-sm"><span className="min-w-0 truncate"><strong>{project.name}</strong><span className="ml-2 text-xs text-muted">{project.code}</span></span><span className={`shrink-0 text-xs font-bold ${project.atRisk ? 'text-critical' : 'text-primary'}`}>{project.atRisk ? 'Over budget' : `${project.utilization}%`}</span></div><div className="relative mt-1.5 h-2 overflow-hidden rounded-full bg-muted/60"><div className="absolute inset-y-0 left-0 rounded-full bg-primary/20" style={{ width: '100%' }} /><div className={`relative h-full rounded-full ${project.atRisk ? 'bg-critical' : project.utilization > 80 ? 'bg-warning' : 'bg-primary'}`} style={{ width: `${project.utilization}%` }} /></div><p className="mt-1 text-[11px] text-muted">Available {formatUGX(project.remaining_budget)} · Actual {formatUGX(project.actual_expenditure)}</p></div>)}
            {!budgetRows.length ? <div className="rounded-xl border border-dashed border-border bg-background p-5 text-center"><Gauge className="mx-auto h-6 w-6 text-muted" /><strong className="mt-2 block text-sm">No approved project budgets yet</strong><p className="mt-1 text-xs text-muted">Create and approve a project budget to see portfolio health here.</p><Link className="mt-3 inline-block text-xs font-bold text-primary hover:underline" to="/finance/budgets">Open Finance budgets</Link></div> : null}
            </div>
            {budgetChart.length ? <DonutChart title="Budget position" data={budgetChart} colors={['#2878D0', '#087A3E']} center={formatUGX(Math.max(totalBudget - totalUsed, 0).toString())} /> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><div className="flex items-center justify-between"><CardTitle>Attention required</CardTitle><Link className="inline-flex items-center text-xs font-bold text-primary hover:underline" to={workspace.queue[0]?.href || '/procurement/requests'}>View all <ChevronRight className="h-3.5 w-3.5" /></Link></div></CardHeader>
          <CardContent className="grid gap-1 p-2.5 sm:p-4">
            {attentionItems.map((item) => <Link key={item.label} to={item.href} className="group flex items-center gap-2 border-b border-border px-1 py-2.5 last:border-0 hover:bg-primary/[0.035] sm:gap-3"><span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${item.tone === 'critical' ? 'bg-critical/10 text-critical' : item.tone === 'info' ? 'bg-info/10 text-info' : 'bg-warning/10 text-warning'}`}><item.icon className="h-4 w-4" /></span><span className="min-w-0 flex-1"><strong className="block truncate text-xs sm:text-sm">{item.label}</strong><span className="block truncate text-[11px] text-muted">{item.detail}</span></span><Badge tone={item.count ? item.tone === 'critical' ? 'danger' : 'warning' : 'success'}>{item.count || 'Clear'}</Badge><ChevronRight className="h-4 w-4 shrink-0 text-muted group-hover:text-primary" /></Link>)}
          </CardContent>
        </Card>
      </section>
      <Card>
        <CardHeader><CardTitle>Procurement pipeline</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3 sm:gap-3 lg:grid-cols-6 sm:p-4">
          {pipeline.map((item, index) => <Link key={item.label} to={item.href} className="group relative rounded-xl border border-border bg-white p-2.5 transition hover:border-primary/40 hover:shadow-sm sm:p-3"><span className={`grid h-8 w-8 place-items-center rounded-full ${item.tone === 'critical' ? 'bg-critical/10 text-critical' : item.tone === 'success' ? 'bg-success/10 text-success' : item.tone === 'warning' ? 'bg-warning/10 text-warning' : 'bg-info/10 text-info'}`}><item.icon className="h-4 w-4" /></span><span className="mt-2 block text-[10px] font-bold uppercase tracking-wide text-muted">{item.label}</span><strong className="mt-0.5 block text-xl font-black">{item.count}</strong><span className={`text-[11px] ${item.count ? item.tone === 'critical' ? 'text-critical' : item.tone === 'success' ? 'text-success' : 'text-warning' : 'text-muted'}`}>{item.count ? 'Needs attention' : 'All clear'}</span>{index < pipeline.length - 1 ? <ChevronRight className="absolute -right-3 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-muted lg:block" /> : null}</Link>)}
        </CardContent>
      </Card>
      <section className="grid gap-3 sm:gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader><div className="flex items-center justify-between"><CardTitle>Recent activity</CardTitle><Link className="inline-flex items-center text-xs font-bold text-primary hover:underline" to="/notifications">View all <ChevronRight className="h-3.5 w-3.5" /></Link></div></CardHeader>
          <CardContent className="grid gap-1 p-3 sm:p-4">
            {data.recent_stock_movements.slice(0, 5).map((movement) => <Link key={movement.id} to="/inventory/movements" className="flex items-center gap-3 border-b border-border py-2 last:border-0"><span className="grid h-8 w-8 place-items-center rounded-full bg-primary/10 text-primary"><Clock3 className="h-4 w-4" /></span><span className="min-w-0 flex-1"><strong className="block truncate text-xs sm:text-sm">{movement.material.name} {movement.source_display ? `· ${movement.source_display}` : ''}</strong><span className="block truncate text-[11px] text-muted">{movement.quantity} · {movement.notes || 'Stock movement recorded'}</span></span><span className="shrink-0 text-[11px] text-muted">{movement.date ? new Date(movement.date).toLocaleDateString() : 'Recent'}</span></Link>)}
            {!data.recent_stock_movements.length ? <div className="py-8 text-center text-sm text-muted">No recent activity to show.</div> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><div className="flex items-center justify-between"><CardTitle>Inventory health</CardTitle><Link className="inline-flex items-center text-xs font-bold text-primary hover:underline" to="/inventory">View all <ChevronRight className="h-3.5 w-3.5" /></Link></div></CardHeader>
          <CardContent className="grid gap-4 p-3 sm:grid-cols-[180px_1fr] sm:p-4"><div className="grid place-items-center">{inventoryChart.length ? <DonutChart title="Current stock position" data={inventoryChart} colors={['#087A3E', '#D58B00']} center={`${Math.max(data.total_active_materials - data.low_stock_count, 0)}`} /> : <div className="text-center text-sm text-muted">No inventory data.</div>}</div><div className="grid content-center gap-3 text-xs">{[['Healthy (OK)', Math.max(data.total_active_materials - data.low_stock_count, 0), '#087A3E'], ['Low stock', data.low_stock_count, '#D58B00']].map(([label, value, color]) => <div key={String(label)}><div className="flex items-center justify-between gap-2"><span className="inline-flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: String(color) }} />{label}</span><strong>{value} items</strong></div><div className="mt-1 h-1.5 rounded-full bg-muted"><div className="h-full rounded-full" style={{ backgroundColor: String(color), width: `${data.total_active_materials ? Math.min(100, Number(value) / data.total_active_materials * 100) : 0}%` }} /></div></div>)}</div></CardContent>
        </Card>
      </section>
    </div>
  );
}

function DonutChart({ title, data, colors, center }: { title: string; data: Array<{ name: string; value: number }>; colors: string[]; center: string }) {
  return <div className="min-w-0"><p className="text-center text-[10px] font-bold uppercase tracking-wide text-muted">{title}</p><div className="relative mx-auto mt-1 h-36 w-full max-w-[180px]"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} dataKey="value" nameKey="name" innerRadius={42} outerRadius={62} paddingAngle={3} stroke="none"><Cell fill={colors[0]} /><Cell fill={colors[1]} /></Pie><Tooltip formatter={(value) => Number(value).toLocaleString()} /></PieChart></ResponsiveContainer><div className="pointer-events-none absolute inset-0 grid place-items-center px-5 text-center text-xs font-black leading-tight">{center}</div></div><div className="flex justify-center gap-3 text-[10px] text-muted">{data.map((item, index) => <span key={item.name} className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ backgroundColor: colors[index] }} />{item.name}</span>)}</div></div>;
}
