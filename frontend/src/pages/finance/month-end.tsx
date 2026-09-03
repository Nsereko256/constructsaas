import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, LockKeyhole, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { financeApi } from '@/modules/finance/api';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { FinancePage } from './components';

export function FinanceMonthEndPage() {
  const { role } = useAuth(); const toast = useToast(); const client = useQueryClient();
  const periods = useQuery({ queryKey: ['finance', 'periods'], queryFn: () => financeApi.fiscalPeriods({ page_size: 100, status: 'OPEN' }) });
  const [periodId, setPeriodId] = useState<number | null>(null);
  const activeId = periodId || periods.data?.results[0]?.id || null;
  const checklist = useQuery({ queryKey: ['finance', 'month-end', activeId], queryFn: () => financeApi.periodChecklist(activeId!), enabled: !!activeId });
  const close = useMutation({ mutationFn: () => financeApi.periodCommand(activeId!, 'close'), onSuccess: async () => { toast.push({ title: 'Fiscal period closed', tone: 'success' }); await client.invalidateQueries({ queryKey: ['finance'] }); }, onError: (error: Error) => toast.push({ title: 'Period cannot close', message: error.message, tone: 'danger' }) });
  const checkLinks: Record<string, string> = { unmatched_grns: '/procurement/grns', unmatched_invoices: '/finance/payables?status=SUBMITTED', pending_payments: '/finance/payments?status=SUBMITTED', unreconciled_cash: '/finance/reconciliation?status=UNRECONCILED', open_supplier_claims: '/procurement/supplier-claims?status=OPEN' };
  return <FinancePage eyebrow="Financial governance" title="Month-end close" description="Resolve every control item before locking the period. Closure is blocked server-side if anything changes after review.">
    <div className="flex flex-wrap gap-2 border border-border bg-white p-3 shadow-panel"><select className={inputClass} value={activeId || ''} onChange={(event) => setPeriodId(Number(event.target.value))}><option value="">Select open period</option>{periods.data?.results.map((period) => <option key={period.id} value={period.id}>{period.name} / {period.start_date} – {period.end_date}</option>)}</select></div>
    {!activeId ? <Card><CardContent className="p-4 text-sm text-muted">There is no open fiscal period to close.</CardContent></Card> : null}
    {checklist.data ? <><Card className={checklist.data.is_ready ? 'border-success/40' : 'border-warning/40'}><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4"><div className="flex items-center gap-2">{checklist.data.is_ready ? <CheckCircle2 className="h-5 w-5 text-success" /> : <TriangleAlert className="h-5 w-5 text-warning" />}<div><strong>{checklist.data.is_ready ? 'Ready to close' : 'Close blocked'}</strong><p className="text-sm text-muted">{checklist.data.period.name}: review all control items below.</p></div></div>{can.manageFinance(role) ? <Button loading={close.isPending} disabled={!checklist.data.is_ready} onClick={() => close.mutate()}><LockKeyhole className="h-4 w-4" />Close period</Button> : null}</CardContent></Card><div className="grid gap-2">{checklist.data.checks.map((check) => <Card key={check.key}><CardContent className="flex items-center justify-between gap-3 p-3"><div><strong className="text-sm">{check.label}</strong><p className="text-xs text-muted">{check.count ? 'Resolve the linked workflow records, then refresh this checklist.' : 'No outstanding items.'}</p></div><div className="flex items-center gap-2"><span className={check.count ? 'text-lg font-black text-warning' : 'text-lg font-black text-success'}>{check.count}</span>{check.count && checkLinks[check.key] ? <Link className="text-xs font-semibold text-primary hover:underline" to={checkLinks[check.key]}>Open records</Link> : null}</div></CardContent></Card>)}</div></> : null}
  </FinancePage>;
}
