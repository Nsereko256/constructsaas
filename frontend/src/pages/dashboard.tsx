import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DashboardData, WorkflowBadges } from '@/api/types';
import { connectSocket } from '@/api/ws';
import { AlertTriangle, CalendarDays, ChevronRight, ClipboardCheck, ClipboardList, FolderKanban, PackageCheck, ReceiptText, Wallet } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { Role } from '@/api/types';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import './dashboard.css';

import { Skeleton } from '@/components/ui/skeleton';
import { formatUGX } from '@/lib/utils';
import { mergeDashboardUpdate, normalizeDashboardData } from '@/lib/dashboard';
import { useAuth } from '@/auth/auth-context';

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
          // Project progress is role-scoped and is not included in the compact
          // websocket payload. Refetch so goal/site changes update Actual now.
          void queryClient.invalidateQueries({ queryKey: qk.dashboard });
        }
      },
    });
    return () => socket.close();
  }, [queryClient]);

  const [slow, setSlow] = useState(false);
  useEffect(() => { const timer = window.setTimeout(() => setSlow(true), 10000); return () => window.clearTimeout(timer); }, []);
  if (dashboard.isLoading) return <section className="dashboard-recovery" role="status"><h1>Loading your dashboard</h1><p>{slow ? 'This is taking longer than usual. You can reload or open a workspace below.' : 'Getting your latest projects and actions…'}</p><Skeleton className="h-24" />{slow && <button onClick={() => window.location.reload()}>Reload dashboard</button>}<Link to="/projects">Open projects</Link></section>;
  if (dashboard.isError || !dashboard.data) return <section className="dashboard-recovery" role="alert"><h1>Dashboard unavailable</h1><p>We couldn’t load the latest information. Try again or continue to your workspace.</p><button onClick={() => void dashboard.refetch()} disabled={dashboard.isFetching}>{dashboard.isFetching ? 'Retrying…' : 'Try again'}</button><Link to="/projects">Open projects</Link></section>;

  const data = normalizeDashboardData(dashboard.data);
  const primaryAction: Record<Role, { label: string; href: string }> = {
    admin: { label: 'New request', href: '/procurement/requests?create=1' },
    project_manager: { label: 'Review approvals', href: '/procurement/requests?action_queue=my_requests' },
    procurement_officer: { label: 'Open buying queue', href: '/procurement/requests?action_queue=my_requests' },
    storekeeper: { label: 'Receive deliveries', href: '/procurement/deliveries?action_queue=warehouse_receipts' },
    site_engineer: { label: 'Create purchase request', href: '/procurement/requests?create=1' },
    finance_officer: { label: 'Prepare finance review', href: '/finance/payables' },
    finance_manager: { label: 'Review finance approvals', href: '/finance/payables' },
    finance_viewer: { label: 'View finance position', href: '/finance' },
  };
  const isFieldRole = role === 'site_engineer' || role === 'storekeeper';
  const financeAvailable = user?.soft_finance_enabled !== false;
  const financeRecovery = !financeAvailable && role === 'admin';
  const isFinanceRole = financeAvailable && role?.startsWith('finance_');
  const kpis = isFieldRole ? [
    { label: 'Assigned projects', value: data.active_projects, note: 'Across assigned sites', icon: FolderKanban },
    { label: role === 'storekeeper' ? 'Low-stock alerts' : 'Open requests', value: role === 'storekeeper' ? data.low_stock_count : data.pending_purchase_requests, note: 'Needs attention', icon: role === 'storekeeper' ? AlertTriangle : ClipboardList },
    { label: 'Actions due', value: workflow.data?.[role === 'storekeeper' ? 'deliveries' : 'requests'] || 0, note: 'Open workflow items', icon: role === 'storekeeper' ? ReceiptText : ClipboardCheck },
  ] : isFinanceRole ? [
    { label: 'Projects monitored', value: data.active_projects, note: 'Across selected sites', icon: FolderKanban },
    { label: 'Requests in flow', value: data.pending_purchase_requests, note: 'Awaiting review', icon: ClipboardList },
    { label: 'Invoice actions', value: workflow.data?.supplier_invoices || 0, note: 'Open workflow items', icon: ReceiptText },
    { label: 'Payment actions', value: workflow.data?.payments || 0, note: 'Open workflow items', icon: Wallet },
  ] : [
    { label: 'Active projects', value: data.active_projects, note: 'Across selected sites', icon: FolderKanban },
    { label: 'Pending approvals', value: data.pending_purchase_requests, note: 'Awaiting review', icon: ClipboardList },
    { label: 'PO actions', value: workflow.data?.purchase_orders || 0, note: 'Open workflow items', icon: PackageCheck },
    { label: 'Low-stock alerts', value: data.low_stock_count, note: 'Needs attention', icon: AlertTriangle },
  ];
  const budgetRows = data.project_budget_vs_actual.slice(0, 4).map((project) => {
    const budget = Number(project.budget || 0);
    const actualSpend = Number(project.actual_expenditure ?? project.actual_material_cost ?? 0);
    const forecastCost = actualSpend + Number(project.open_commitments || 0);
    const actualSpendPercent = budget ? Math.min(100, Math.round((actualSpend / budget) * 100)) : 0;
    return { ...project, actualSpend, forecastCost, actualSpendPercent, plannedProgress: Math.max(0, Math.min(100, Number(project.planned_progress ?? 0))), actualProgress: Math.max(0, Math.min(100, Number(project.actual_progress ?? 0))), atRisk: budget > 0 && forecastCost > budget };
  });
  const pipeline = [
    { label: 'Requests', count: workflow.data?.requests || 0, status: 'Needs attention', href: '/procurement/requests?action_queue=my_requests' },
    { label: 'POs', count: workflow.data?.purchase_orders || 0, status: 'Open', href: '/procurement/purchase-orders' },
    { label: 'Deliveries', count: workflow.data?.deliveries || 0, status: 'Needs action', href: '/procurement/deliveries' },
    { label: 'Stock', count: data.low_stock_count, status: data.low_stock_count ? 'Low stock' : 'Healthy', href: '/inventory' },
    { label: 'Invoices', count: workflow.data?.supplier_invoices || 0, status: 'All clear', href: '/finance/payables' },
    { label: 'Payments', count: workflow.data?.payments || 0, status: 'All clear', href: '/finance/payments' },
  ] as const;
  const attentionItems = [
    ...data.pending_purchase_requests_list.slice(0, 3).map(request => ({
      label: request.number, detail: request.title, count: 1,
      href: '/procurement/requests?search=' + encodeURIComponent(request.number),
      tone: 'warning', icon: ClipboardList,
    })),
    ...data.low_stock_materials.slice(0, 2).map(material => ({
      label: material.name, detail: 'On hand: ' + material.current_stock + ' ' + material.unit,
      count: 1, href: '/inventory?search=' + encodeURIComponent(material.code),
      tone: 'critical', icon: AlertTriangle,
    })),
  ].slice(0, 4);

  const health = data.inventory_health || [
    { name: 'Healthy (OK)', count: Math.max(data.total_active_materials - data.low_stock_count, 0), color: '#0F7075' },
    { name: 'Low stock', count: data.low_stock_count, color: '#E99A17' },
  ];
  const healthyPercent = data.total_active_materials ? Math.round(health[0].count / data.total_active_materials * 100) : 0;
  const kpiColors = ['teal', 'amber', 'blue', 'rose'];
  const kpiHref = (label: string) => label.includes('project') || label.includes('Projects') ? '/projects' : label.includes('stock') ? '/inventory' : label.includes('Invoice') ? '/finance/payables' : label.includes('Payment') ? '/finance/payments' : label.includes('PO') ? '/procurement/purchase-orders?action_queue=po_progress' : label === 'Actions due' && role === 'storekeeper' ? '/procurement/deliveries?action_queue=warehouse_receipts' : '/procurement/requests?action_queue=my_requests';
  return (
    <div className="reference-dashboard">
      <section className="dashboard-greeting">
        <div><h1>Good day, {user?.first_name || user?.username || 'there'}</h1><p>Overview of your construction operations.</p></div>
        <div className="dashboard-greeting-actions"><span><CalendarDays size={15} />{new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date())}</span><Link className="dashboard-primary" to={financeRecovery ? '/finance/settings' : financeAvailable ? primaryAction[role || 'admin'].href : '/procurement/requests'}>{financeRecovery ? 'Enable Finance' : financeAvailable ? primaryAction[role || 'admin'].label : 'Open procurement'}</Link></div>
      </section>
      <section className="dashboard-kpis">
        {kpis.map((kpi, index) => <Link to={kpiHref(kpi.label)} className="dashboard-panel dashboard-kpi" key={kpi.label}>
          <span className={`dashboard-icon ${kpiColors[index]}`}><kpi.icon size={25} strokeWidth={1.7} /></span>
          <div><p>{kpi.label}</p><strong>{kpi.value}</strong><small>{kpi.note || 'Open workflow items'}</small></div>
        </Link>)}
      </section>
      <section className="dashboard-pair">
        <div className="dashboard-panel">
          <div className="dashboard-panel-heading"><h2>Project spending</h2><Link to="/projects">All projects <ChevronRight size={13}/></Link></div>
          <p className="dashboard-panel-note">Actual spend against each project’s budget.</p>
          <div className="dashboard-project-chart">
            {budgetRows.map(project => <Link key={project.id} className="dashboard-project-row" title={`Open ${project.name} · actual spend ${formatUGX(project.actualSpend)}${project.budget ? ` of ${formatUGX(project.budget)}` : ''}`} to={`/projects/${project.id}/progress`}>
              <span className="dashboard-project-name"><strong>{project.name}</strong><small>Progress {project.actualProgress}% · planned {project.plannedProgress}%</small></span>
              <span className="dashboard-spend"><span className="dashboard-spend-values"><strong>{formatCompactUGX(project.actualSpend)} spent</strong><small>{Number(project.budget) > 0 ? `of ${formatCompactUGX(Number(project.budget))}` : 'Budget not set'}</small></span>
                {Number(project.budget) > 0 && <span className={`dashboard-spend-track${project.actualSpend > Number(project.budget) ? ' over' : ''}`} role="img" aria-label={`${Math.round(project.actualSpend / Number(project.budget) * 100)}% of budget spent`}><i style={{width:`${project.actualSpendPercent}%`}} /></span>}
                {project.actualSpend > Number(project.budget) && Number(project.budget) > 0 ? <small className="dashboard-over">{formatCompactUGX(project.actualSpend - Number(project.budget))} over budget</small> : project.atRisk ? <small className="dashboard-over">Spend + commitments exceed budget by {formatCompactUGX(project.forecastCost - Number(project.budget))}</small> : null}
              </span>
            </Link>)}
            {!budgetRows.length && <p className="dashboard-empty">No projects in this scope. Open Projects to get started.</p>}
          </div>
          <Link className="dashboard-footer-link" to="/projects">View all projects <ChevronRight size={13}/></Link>
        </div>
        <div className="dashboard-panel dashboard-priorities">
          <div className="dashboard-panel-heading"><h2>Attention required</h2><Link to="/notifications">Notifications <ChevronRight size={13}/></Link></div>
          <div className="dashboard-attention">
            {workflow.isError ? <p className="dashboard-empty">Action counts unavailable. <button onClick={() => void workflow.refetch()}>Try again</button></p> : <DashboardQueues role={role} financeAvailable={financeAvailable} workflow={workflow.data} />}
            {!!attentionItems.length && <details className="dashboard-alert-details"><summary>Request & stock alerts ({attentionItems.length})</summary>{attentionItems.map(item=><Link key={item.label} to={item.href} className="dashboard-attention-row"><span className={`dashboard-icon small ${item.tone === 'critical' ? 'rose' : 'blue'}`}><item.icon size={17}/></span><span><strong>{item.label}</strong><small>{item.detail}</small></span><span className="dashboard-status attention">{item.tone === 'critical' ? 'Low stock' : 'Review'}</span><ChevronRight size={13}/></Link>)}</details>}
          </div>
        </div>
      </section>
      <details className="dashboard-panel dashboard-secondary">
        <summary>Workflow overview <span>Open queues and stock alerts</span></summary>
        <div className="dashboard-pipeline">
          {pipeline.filter(item => financeAvailable || !['Invoices','Payments'].includes(item.label)).map((item,index)=><Link to={item.href} key={item.label} className="dashboard-pipeline-step"><span className={`dashboard-step-number ${item.count ? 'active' : ''}`}>{index+1}</span><span className="dashboard-step-content"><span>{item.label}</span><strong>{item.count}</strong><small className={item.count ? 'pending' : 'clear'}>{item.count ? item.label === 'Stock' ? 'Stock alerts' : 'Needs action' : 'None pending'}</small></span></Link>)}
        </div>
      </details>
      <details className="dashboard-secondary"><summary>Stock activity & health <span>Supporting information</span></summary><section className="dashboard-pair">
        <div className="dashboard-panel">
          <div className="dashboard-panel-heading"><h2>Recent stock activity</h2><Link to="/inventory/movements">View all</Link></div>
          <div className="dashboard-activity">
            {data.recent_stock_movements.slice(0,4).map((movement,index)=><Link key={movement.id} to="/inventory/movements" className="dashboard-activity-row"><span className={`dashboard-icon small ${kpiColors[index]}`}><PackageCheck size={16}/></span><span className="dashboard-timeline-dot"/><span className="dashboard-activity-name"><strong>{movement.movement_type_display || 'Stock movement'} recorded</strong><small>{movement.material.name} · {movement.quantity}</small></span><small>{movement.project?.name || 'Warehouse'}</small><time>{movement.date ? new Date(movement.date).toLocaleDateString() : ''}</time></Link>)}
            {!data.recent_stock_movements.length && <p className="dashboard-empty">No stock activity recorded yet.</p>}
          </div>
        </div>
        <div className="dashboard-panel">
          <div className="dashboard-panel-heading"><h2>Inventory health</h2><Link to="/inventory">View all</Link></div>
          <div className="dashboard-health">
            <div className="dashboard-donut">
              <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={health.filter(item=>item.count>0)} dataKey="count" nameKey="name" innerRadius="68%" outerRadius="95%" paddingAngle={1} stroke="white" strokeWidth={1}>{health.filter(item=>item.count>0).map(item=><Cell key={item.name} fill={item.color}/>)}</Pie><Tooltip/></PieChart></ResponsiveContainer>
              <div><strong>{data.total_active_materials ? `${healthyPercent}%` : '—'}</strong><small>{data.total_active_materials ? 'Healthy' : 'No stock data'}</small></div>
            </div>
            <div className="dashboard-health-legend">{health.map(item=><div className="dashboard-health-row" key={item.name}><span><i style={{background:item.color}}/>{item.name}</span><span className="dashboard-health-track"><i style={{background:item.color,width:`${data.total_active_materials ? item.count/data.total_active_materials*100 : 0}%`}}/></span><small>{item.count} items</small><small>{data.total_active_materials ? Math.round(item.count/data.total_active_materials*100) : 0}%</small></div>)}<Link className="dashboard-footer-link" to="/inventory">View inventory</Link></div>
          </div>
        </div>
      </section></details>
    </div>
  );
}

function DashboardQueues({ role, financeAvailable, workflow }: { role: Role | null; financeAvailable: boolean; workflow?: WorkflowBadges }) {
  const keys: Record<Role, Array<keyof WorkflowBadges>> = {
    admin: ['requests', 'purchase_orders', 'deliveries', 'supplier_invoices', 'payments', 'budgets', 'expenses'],
    procurement_officer: ['requests', 'purchase_orders', 'deliveries'],
    project_manager: ['requests', 'budgets'],
    site_engineer: ['deliveries', 'requests'], storekeeper: ['deliveries', 'requests', 'inventory'],
    finance_officer: ['requests', 'supplier_invoices', 'payments', 'expenses'],
    finance_manager: ['requests', 'supplier_invoices', 'payments', 'budgets', 'expenses'], finance_viewer: [],
  };
  const destinations: Partial<Record<keyof WorkflowBadges, [string, string, string]>> = {
    requests: ['Request decisions', '/procurement/requests?action_queue=my_requests', 'Review approvals, sourcing and stock issues'],
    purchase_orders: ['Purchase orders', '/procurement/purchase-orders?action_queue=po_progress', 'Review the next step for each order'],
    deliveries: ['Delivery follow-ups', role === 'storekeeper' ? '/procurement/deliveries?action_queue=warehouse_receipts' : role === 'site_engineer' ? '/procurement/deliveries?action_queue=site_receipts' : role === 'procurement_officer' ? '/procurement/deliveries?action_queue=site_dispatch' : '/procurement/deliveries', 'Check arrivals, delays and receipt confirmations'],
    supplier_invoices: ['Invoice decisions', '/finance/payables', 'Review matching, exceptions and approvals'],
    payments: ['Payment decisions', '/finance/payments', 'Prepare, approve or post payment vouchers'],
    budgets: ['Budget approvals', '/finance/budgets', 'Review submitted budgets'],
    expenses: ['Expense decisions', '/finance/expenses', 'Review outstanding expense actions'],
    inventory: ['Stock alerts', '/inventory', 'Review material availability'],
  };
  if (!workflow) return <p className="dashboard-panel-note" role="status">Loading your action queues…</p>;
  const rows = keys[role || 'finance_viewer'].filter(key => workflow[key] && destinations[key] && (financeAvailable || !destinations[key]![1].startsWith('/finance')));
  return <>{!rows.length && <p className="dashboard-empty">{role === 'finance_viewer' ? 'View project and finance summaries using the links above.' : 'No pending actions in your queues.'}</p>}{rows.map(key => { const [label, href, detail] = destinations[key]!; return <Link className="dashboard-queue" key={key} to={href}><span className="dashboard-queue-count">{workflow[key]}</span><span><strong>{label}</strong><small>{detail}</small></span><ChevronRight size={16}/></Link>; })}</>;
}

function formatCompactUGX(value: number) {
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000_000) return `UGX ${(value / 1_000_000_000).toFixed(1).replace(/\.0$/, '')}B`;
  if (absolute >= 1_000_000) return `UGX ${(value / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  if (absolute >= 1_000) return `UGX ${(value / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
  return formatUGX(value);
}
