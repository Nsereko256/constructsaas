import { useQuery } from '@tanstack/react-query';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { api } from '@/api/services';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Badge } from '@/components/ui/badge';
import { formatNumber, formatUGX } from '@/lib/utils';

export function ReportsPage() {
  const { role } = useAuth();
  const dashboard = useQuery({ queryKey: ['reports'], queryFn: api.reports, enabled: can.reports(role) });

  if (!can.reports(role)) {
    return <Card><CardContent className="p-5">Your role cannot view reports.</CardContent></Card>;
  }

  const data = dashboard.data;
  const procurement = [
    { name: 'Pending PRs', value: data?.pending_purchase_requests || 0 },
    { name: 'Low stock', value: data?.low_stock_count || 0 },
  ];

  return (
    <div className="grid gap-4">
      <PageToolbar title="Operations reports" subtitle="A management view of inventory, procurement pressure, and project material usage." />
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="Inventory value" value={formatUGX(data?.inventory_value)} tone="success" />
        <MetricCard label="Pending requests" value={formatNumber(String(data?.pending_purchase_requests || 0))} tone="warning" />
        <MetricCard label="Low-stock materials" value={formatNumber(String(data?.low_stock_count || 0))} tone="danger" />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
      <Card className="xl:col-span-2">
        <CardHeader><div className="flex items-start justify-between gap-3"><div><CardTitle>Inventory valuation</CardTitle><p className="mt-1 text-xs text-muted">Current weighted-average value across active company stock.</p></div><Badge tone="success">Live value</Badge></div></CardHeader>
        <CardContent className="grid gap-3">
          <strong className="text-3xl tracking-tight">{formatUGX(data?.inventory_value)}</strong>
          {(data?.low_stock_materials || []).map((material) => (
            <div key={material.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-background px-3 py-2.5 text-sm">
              <span><strong className="block">{material.name}</strong><span className="text-xs text-muted">Low-stock material</span></span>
              <strong>{formatUGX(material.stock_value)}</strong>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Procurement pressure</CardTitle><p className="mt-1 text-xs text-muted">Open demand versus stock risk.</p></CardHeader>
        <CardContent className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={procurement} dataKey="value" nameKey="name" innerRadius={60}>
                {procurement.map((_, index) => <Cell key={index} fill={index === 0 ? '#087A3E' : '#E99A11'} />)}
              </Pie>
              <Tooltip formatter={(value) => formatNumber(String(value))} />
            </PieChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      <Card className="xl:col-span-3">
        <CardHeader><CardTitle>Project budget position</CardTitle><p className="mt-1 text-xs text-muted">Finance-approved budget, commitments, actual expenditure, and available balance.</p></CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {(data?.project_budget_vs_actual || []).map((project) => (
            <div key={project.id} className="rounded-xl border border-border/70 bg-background p-3">
              <div className="flex items-start justify-between gap-2"><strong>{project.name}</strong><span className="text-xs font-bold text-primary">{formatUGX(project.remaining_budget)}</span></div>
              <p className="mt-2 text-xs text-muted">Available balance · {project.budget_source === 'finance' ? 'Finance budget' : 'Legacy project budget'}</p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs"><span>Budget<strong className="block text-sm">{formatUGX(project.budget)}</strong></span><span>Committed<strong className="block text-sm">{formatUGX(project.open_commitments)}</strong></span><span>Actual<strong className="block text-sm">{formatUGX(project.actual_expenditure)}</strong></span><span>Materials<strong className="block text-sm">{formatUGX(project.actual_material_cost)}</strong></span></div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
    </div>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: 'success' | 'warning' | 'danger' }) {
  return <Card><CardContent className="p-3.5"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted">{label}</p><strong className={`mt-1.5 block text-2xl tracking-tight ${tone === 'danger' ? 'text-critical' : tone === 'warning' ? 'text-[#8A5A00]' : 'text-primary'}`}>{value}</strong></CardContent></Card>;
}
