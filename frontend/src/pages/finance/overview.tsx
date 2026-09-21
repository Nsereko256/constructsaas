import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { financeApi } from '@/modules/finance/api';
import { qk } from '@/api/queryKeys';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatMoney } from '@/lib/utils';
import { FinanceKpi, FinancePage, Status } from './components';

export function FinanceOverviewPage() {
  const query = useQuery({ queryKey: qk.financeDashboard(), queryFn: () => financeApi.dashboard() });
  if (query.isLoading) return <Skeleton className="h-[560px]" />;
  if (query.isError || !query.data) throw query.error;
  const data = query.data;
  const currency = data.base_currency || 'UGX';
  const chart = data.project_balances.slice(0, 10).map((row) => ({
    code: row.project_code, Actual: Number(row.actual_expenditure), Committed: Number(row.open_commitments), Available: Number(row.available_balance),
  }));
  return (
    <FinancePage eyebrow="Finance control" title="Financial command centre" description={`Authoritative company position as at ${data.as_of}. Values are reported in ${currency}.`}>
      <section className="finance-primary-kpis" aria-label="Financial position">
        <FinanceKpi label="Approved budgets" value={formatMoney(data.approved_budgets, currency)} detail={`${data.project_balances.length} approved project budgets`} href="/finance/budgets" />
        <FinanceKpi label="Open commitments" value={formatMoney(data.open_commitments, currency)} detail="Approved purchasing not yet expensed" tone="info" href="/finance/budgets" />
        <FinanceKpi label="Actual expenditure" value={formatMoney(data.actual_expenditure, currency)} detail="Posted project expenditure" href="/finance/reports" />
      </section>
      <section aria-label="Finance work queues" className="finance-queue-grid">
        <QueueLink href="/finance/payables" label="Invoice control queue" detail="Match, verify, approve and post supplier invoices." count={data.unmatched_invoices} />
        <QueueLink href="/finance/payments" label="Payment control queue" detail="Review payment vouchers and posting actions." count={data.payments_awaiting_approval.count} />
        <QueueLink href="/finance/expenses" label="Staff cost queue" detail="Review expense claims and outstanding advances." count={formatMoney(data.outstanding_staff_advances, currency)} />
        <QueueLink href="/finance/budgets" label="Budget control queue" detail="Review approvals, commitments and available balances." count={data.pending_financial_approvals} />
      </section>
      <section>
        <Card>
          <CardHeader><CardTitle>Project budget position</CardTitle></CardHeader>
          <CardContent className="h-[300px]">
            {chart.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={chart}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="code" /><YAxis tickFormatter={(value) => `${Number(value) / 1000000}m`} /><Tooltip formatter={(value) => formatMoney(String(value), currency)} /><Legend /><Bar dataKey="Actual" stackId="used" fill="#087A3E" /><Bar dataKey="Committed" stackId="used" fill="#2878D0" /><Bar dataKey="Available" fill="#D7DDD7" /></BarChart></ResponsiveContainer> : <div className="grid h-full place-items-center text-sm text-muted">Approve a project budget to populate this view.</div>}
          </CardContent>
        </Card>
      </section>
      <Card>
        <CardHeader><CardTitle>Approved project balances</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm"><thead className="bg-[#EEF2EE] text-[10px] uppercase tracking-wide text-muted"><tr><th className="px-4 py-2.5">Project</th><th className="px-4 py-2.5">Status</th><th className="px-4 py-2.5 text-right">Revised</th><th className="px-4 py-2.5 text-right">Committed</th><th className="px-4 py-2.5 text-right">Actual</th><th className="px-4 py-2.5 text-right">Available</th></tr></thead><tbody>{data.project_balances.map((row) => <tr key={row.id} className="border-t border-border"><td className="px-4 py-3"><strong>{row.project_code}</strong><span className="ml-2 text-muted">{row.project_name}</span></td><td className="px-4 py-3"><Status value={row.status} /></td><td className="px-4 py-3 text-right">{formatMoney(row.revised_budget, currency)}</td><td className="px-4 py-3 text-right">{formatMoney(row.open_commitments, currency)}</td><td className="px-4 py-3 text-right">{formatMoney(row.actual_expenditure, currency)}</td><td className="px-4 py-3 text-right font-bold">{formatMoney(row.available_balance, currency)}</td></tr>)}</tbody></table>
          {!data.project_balances.length ? <p className="p-6 text-center text-sm text-muted">No approved project budgets yet.</p> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Site cost comparison</CardTitle><p className="text-xs text-muted">Operational site costs are compared here; approved budgets remain controlled at project level.</p></CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm"><thead className="bg-[#EEF2EE] text-[10px] uppercase tracking-wide text-muted"><tr><th className="px-4 py-2.5">Site</th><th className="px-4 py-2.5 text-right">Planned</th><th className="px-4 py-2.5 text-right">Committed</th><th className="px-4 py-2.5 text-right">Actual</th><th className="px-4 py-2.5 text-right">Forecast</th><th className="px-4 py-2.5 text-right">Variance</th></tr></thead><tbody>{data.site_balances.map((row) => <tr key={row.id} className="border-t border-border"><td className="px-4 py-3"><strong>{row.site_code}</strong><span className="ml-2 text-muted">{row.site_name}</span><p className="text-xs text-muted">{row.project_code} · {row.project_name}</p></td><td className="px-4 py-3 text-right">{formatMoney(row.planned_cost, currency)}</td><td className="px-4 py-3 text-right">{formatMoney(row.committed_cost, currency)}</td><td className="px-4 py-3 text-right">{formatMoney(row.actual_cost, currency)}</td><td className="px-4 py-3 text-right">{formatMoney(row.forecast_cost, currency)}</td><td className={Number(row.variance) > 0 ? 'px-4 py-3 text-right font-bold text-red-700' : 'px-4 py-3 text-right font-bold text-primary'}>{formatMoney(row.variance, currency)}</td></tr>)}</tbody></table>
          {!data.site_balances.length ? <p className="p-6 text-center text-sm text-muted">No active project sites match the current scope.</p> : null}
        </CardContent>
      </Card>
    </FinancePage>
  );
}

function QueueLink({ href, label, detail, count }: { href: string; label: string; detail: string; count: number | string }) {
  return <Link to={href} className="group border border-border bg-white p-3 hover:border-primary/40">
    <div className="flex items-start justify-between gap-3"><strong className="block text-sm">{label}</strong><span className="min-w-8 text-right text-sm font-black text-primary">{count}</span></div>
    <p className="mt-1 text-xs text-muted">{detail}</p><span className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-primary">Open <ArrowRight className="h-3.5 w-3.5" /></span>
  </Link>;
}
