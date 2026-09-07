import {
  AlertCircle, ArrowUpRight, Banknote, BookOpenCheck, BriefcaseBusiness,
  CircleDollarSign, Clock3, Download, FileCheck2, Landmark, ReceiptText,
  ShieldCheck, SlidersHorizontal, WalletCards, type LucideIcon,
} from 'lucide-react';
import type React from 'react';
import { useQuery } from '@tanstack/react-query';
import { financeApi } from '@/modules/finance/api';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { Badge, statusTone } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { WorkspaceTabs } from '@/components/common/workspace-hub';
import { formatDate, formatMoney } from '@/lib/utils';
import { qk } from '@/api/queryKeys';
import './finance-reference.css';

export const financeTabs = [
  ['Overview', '/finance'], ['Budgets', '/finance/budgets'], ['Payables', '/finance/payables'],
  ['Cash & Payments', '/finance/payments'], ['Expenses & Advances', '/finance/expenses'],
  ['Month end', '/finance/month-end'],
  ['Reports', '/finance/reports'], ['Setup & Audit', '/finance/settings'],
] as const;

const stakeholderTabs = new Set(['/finance', '/finance/budgets', '/finance/payables', '/finance/reports']);

export function FinanceGate({ children }: { children: React.ReactNode }) {
  const { role, user, retrySession } = useAuth();
  const location = useLocation();
  const canConfigureDisabledModule = role === 'admin' && location.pathname === '/finance/settings';
  const disabledCapability = (
    (location.pathname.startsWith('/finance/payables') && user?.invoice_tracking_enabled === false)
    || (location.pathname.startsWith('/finance/payments') && user?.payment_tracking_enabled === false)
  );
  if (!can.viewFinance(role)) return <Navigate to="/dashboard" replace />;
  if (canConfigureDisabledModule) return children;
  if (user?.soft_finance_enabled === false) {
    return <FinanceUnavailable title="Soft Finance is disabled" message="Your company has turned off Finance / Cost Control. An administrator can turn it back on from Finance settings without changing procurement or inventory records." action="Open Finance settings" to="/finance/settings" />;
  }
  if (disabledCapability) {
    const capability = location.pathname.startsWith('/finance/payables') ? 'invoice tracking' : 'payment tracking';
    return <FinanceUnavailable title={`${capability[0].toUpperCase()}${capability.slice(1)} is disabled`} message={`This workspace is unavailable because ${capability} is turned off for your company. An administrator can re-enable it from Finance settings.`} action="Review Finance settings" to="/finance/settings" />;
  }
  if (!user) return <FinanceUnavailable title="Finance access needs verification" message="We could not confirm your Finance settings yet. Retry the session check, then try this page again." action="Retry session check" onAction={retrySession} />;
  return children;
}

function FinanceUnavailable({ title, message, action, to, onAction }: { title: string; message: string; action: string; to?: string; onAction?: () => void }) {
  return <div className="finance-unavailable" role="status"><div className="finance-unavailable-icon"><ShieldCheck className="h-6 w-6" /></div><div className="min-w-0"><h1>{title}</h1><p>{message}</p>{to ? <Link className="finance-unavailable-action" to={to}>{action} <ArrowUpRight className="h-3.5 w-3.5" /></Link> : <button type="button" className="finance-unavailable-action" onClick={onAction}>{action}</button>}</div></div>;
}

export function FinancePage({ eyebrow, title, description, actions, children }: {
  eyebrow: string; title: string; description: string; actions?: React.ReactNode; children: React.ReactNode;
}) {
  const { role, user } = useAuth();
  const tabs = role === 'project_manager' || role === 'procurement_officer'
    ? financeTabs.filter(([, href]) => stakeholderTabs.has(href))
    : financeTabs;
  const enabledTabs = tabs.filter(([, href]) => (
    !(href === '/finance/payables' && user?.invoice_tracking_enabled === false)
    && !(href === '/finance/payments' && user?.payment_tracking_enabled === false)
  ));
  return (
    <FinanceGate>
      <div className="finance-reference grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
        <header className="finance-page-head min-w-0">
          <div className="finance-page-titlebar flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <p className="finance-page-eyebrow">{eyebrow}</p>
              <h1>{title}</h1>
              <p className="finance-page-description">{description}</p>
            </div>
            {actions ? <div className="finance-page-actions flex flex-wrap items-center gap-2">{actions}</div> : null}
          </div>
          <div className="finance-tabs"><WorkspaceTabs links={enabledTabs.map(([label, href]) => ({ label, href }))} /></div>
        </header>
        {children}
      </div>
    </FinanceGate>
  );
}

export function FinanceKpi({ label, value, detail, tone = 'primary', href }: {
  label: string; value: React.ReactNode; detail?: string; tone?: 'primary' | 'info' | 'warning' | 'critical'; href?: string;
}) {
  const Icon = kpiIcon(label);
  const body = (
    <Card className={cn('finance-kpi h-full', `finance-kpi-${tone}`)}>
      <CardContent className="finance-kpi-content">
        <div className="finance-kpi-icon" aria-hidden="true"><Icon /></div>
        <div className="min-w-0">
          <p className="finance-kpi-label">{label}</p>
          <strong className="finance-kpi-value">{value}</strong>
          {detail ? <p className="finance-kpi-detail">{detail}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
  return href ? <Link to={href} className="block h-full hover:brightness-[0.99]">{body}</Link> : body;
}

type FinanceSummaryView = 'budgets' | 'payables' | 'payments' | 'expenses' | 'month-end' | 'reports';

export function FinanceWorkspaceSummary({ view }: { view: FinanceSummaryView }) {
  const query = useQuery({ queryKey: qk.financeDashboard(), queryFn: () => financeApi.dashboard() });
  if (!query.data) return null;
  const data = query.data;
  const currency = data.base_currency || 'UGX';
  const summaries: Record<FinanceSummaryView, Array<Parameters<typeof FinanceKpi>[0]>> = {
    budgets: [
      { label: 'Approved budgets', value: formatMoney(data.approved_budgets, currency), detail: `${data.project_balances.length} controlled projects` },
      { label: 'Open commitments', value: formatMoney(data.open_commitments, currency), detail: 'Approved, not yet expensed', tone: 'info' },
      { label: 'Actual expenditure', value: formatMoney(data.actual_expenditure, currency), detail: 'Posted project costs' },
      { label: 'Available balance', value: formatMoney(data.available_project_balances, currency), detail: 'Remaining approved capacity', tone: 'info' },
    ],
    payables: [
      { label: 'Unpaid invoices', value: data.unpaid_invoices.count, detail: formatMoney(data.unpaid_invoices.base_amount, currency), tone: 'info' },
      { label: 'Unmatched invoices', value: data.unmatched_invoices, detail: 'Need matching review', tone: data.unmatched_invoices ? 'warning' : 'primary' },
      { label: 'Overdue invoices', value: data.overdue_invoices.count, detail: formatMoney(data.overdue_invoices.base_amount, currency), tone: data.overdue_invoices.count ? 'critical' : 'primary' },
      { label: 'Pending approvals', value: data.pending_financial_approvals, detail: 'Across finance controls', tone: 'warning' },
    ],
    payments: [
      { label: 'Payments awaiting approval', value: data.payments_awaiting_approval.count, detail: formatMoney(data.payments_awaiting_approval.base_amount, currency), tone: 'warning' },
      { label: 'Unpaid invoices', value: data.unpaid_invoices.count, detail: formatMoney(data.unpaid_invoices.base_amount, currency), tone: 'info' },
      { label: 'Outstanding advances', value: formatMoney(data.outstanding_staff_advances, currency), detail: 'Awaiting retirement or recovery', tone: 'warning' },
      { label: 'Available project balance', value: formatMoney(data.available_project_balances, currency), detail: 'After costs and commitments' },
    ],
    expenses: [
      { label: 'Actual expenditure', value: formatMoney(data.actual_expenditure, currency), detail: 'Posted project costs' },
      { label: 'Outstanding advances', value: formatMoney(data.outstanding_staff_advances, currency), detail: 'Staff accountability balance', tone: 'warning' },
      { label: 'Pending approvals', value: data.pending_financial_approvals, detail: 'Finance decisions required', tone: 'warning' },
      { label: 'Available balance', value: formatMoney(data.available_project_balances, currency), detail: 'Remaining project capacity', tone: 'info' },
    ],
    'month-end': [
      { label: 'Actual expenditure', value: formatMoney(data.actual_expenditure, currency), detail: `Position at ${data.as_of}` },
      { label: 'Unpaid invoices', value: data.unpaid_invoices.count, detail: formatMoney(data.unpaid_invoices.base_amount, currency), tone: 'info' },
      { label: 'Pending approvals', value: data.pending_financial_approvals, detail: 'Must be reviewed before close', tone: 'warning' },
      { label: 'Overdue invoices', value: data.overdue_invoices.count, detail: formatMoney(data.overdue_invoices.base_amount, currency), tone: data.overdue_invoices.count ? 'critical' : 'primary' },
    ],
    reports: [
      { label: 'Approved budgets', value: formatMoney(data.approved_budgets, currency), detail: 'Current approved envelope' },
      { label: 'Actual expenditure', value: formatMoney(data.actual_expenditure, currency), detail: 'Posted cost position' },
      { label: 'Open commitments', value: formatMoney(data.open_commitments, currency), detail: 'Approved future costs', tone: 'info' },
      { label: 'Inventory value', value: formatMoney(data.inventory_value, currency), detail: 'Current stock valuation', tone: 'info' },
    ],
  };
  return <section className="finance-primary-kpis" aria-label={`${view} summary`}>
    {summaries[view].map((item) => <FinanceKpi key={item.label} {...item} />)}
  </section>;
}

function kpiIcon(label: string): LucideIcon {
  const normalized = label.toLowerCase();
  if (normalized.includes('budget') || normalized.includes('balance')) return CircleDollarSign;
  if (normalized.includes('commitment')) return BriefcaseBusiness;
  if (normalized.includes('approval')) return FileCheck2;
  if (normalized.includes('invoice') || normalized.includes('payable')) return ReceiptText;
  if (normalized.includes('payment') || normalized.includes('cash')) return WalletCards;
  if (normalized.includes('expense') || normalized.includes('actual')) return Banknote;
  if (normalized.includes('overdue') || normalized.includes('pending')) return Clock3;
  if (normalized.includes('audit') || normalized.includes('control')) return ShieldCheck;
  if (normalized.includes('report')) return BookOpenCheck;
  if (normalized.includes('setting')) return SlidersHorizontal;
  return Landmark;
}

export function Status({ value }: { value: string }) {
  return <Badge tone={statusTone(value)}>{value.replace(/_/g, ' ')}</Badge>;
}

export function InlineError({ error }: { error: Error | null | undefined }) {
  if (!error) return null;
  return <div className="flex items-center gap-2 rounded-lg border border-critical/20 bg-critical/5 p-3 text-sm text-critical"><AlertCircle className="h-4 w-4" />{error.message}</div>;
}

export function DrillLink({ to, children }: { to: string; children: React.ReactNode }) {
  return <Link to={to} className="inline-flex items-center gap-1 font-bold text-info hover:underline">{children}<ArrowUpRight className="h-3 w-3" /></Link>;
}

export function FinanceActivityTimeline({ objectType, objectId }: { objectType: string; objectId: number }) {
  const audit = useQuery({
    queryKey: ['finance', 'audit', objectType, objectId],
    queryFn: () => financeApi.auditEvents({ object_type: objectType, object_id: objectId, page_size: 12 }),
  });
  const attachments = useQuery({
    queryKey: ['finance', 'invoice-attachments', objectId],
    queryFn: () => financeApi.invoiceAttachments({ invoice: objectId, page_size: 100 }),
    enabled: objectType === 'SupplierInvoice',
  });
  const events = audit.data?.results || [];
  return <Card>
    <CardContent className="grid gap-3 p-3">
      <div><strong className="text-sm">Activity and accountability</strong><p className="text-xs text-muted">Every recorded finance action shows who performed it and when.</p></div>
      {audit.isLoading ? <p className="text-sm text-muted">Loading activity…</p> : null}
      {!audit.isLoading && !events.length ? <p className="text-sm text-muted">No finance actions have been recorded yet.</p> : null}
      {events.map((event) => <div key={event.id} className="border-l-2 border-primary/30 pl-3 text-sm"><div className="flex flex-wrap justify-between gap-2"><strong>{event.action.replace(/\./g, ' ')}</strong><span className="text-xs text-muted">{formatDate(event.created_at)}</span></div><p className="mt-0.5 text-xs text-muted">By {event.actor_username || 'System'}{event.message ? ` — ${event.message}` : ''}</p></div>)}
      {objectType === 'SupplierInvoice' ? <div className="border-t border-border pt-3"><strong className="text-sm">Supporting documents</strong>{attachments.isLoading ? <p className="mt-2 text-xs text-muted">Loading documents…</p> : null}{!attachments.isLoading && !attachments.data?.results.length ? <p className="mt-2 text-xs text-muted">No documents attached.</p> : null}<div className="mt-2 grid gap-2">{attachments.data?.results.map((attachment) => <div key={attachment.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-2.5 py-2 text-xs"><div><strong>{attachment.original_name}</strong><p className="text-muted">{attachment.content_type} · {formatDate(attachment.created_at)}</p></div><button type="button" className="inline-flex items-center gap-1 font-bold text-primary hover:underline" onClick={() => void financeApi.downloadInvoiceAttachment(attachment.id, attachment.original_name)}><Download className="h-3.5 w-3.5" />Download</button></div>)}</div></div> : null}
    </CardContent>
  </Card>;
}
