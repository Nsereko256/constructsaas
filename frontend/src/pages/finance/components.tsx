import { AlertCircle, ArrowUpRight, Download } from 'lucide-react';
import type React from 'react';
import { useQuery } from '@tanstack/react-query';
import { financeApi } from '@/modules/finance/api';
import { Link, Navigate, NavLink } from 'react-router-dom';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { Badge, statusTone } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { formatDate } from '@/lib/utils';

export const financeTabs = [
  ['Overview', '/finance'], ['Budgets', '/finance/budgets'], ['Payables', '/finance/payables'],
  ['Cash & Payments', '/finance/payments'], ['Expenses & Advances', '/finance/expenses'], ['Ledger', '/finance/ledger'],
  ['Payment batches', '/finance/payment-batches'],
  ['Month end', '/finance/month-end'],
  ['Reconciliation', '/finance/reconciliation'],
  ['Reports', '/finance/reports'], ['Setup & Audit', '/finance/settings'],
] as const;

const stakeholderTabs = new Set(['/finance', '/finance/budgets', '/finance/payables', '/finance/reports']);

export function FinanceGate({ children }: { children: React.ReactNode }) {
  const { role } = useAuth();
  return can.viewFinance(role) ? children : <Navigate to="/dashboard" replace />;
}

export function FinancePage({ eyebrow, title, description, actions, children }: {
  eyebrow: string; title: string; description: string; actions?: React.ReactNode; children: React.ReactNode;
}) {
  const { role } = useAuth();
  const tabs = role === 'project_manager' || role === 'procurement_officer'
    ? financeTabs.filter(([, href]) => stakeholderTabs.has(href))
    : financeTabs;
  return (
    <FinanceGate>
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
        <section className="min-w-0 rounded-2xl border border-border/80 bg-white shadow-panel">
          <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
            <div>
              <div className="flex items-center gap-2"><span className="h-6 w-1 rounded-full bg-primary" aria-hidden="true" /><div><p className="text-[10px] font-bold uppercase tracking-[0.17em] text-primary">{eyebrow}</p>
              <h2 className="mt-0.5 text-lg font-black tracking-tight sm:mt-1 sm:text-xl">{title}</h2></div></div>
              <p className="mt-0.5 max-w-3xl text-xs text-muted sm:mt-1 sm:text-sm">{description}</p>
            </div>
            {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
          </div>
          <nav className="flex overflow-x-auto px-2" aria-label="Finance navigation">
            {tabs.map(([label, href]) => (
              <NavLink key={href} to={href} end={href === '/finance'} className={({ isActive }) => cn('whitespace-nowrap rounded-t-lg border-b-2 border-transparent px-2.5 py-2 text-[11px] font-bold text-muted hover:bg-primary/5 hover:text-foreground sm:px-3 sm:py-2.5 sm:text-xs', isActive && 'border-primary bg-primary/5 text-primary')}>
                {label}
              </NavLink>
            ))}
          </nav>
        </section>
        {children}
      </div>
    </FinanceGate>
  );
}

export function FinanceKpi({ label, value, detail, tone = 'primary', href }: {
  label: string; value: React.ReactNode; detail?: string; tone?: 'primary' | 'info' | 'warning' | 'critical'; href?: string;
}) {
  const colors = { primary: 'border-l-primary', info: 'border-l-info', warning: 'border-l-warning', critical: 'border-l-critical' };
  const body = (
    <Card className={cn('h-full border-l-[3px]', colors[tone])}>
      <CardContent className="p-3.5 transition-shadow hover:shadow-lift">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted">{label}</p>
        <strong className="mt-1.5 block text-xl font-black tracking-tight">{value}</strong>
        {detail ? <p className="mt-1 text-xs text-muted">{detail}</p> : null}
      </CardContent>
    </Card>
  );
  return href ? <Link to={href} className="block h-full hover:brightness-[0.99]">{body}</Link> : body;
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
