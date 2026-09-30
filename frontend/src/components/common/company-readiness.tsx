import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequestWithoutSiteScope } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

type Readiness = { checked_at: string; attention_count: number; finance_enabled: boolean; checks: Array<{
  key: string; label: string; status: 'ready' | 'attention'; detail: string; href: string; owner: string;
}> };

export function CompanyReadiness() {
  const [showReady, setShowReady] = useState(false);
  const check = useQuery({ queryKey: ['company-readiness'], queryFn: () => apiRequestWithoutSiteScope<Readiness>('/api/company-readiness/') });
  return <Card id="readiness"><CardHeader className="flex flex-wrap items-center justify-between gap-3"><div><CardTitle>Company readiness</CardTitle><p className="mt-1 text-sm text-muted">Setup checks and outstanding handoffs. No stock or approvals are changed here.</p></div><Button variant="secondary" loading={check.isFetching} onClick={() => void check.refetch()}>Refresh checks</Button></CardHeader><CardContent>
    {check.isLoading ? <p role="status">Checking company setup…</p> : check.isError ? <p role="alert">Readiness checks could not load. Try refreshing.</p> : check.data ? <>
      <p className="mb-3 text-sm"><strong>{check.data.attention_count} areas need attention</strong> · Finance {check.data.finance_enabled ? 'enabled' : 'disabled'}. These checks do not replace end-to-end release testing.</p>
      <ul className="divide-y divide-border">{check.data.checks.filter((item) => showReady || item.status !== 'ready').map((item) => <li key={item.key} className="flex flex-wrap items-start gap-3 py-3"><Badge tone={item.status === 'ready' ? 'success' : 'warning'}>{item.status === 'ready' ? 'Ready' : 'Review'}</Badge><div className="min-w-0 flex-1 basis-64"><strong className="text-sm">{item.label}</strong><p className="mt-1 text-sm leading-relaxed text-muted">{item.detail}</p><small className="text-muted">Responsible: {item.owner}</small></div><Button variant="secondary" size="sm" asChild><Link to={item.href}>Open {item.label.toLowerCase()}</Link></Button></li>)}</ul>
      <Button variant="ghost" size="sm" aria-expanded={showReady} onClick={() => setShowReady(!showReady)}>{showReady ? 'Hide ready checks' : `Show ${check.data.checks.length - check.data.attention_count} ready checks`}</Button>
    </> : null}
  </CardContent></Card>;
}
