import type { ColumnDef } from '@tanstack/react-table';
import { useQuery } from '@tanstack/react-query';
import { Download, FileSpreadsheet, FileText } from 'lucide-react';
import { useMemo, useState } from 'react';
import { financeApi } from '@/modules/finance/api';
import { qk } from '@/api/queryKeys';
import { api } from '@/api/services';
import { Pagination } from '@/components/common/pagination';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatMoney } from '@/lib/utils';
import { FinancePage } from './components';

const reports = [
  ['budget-vs-actual', 'Budget versus actual'],
  ['project-cost-summary', 'Project cost summary'],
  ['material-cost-by-project', 'Material cost by project'],
  ['inventory-valuation', 'Inventory valuation'],
  ['supplier-statements', 'Supplier statements'],
  ['accounts-payable-ageing', 'Accounts payable ageing'],
  ['purchase-commitments', 'Purchase commitments'],
  ['invoice-matching-exceptions', 'Invoice matching exceptions'],
  ['payment-register', 'Payment register'],
  ['expense-register', 'Expense register'],
  ['staff-advances', 'Staff advances'],
  ['general-ledger', 'General ledger'],
  ['trial-balance', 'Trial balance'],
  ['finance-audit-events', 'Finance audit events'],
  ['project-forecast', 'Project forecast'],
  ['procurement-aging', 'Procurement aging'],
  ['inventory-health', 'Inventory health'],
  ['finance-control-pack', 'Finance control pack'],
  ['supplier-performance', 'Supplier performance'],
] as const;

type ReportSlug = (typeof reports)[number][0];

export function FinanceReportsPage() {
  const [slug, setSlug] = useState<ReportSlug>('budget-vs-actual');
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ date_from: '', date_to: '', project: '', supplier: '', status: '' });
  const toast = useToast();
  const projects = useQuery({ queryKey: qk.projects({ page_size: 100 }), queryFn: () => api.projects({ page_size: 100 }) });
  const suppliers = useQuery({ queryKey: qk.suppliers({ page_size: 100 }), queryFn: () => api.suppliers({ page_size: 100 }) });
  const params = { ...filters, page };
  const query = useQuery({ queryKey: qk.financeReport(slug, params), queryFn: () => financeApi.report(slug, params) });
  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(() => {
    const keys = Object.keys(query.data?.results[0] || {})
      .filter((key) => !key.endsWith('_url') && !['id', 'metadata'].includes(key))
      .slice(0, 8);
    return keys.map((key) => ({
      header: key.replace(/_/g, ' '),
      cell: ({ row }) => renderValue(key, row.original[key]),
    }));
  }, [query.data]);
  const setFilter = (key: keyof typeof filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  };
  const download = async (format: 'csv' | 'xlsx' | 'pdf') => {
    try {
      await financeApi.downloadReport(slug, format, filters);
      toast.push({ title: `${format.toUpperCase()} report prepared`, tone: 'success' });
    } catch (error) {
      toast.push({ title: 'Report download failed', message: (error as Error).message, tone: 'danger' });
    }
  };

  return (
    <FinancePage
      eyebrow="Authoritative reporting"
      title="Finance reports"
      description="Filter, drill down, and export company-scoped financial and project-cost information."
      actions={<><Button variant="secondary" onClick={() => void download('csv')}><Download className="h-4 w-4" />CSV</Button><Button variant="secondary" onClick={() => void download('pdf')}><FileText className="h-4 w-4" />PDF</Button><Button onClick={() => void download('xlsx')}><FileSpreadsheet className="h-4 w-4" />Excel</Button></>}
    >
      <div className="grid min-w-0 gap-2 border border-border bg-white p-3 shadow-panel lg:grid-cols-[minmax(180px,1.3fr)_repeat(5,minmax(0,1fr))]">
        <select className={`${inputClass} min-w-0 w-full`} value={slug} onChange={(event) => { setSlug(event.target.value as ReportSlug); setPage(1); }}>
          {reports.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <input className={`${inputClass} min-w-0 w-full`} type="date" value={filters.date_from} onChange={(event) => setFilter('date_from', event.target.value)} aria-label="Report date from" />
        <input className={`${inputClass} min-w-0 w-full`} type="date" value={filters.date_to} onChange={(event) => setFilter('date_to', event.target.value)} aria-label="Report date to" />
        <select className={`${inputClass} min-w-0 w-full`} value={filters.project} onChange={(event) => setFilter('project', event.target.value)}>
          <option value="">All projects</option>
          {projects.data?.results.map((project) => <option key={project.id} value={project.id}>{project.code} / {project.name}</option>)}
        </select>
        <select className={`${inputClass} min-w-0 w-full`} value={filters.supplier} onChange={(event) => setFilter('supplier', event.target.value)}>
          <option value="">All suppliers</option>
          {suppliers.data?.results.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}
        </select>
        <input className={`${inputClass} min-w-0 w-full`} value={filters.status} onChange={(event) => setFilter('status', event.target.value)} placeholder="Status / action" />
      </div>
      {query.data ? (
        <Card><CardContent className="flex flex-wrap gap-x-8 gap-y-2 p-3">
          {Object.entries(query.data.totals).map(([key, value]) => <div key={key}><span className="text-[10px] font-bold uppercase tracking-wide text-muted">{key.replace(/_/g, ' ')}</span><strong className="ml-2 text-sm">{key.includes('count') ? String(value) : formatMoney(String(value))}</strong></div>)}
        </CardContent></Card>
      ) : null}
      <DataTable columns={columns} data={query.data?.results || []} emptyTitle={query.isLoading ? 'Calculating report...' : 'No report rows match these filters'} />
      <Pagination page={page} setPage={setPage} data={query.data} />
    </FinancePage>
  );
}

function renderValue(key: string, value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'object') return JSON.stringify(value);
  if (/(amount|budget|balance|cost|value|debit|credit|expenditure|commitment|total)/.test(key)) return formatMoney(String(value));
  if (key.includes('date') || key.endsWith('_at')) return new Date(String(value)).toLocaleDateString();
  return String(value).replace(/_/g, ' ');
}
