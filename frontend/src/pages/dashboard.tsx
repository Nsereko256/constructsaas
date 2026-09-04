import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DashboardData } from '@/api/types';
import { connectSocket } from '@/api/ws';
import { AlertTriangle, ArrowRight, Boxes, CalendarDays, CheckCircle2, ClipboardCheck, ClipboardList, CircleDollarSign, FolderKanban, Gauge, PackageCheck, ReceiptText, ShieldAlert, TrendingUp, Wallet, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { Role, WorkflowBadges } from '@/api/types';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import { Badge, statusTone } from '@/components/ui/badge';
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
  const queueIcons: Partial<Record<keyof WorkflowBadges, LucideIcon>> = { requests: ClipboardList, deliveries: ReceiptText, inventory: Boxes, purchase_orders: PackageCheck, supplier_invoices: ReceiptText, payments: Wallet, ledger: ClipboardCheck, budgets: TrendingUp };
  const priorityCount = workspace.queue.reduce((total, item) => total + (workflow.data?.[item.badge] || 0), 0);
  const budgetRows = data.project_budget_vs_actual.slice(0, 6).map((project) => {
    const budget = Number(project.budget || 0);
    const used = Number(project.actual_expenditure || 0) + Number(project.open_commitments || 0);
    return { ...project, used, utilization: budget ? Math.min(100, Math.round((used / budget) * 100)) : 0, atRisk: budget > 0 && used > budget };
  });
  const totalBudget = data.project_budget_vs_actual.reduce((total, project) => total + Number(project.budget || 0), 0);
  const totalUsed = data.project_budget_vs_actual.reduce((total, project) => total + Number(project.actual_expenditure || 0) + Number(project.open_commitments || 0), 0);
  const budgetChart = [{ name: 'Used', value: Math.min(totalUsed, totalBudget) }, { name: 'Available', value: Math.max(totalBudget - totalUsed, 0) }].filter((item) => item.value > 0);
  const inventoryChart = [{ name: 'Healthy', value: Math.max(data.total_active_materials - data.low_stock_count, 0) }, { name: 'Low stock', value: data.low_stock_count }].filter((item) => item.value > 0);
  const pipeline: Array<{ label: string; count: number; href: string; icon: LucideIcon }> = [
    { label: 'Requests', count: workflow.data?.requests || 0, href: '/procurement/requests', icon: ClipboardList }, { label: 'POs', count: workflow.data?.purchase_orders || 0, href: '/procurement/purchase-orders', icon: PackageCheck }, { label: 'Deliveries', count: workflow.data?.deliveries || 0, href: '/procurement/deliveries', icon: ReceiptText }, { label: 'Stock alerts', count: workflow.data?.inventory || 0, href: '/inventory', icon: Boxes }, { label: 'Invoices', count: workflow.data?.supplier_invoices || 0, href: '/finance/payables', icon: CircleDollarSign }, { label: 'Payments', count: workflow.data?.payments || 0, href: '/finance/payments', icon: Wallet },
  ];

  return (
    <div className="grid gap-2.5 sm:gap-5">
      <section className="app-sheen overflow-hidden rounded-2xl border border-primary/15 bg-white px-4 py-4 shadow-panel sm:px-6 sm:py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Company command centre</p><h2 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">Good day, {user?.first_name || user?.username || 'there'}</h2><p className="mt-1 max-w-2xl text-sm text-muted sm:text-base">{role ? roleIntro[role] : roleIntro.admin}</p></div>
          <div className="flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-2 text-xs font-semibold text-muted"><CalendarDays className="h-4 w-4 text-primary" />{new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date())}</div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3"><div className={`flex items-center gap-2 rounded-xl border p-3 ${priorityCount ? 'border-warning/30 bg-warning/5' : 'border-success/25 bg-success/5'}`}><span className={`grid h-8 w-8 place-items-center rounded-lg ${priorityCount ? 'bg-warning/15 text-warning' : 'bg-success/15 text-success'}`}>{priorityCount ? <ShieldAlert className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}</span><span><strong className="block text-sm">{priorityCount ? `${priorityCount} action${priorityCount === 1 ? '' : 's'} need attention` : 'Operations are clear'}</strong><span className="text-xs text-muted">Your role-based queue</span></span></div><div className="flex items-center gap-2 rounded-xl border border-border bg-background p-3"><span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary"><Gauge className="h-4 w-4" /></span><span><strong className="block text-sm">{data.active_projects} active project{data.active_projects === 1 ? '' : 's'}</strong><span className="text-xs text-muted">Across the company</span></span></div><div className="flex items-center gap-2 rounded-xl border border-border bg-background p-3"><span className="grid h-8 w-8 place-items-center rounded-lg bg-info/10 text-info"><CircleDollarSign className="h-4 w-4" /></span><span><strong className="block text-sm">{data.low_stock_count ? `${data.low_stock_count} stock alerts` : 'Stock position healthy'}</strong><span className="text-xs text-muted">Inventory signal</span></span></div></div>
      </section>
      <section className="grid grid-cols-2 gap-2 sm:gap-3 xl:grid-cols-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label}>
            <CardContent className="p-2.5 sm:p-4">
              <div className="flex items-center justify-between"><kpi.icon className="h-4 w-4 text-primary sm:h-5 sm:w-5" /><span className="hidden text-xs font-bold uppercase tracking-wide text-muted sm:inline">Live</span></div>
              <p className="mt-2 text-[10px] font-bold uppercase leading-3 tracking-wide text-muted sm:mt-3 sm:text-xs">{kpi.label}</p>
              <strong className="mt-0.5 block text-lg font-black sm:mt-1 sm:text-2xl">{kpi.value}</strong>
            </CardContent>
          </Card>
        ))}
      </section>
      <section aria-label="Operations pipeline" className="rounded-2xl border border-border bg-white p-3 shadow-panel sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-[10px] font-black uppercase tracking-[0.14em] text-primary">End-to-end control</p><h3 className="mt-0.5 text-base font-black">Operations pipeline</h3></div><Link className="text-xs font-bold text-primary hover:underline" to="/procurement">Open Procurement</Link></div>
        <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">{pipeline.map(({ label, count, href, icon: Icon }, index) => <Link key={label} to={href} className={`group relative overflow-hidden rounded-2xl border p-3.5 transition-all hover:-translate-y-0.5 hover:shadow-lift ${count ? 'border-[#D89B24] bg-[#FFF8E6] hover:border-[#A96F00]' : 'border-[#7FB995] bg-[#F2FAF5] hover:border-[#2E8B57]'}`}><span className={`absolute inset-x-0 top-0 h-1 ${count ? 'bg-[#D89B24]' : 'bg-[#2E8B57]'}`} /><div className="flex items-start justify-between gap-2"><span className={`grid h-8 w-8 place-items-center rounded-xl ${count ? 'bg-[#FFE6A6] text-[#6B4300]' : 'bg-[#D8F0E1] text-[#17663A]'}`}><Icon className="h-4 w-4" /></span><span className="text-[10px] font-black text-[#52615A]">0{index + 1}</span></div><p className="mt-3 text-[10px] font-black uppercase tracking-[0.1em] text-[#52615A]">{label}</p><strong className="mt-0.5 block text-2xl font-black tracking-tight text-[#17231C]">{count}</strong><span className={`mt-2 inline-flex rounded-full px-2 py-1 text-[10px] font-bold ${count ? 'bg-[#FFE6A6] text-[#6B4300]' : 'bg-[#D8F0E1] text-[#17663A]'}`}>{count ? 'Needs attention' : 'All clear'}</span>{index < 5 ? <span className="absolute -right-1.5 top-1/2 z-10 hidden h-3 w-3 -translate-y-1/2 rotate-45 border-r border-t border-[#B7C8BC] bg-[#F7FBF8] lg:block" /> : null}</Link>)}
        </div>
      </section>
      <section className="grid gap-3 sm:gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <Card>
          <CardHeader><div className="flex items-center justify-between gap-3"><div><CardTitle>Portfolio health</CardTitle><p className="mt-1 text-xs text-muted">Committed and actual spend against approved project budgets.</p></div><Link className="text-xs font-bold text-primary hover:underline" to="/projects">View projects</Link></div></CardHeader>
          <CardContent className="grid gap-4 p-3 sm:p-4 lg:grid-cols-[1fr_190px]">
            <div className="grid gap-3">
            {budgetRows.map((project) => <div key={project.id}><div className="flex items-center justify-between gap-3 text-sm"><span className="min-w-0 truncate"><strong>{project.code}</strong><span className="ml-2 text-muted">{project.name}</span></span><span className={`shrink-0 font-bold ${project.atRisk ? 'text-critical' : 'text-primary'}`}>{project.atRisk ? 'Over budget' : `${project.utilization}% used`}</span></div><div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted"><div className={`h-full rounded-full ${project.atRisk ? 'bg-critical' : project.utilization > 80 ? 'bg-warning' : 'bg-primary'}`} style={{ width: `${project.utilization}%` }} /></div><p className="mt-1 text-[11px] text-muted">Actual {formatUGX(project.actual_expenditure)} · Committed {formatUGX(project.open_commitments)} · Available {formatUGX(project.remaining_budget)}</p></div>)}
            {!budgetRows.length ? <div className="rounded-xl border border-dashed border-border bg-background p-5 text-center"><Gauge className="mx-auto h-6 w-6 text-muted" /><strong className="mt-2 block text-sm">No approved project budgets yet</strong><p className="mt-1 text-xs text-muted">Create and approve a project budget to see portfolio health here.</p><Link className="mt-3 inline-block text-xs font-bold text-primary hover:underline" to="/finance/budgets">Open Finance budgets</Link></div> : null}
            </div>
            {budgetChart.length ? <DonutChart title="Budget position" data={budgetChart} colors={['#2878D0', '#087A3E']} center={formatUGX(Math.max(totalBudget - totalUsed, 0).toString())} /> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>{isFieldRole ? (role === 'storekeeper' ? 'Warehouse focus' : 'Site focus') : 'Inventory alerts'}</CardTitle></CardHeader>
          <CardContent className="grid gap-4 p-3 text-sm sm:p-4 lg:grid-cols-[1fr_150px]">
            {isFieldRole ? <><div><p className="text-muted">{role === 'storekeeper' ? 'Keep receipts, stock issues and supplier exceptions current.' : 'Keep requests tied to the right project and confirm materials physically received on site.'}</p><div className="mt-3 flex items-center gap-2 rounded-xl border border-info/20 bg-info/5 p-3 text-xs"><ReceiptText className="h-4 w-4 shrink-0 text-info" />Offline actions remain on this device until they sync.</div></div></> : <div className="grid gap-2.5">{data.low_stock_materials.slice(0, 5).map((material) => <div key={material.id} className="flex items-center justify-between gap-2 border-b border-border pb-2 last:border-0"><span className="min-w-0 truncate"><strong>{material.name}</strong><span className="ml-2 text-xs text-muted">{material.code}</span></span><Badge tone="warning">Low stock</Badge></div>)}{!data.low_stock_materials.length ? <div className="rounded-xl border border-success/20 bg-success/5 p-4 text-center"><CheckCircle2 className="mx-auto h-5 w-5 text-success" /><strong className="mt-1 block text-sm">Inventory is healthy</strong><p className="mt-1 text-xs text-muted">No materials are below their minimum stock level.</p></div> : null}<Link className="text-xs font-bold text-primary hover:underline" to="/inventory">Review inventory</Link></div>}
            {!isFieldRole && inventoryChart.length ? <DonutChart title="Stock health" data={inventoryChart} colors={['#087A3E', '#D58B00']} center={String(data.total_active_materials)} /> : null}
          </CardContent>
        </Card>
      </section>
      <section className="grid gap-3 sm:gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{workspace.queueHeading || 'My next actions'}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 p-2.5 sm:gap-3 sm:p-4">
            {workspace.queue.map((item) => {
              const count = workflow.data?.[item.badge] || 0;
              const Icon = queueIcons[item.badge] || ClipboardCheck;
              return <Link key={item.label} to={item.href} className="group flex min-h-12 items-center gap-2 rounded-xl border-b border-border px-1 py-2 last:border-0 hover:bg-primary/[0.035] hover:text-primary sm:min-h-16 sm:gap-3 sm:px-2 sm:py-3">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary sm:h-10 sm:w-10"><Icon className="h-4 w-4 sm:h-5 sm:w-5" /></span>
                <div className="min-w-0 flex-1"><strong className="text-sm sm:text-base">{item.label}</strong><p className="mt-0.5 text-xs text-muted sm:text-sm">{count ? `${count} item${count === 1 ? '' : 's'} ${workspace.readOnlyQueue ? 'currently in progress.' : 'need your attention.'}` : item.empty}</p></div>
                <Badge tone={count ? 'warning' : 'success'}>{count || 'Clear'}</Badge><ArrowRight className="h-4 w-4 shrink-0 text-muted group-hover:text-primary" />
              </Link>;
            })}
          </CardContent>
        </Card>
        <Card className="hidden md:block">
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 p-2.5 sm:gap-3 sm:p-4">
            {data.recent_stock_movements.slice(0, 8).map((movement) => (
              <div key={movement.id} className="flex min-h-12 items-center justify-between gap-2 border-b border-border py-2 last:border-0 sm:min-h-14 sm:gap-3">
                <div>
                  <strong className="text-sm">{movement.material?.name || 'Material movement'}</strong>
                  <p className="text-xs text-muted sm:text-sm">{movement.project?.name || 'General stock'}</p>
                </div>
                <Badge tone={statusTone(movement.movement_type)}>{movement.movement_type_display}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
      <details className="border border-border bg-white md:hidden">
        <summary className="cursor-pointer px-3 py-2.5 text-sm font-bold text-primary">More dashboard insights</summary>
        <div className="grid gap-3 border-t border-border p-2.5">
          <div>
            <strong className="text-sm">Inventory alerts requiring attention</strong>
            <div className="mt-2 grid gap-2">
              {data.low_stock_materials.slice(0, 3).map((material) => <div key={material.id} className="flex items-center justify-between gap-2 border-b border-border pb-2"><span className="min-w-0 truncate text-sm">{material.name}</span><Badge tone="warning">Low stock</Badge></div>)}
              {!data.low_stock_materials.length ? <p className="text-sm text-muted">No urgent material alerts.</p> : null}
            </div>
          </div>
          <div>
            <strong className="text-sm">Recent activity</strong>
            <div className="mt-2 grid gap-2">
              {data.recent_stock_movements.slice(0, 4).map((movement) => <div key={movement.id} className="flex items-center justify-between gap-2 border-b border-border pb-2"><span className="min-w-0 truncate text-sm">{movement.material?.name || 'Material movement'}</span><Badge tone={statusTone(movement.movement_type)}>{movement.movement_type_display}</Badge></div>)}
              {!data.recent_stock_movements.length ? <p className="text-sm text-muted">No recent activity.</p> : null}
            </div>
          </div>
        </div>
      </details>
    </div>
  );
}

function DonutChart({ title, data, colors, center }: { title: string; data: Array<{ name: string; value: number }>; colors: string[]; center: string }) {
  return <div className="min-w-0"><p className="text-center text-[10px] font-bold uppercase tracking-wide text-muted">{title}</p><div className="relative mx-auto mt-1 h-36 w-full max-w-[180px]"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} dataKey="value" nameKey="name" innerRadius={42} outerRadius={62} paddingAngle={3} stroke="none"><Cell fill={colors[0]} /><Cell fill={colors[1]} /></Pie><Tooltip formatter={(value) => Number(value).toLocaleString()} /></PieChart></ResponsiveContainer><div className="pointer-events-none absolute inset-0 grid place-items-center px-5 text-center text-xs font-black leading-tight">{center}</div></div><div className="flex justify-center gap-3 text-[10px] text-muted">{data.map((item, index) => <span key={item.name} className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ backgroundColor: colors[index] }} />{item.name}</span>)}</div></div>;
}
