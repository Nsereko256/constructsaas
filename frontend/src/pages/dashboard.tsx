import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DashboardData } from '@/api/types';
import { connectSocket } from '@/api/ws';
import { AlertTriangle, CalendarDays, ChevronRight, ClipboardCheck, ClipboardList, FolderKanban, PackageCheck, ReceiptText, Wallet } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { Role } from '@/api/types';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import './dashboard.css';

import { Skeleton } from '@/components/ui/skeleton';
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
        }
      },
    });
    return () => socket.close();
  }, [queryClient]);

  if (dashboard.isLoading) return <Skeleton className="h-[540px]" />;
  if (dashboard.isError || !dashboard.data) throw dashboard.error;

  const data = normalizeDashboardData(dashboard.data);
  const primaryAction: Record<Role, { label: string; href: string }> = {
    admin: { label: 'New request', href: '/procurement/requests?create=1' },
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
    const used = Number(project.actual_expenditure || 0) + Number(project.open_commitments || 0);
    const utilization = budget ? Math.min(100, Math.round((used / budget) * 100)) : 0;
    return { ...project, used, utilization, plannedProgress: Math.max(0, Math.min(100, Number(project.planned_progress ?? 0))), actualProgress: Math.max(0, Math.min(100, Number(project.actual_progress ?? 0))), atRisk: budget > 0 && used > budget };
  });
  const pipeline = [
    { label: 'Requests', count: data.pending_purchase_requests, status: 'Needs attention', href: '/procurement/requests' },
    { label: 'POs', count: workflow.data?.purchase_orders || 0, status: 'Open', href: '/procurement/purchase-orders' },
    { label: 'Deliveries', count: workflow.data?.deliveries || 0, status: 'In transit', href: '/procurement/deliveries' },
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
  return (
    <div className="reference-dashboard">
      <section className="dashboard-greeting">
        <div><h1>Good day, {user?.first_name || user?.username || 'there'}</h1><p>Overview of your construction operations.</p></div>
        <div className="dashboard-greeting-actions"><span><CalendarDays size={15} />{new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date())}</span><Link className="dashboard-primary" to={primaryAction[role || 'admin'].href}>{primaryAction[role || 'admin'].label}</Link></div>
      </section>
      <section className="dashboard-kpis">
        {kpis.map((kpi, index) => <div className="dashboard-panel dashboard-kpi" key={kpi.label}>
          <span className={`dashboard-icon ${kpiColors[index]}`}><kpi.icon size={25} strokeWidth={1.7} /></span>
          <div><p>{kpi.label}</p><strong>{kpi.value}</strong><small>{kpi.note || 'Open workflow items'}</small></div>
        </div>)}
      </section>
      <section className="dashboard-pair">
        <div className="dashboard-panel">
          <div className="dashboard-panel-heading"><h2>Projects overview</h2><div className="dashboard-legend"><span><i style={{background:'#D9DDDE'}} />Planned</span><span><i style={{background:'#0F7075'}} />Actual</span></div></div>
          <div className="dashboard-project-chart">
            {budgetRows.map(project => <Link key={project.id} className="dashboard-project-row" to={`/projects/${project.id}/progress`}>
              <span className="dashboard-project-name"><strong>{project.name}</strong><small>{project.code}</small></span>
              <span className="dashboard-bar-pair">
                {[{value:project.plannedProgress, color:'#D9DDDE', label:'Planned'}, {value:project.actualProgress, color:'#0F7075', label:'Actual'}].map(bar => <span key={bar.label} className="dashboard-bar-track" aria-label={`${bar.label}: ${bar.value}%`}><span className="dashboard-bar" style={{width:`${bar.value}%`, background:bar.color}} /><small style={{left:`${bar.value}%`}}>{bar.value}%</small></span>)}
              </span>
            </Link>)}
            {budgetRows.length ? <div className="dashboard-chart-axis"><span /> <div>{[0,25,50,75,100].map(n=><span key={n}>{n}%</span>)}</div></div> : <p className="dashboard-empty">Add a project, dates and goals to track delivery progress.</p>}
          </div>
          <Link className="dashboard-footer-link" to="/projects">View all projects <ChevronRight size={13}/></Link>
        </div>
        <div className="dashboard-panel">
          <div className="dashboard-panel-heading"><h2>Attention required</h2><Link to="/procurement/requests?action_queue=my_requests">View all</Link></div>
          <div className="dashboard-attention">
            {!attentionItems.length && <p className="dashboard-empty">No pending requests or stock alerts.</p>}
            {attentionItems.map(item=><Link key={item.label} to={item.href} className="dashboard-attention-row"><span className={`dashboard-icon small ${item.tone === 'critical' ? 'rose' : item.tone === 'info' ? 'teal' : 'blue'}`}><item.icon size={17}/></span><span><strong>{item.label}</strong><small>{item.detail}</small></span><span className={`dashboard-status ${item.count ? 'attention' : 'clear'}`}>{item.count ? item.tone === 'critical' ? 'Low stock' : 'Review' : 'All clear'}</span><ChevronRight size={13}/></Link>)}
          </div>
        </div>
      </section>
      <div className="dashboard-panel">
        <div className="dashboard-panel-heading"><h2>Procurement pipeline</h2></div>
        <div className="dashboard-pipeline">
          {pipeline.filter(item => !['Invoices','Payments'].includes(item.label) || !isFieldRole).map((item,index)=><Link to={item.href} key={item.label} className="dashboard-pipeline-step"><span className={`dashboard-step-number ${item.count ? 'active' : ''}`}>{index+1}</span><span className="dashboard-step-content"><span>{item.label}</span><strong>{item.count}</strong><small className={item.count ? 'pending' : 'clear'}>{item.count ? item.status === 'All clear' ? 'Needs attention' : item.status : 'All clear'}</small></span><span className="dashboard-step-connector"><ChevronRight size={13}/></span></Link>)}
        </div>
      </div>
      <section className="dashboard-pair">
        <div className="dashboard-panel">
          <div className="dashboard-panel-heading"><h2>Recent activity</h2><Link to="/inventory/movements">View all</Link></div>
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
      </section>
    </div>
  );
}
