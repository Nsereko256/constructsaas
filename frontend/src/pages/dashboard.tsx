import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DashboardData } from '@/api/types';
import { connectSocket } from '@/api/ws';
import { AlertTriangle, ArrowRight, Boxes, ClipboardCheck, ClipboardList, FolderKanban, PackageCheck, ReceiptText, TrendingUp, Wallet, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Role, WorkflowBadges } from '@/api/types';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import { Badge, statusTone } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatUGX } from '@/lib/utils';
import { mergeDashboardUpdate, normalizeDashboardData } from '@/lib/dashboard';
import { useAuth } from '@/auth/auth-context';
import { ActionCentre } from '@/components/layout/action-centre';

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
  const { role } = useAuth();
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

  return (
    <div className="grid gap-2.5 sm:gap-5">
      <section className="app-sheen rounded-2xl border border-border/70 bg-white/70 px-3 py-3 shadow-sm sm:px-4 sm:py-4">
        <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-primary sm:text-sm">{role?.replace(/_/g, ' ')}</p>
        <h2 className="mt-0.5 text-xl font-black tracking-tight sm:mt-1 sm:text-2xl">{workspace.title}</h2>
        <p className="mt-1 line-clamp-2 text-sm text-muted sm:text-base">{role ? roleIntro[role] : roleIntro.admin}</p>
      </section>
      <ActionCentre role={role} workflow={workflow.data} />
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
      <section className="hidden gap-3 sm:gap-5 md:grid xl:grid-cols-[1.35fr_0.65fr]">
        {!isFieldRole ? <Card>
          <CardHeader>
            <CardTitle>Portfolio budget utilization</CardTitle>
          </CardHeader>
          <CardContent className="h-48 p-2.5 sm:h-80 sm:p-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.project_budget_vs_actual}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="code" />
                <YAxis tickFormatter={(value) => `${Number(value) / 1000000}m`} />
                <Tooltip formatter={(value) => formatUGX(String(value))} />
                <Bar dataKey="actual_expenditure" fill="#087A3E" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card> : <Card>
          <CardHeader><CardTitle>{role === 'storekeeper' ? 'Warehouse focus' : 'Site focus'}</CardTitle></CardHeader>
          <CardContent className="grid gap-2.5 p-2.5 text-sm text-muted sm:gap-3 sm:p-4">
            <p>{role === 'storekeeper' ? 'Keep receipts, stock issues and supplier exceptions current. Stock updates only after confirmed receipt.' : 'Keep requests tied to the right project and confirm only materials physically received on site.'}</p>
            <div className="flex items-center gap-2 border border-info/20 bg-info/5 p-2.5 text-xs text-foreground sm:p-3 sm:text-sm"><ReceiptText className="h-4 w-4 shrink-0 text-info sm:h-5 sm:w-5" />Offline actions remain on this device until they sync successfully.</div>
          </CardContent>
        </Card>}
        <Card>
          <CardHeader>
            <CardTitle>Inventory alerts requiring attention</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 p-2.5 sm:gap-3 sm:p-4">
            {data.low_stock_materials.slice(0, 6).map((material) => (
              <div key={material.id} className="flex items-center justify-between gap-2 border-b border-border pb-2 last:border-0 sm:gap-3 sm:pb-3">
                <div>
                  <strong className="text-sm">{material.name}</strong>
                  <p className="text-xs text-muted">{material.code}</p>
                </div>
                <Badge tone="warning">Low stock</Badge>
              </div>
            ))}
            {!data.low_stock_materials.length ? <p className="text-sm text-muted">No urgent material alerts.</p> : null}
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
