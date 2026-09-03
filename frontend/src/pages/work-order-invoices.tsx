import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '@/api/services';
import { Badge, statusTone } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { PageToolbar } from '@/components/common/page-toolbar';

export function WorkOrderInvoicesPage() {
  const invoices = useQuery({ queryKey: ['work-order-invoices'], queryFn: api.workOrderInvoices });
  return <div className="grid gap-4"><PageToolbar title="Work order invoices" subtitle="Supplier invoices and contractor costs linked to work orders and physical site packages." />{invoices.isError ? <Card><CardContent className="p-4 text-sm text-critical">Work-order invoices could not be loaded. Refresh the page or try again.</CardContent></Card> : null}<div className="grid gap-3">{(invoices.data || []).map((invoice) => <Card key={invoice.id}><CardContent className="grid gap-2 p-4 sm:grid-cols-[1fr_auto]"><div><div className="flex flex-wrap items-center gap-2"><strong>{invoice.internal_number || invoice.invoice_number}</strong><Badge tone={statusTone(invoice.status)}>{invoice.status}</Badge></div><p className="mt-1 text-sm">{invoice.work_order}{invoice.site ? ` · ${invoice.site}` : ''}</p><p className="text-xs text-muted">{invoice.supplier} · Supplier invoice {invoice.invoice_number} · Due {invoice.due_date || 'Not set'}</p></div><div className="text-left sm:text-right"><strong>{invoice.currency} {Number(invoice.total_amount).toLocaleString()}</strong><br /><Link className="text-xs font-semibold text-primary underline" to="/finance/payables">Open in payables</Link></div></CardContent></Card>)}{!invoices.isLoading && !invoices.isError && !(invoices.data || []).length ? <Card><CardContent className="p-6 text-center text-sm text-muted">No supplier invoice is linked to your accessible work orders yet.</CardContent></Card> : null}</div></div>;
}
