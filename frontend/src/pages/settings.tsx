import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BellRing, Building2, CheckCircle2, Mail, ShieldCheck, UserRound } from 'lucide-react';
import type { ReactNode } from 'react';
import { api } from '@/api/services';
import type { EmailNotificationPreferences } from '@/api/types';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/components/ui/toast';

const categories: Array<{ key: keyof EmailNotificationPreferences; label: string; detail: string }> = [
  { key: 'procurement', label: 'Procurement', detail: 'Requests, purchase orders, returns and approvals' },
  { key: 'inventory', label: 'Inventory', detail: 'Low stock, stock exceptions and adjustments' },
  { key: 'projects', label: 'Projects', detail: 'Budget approvals and project cost warnings' },
  { key: 'finance', label: 'Finance', detail: 'Invoices, payments, overdue items and matching exceptions' },
  { key: 'system', label: 'System updates', detail: 'General platform information that normally stays in-app' },
];

export function SettingsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const preferences = useQuery({ queryKey: ['notifications', 'email-preferences'], queryFn: api.emailNotificationPreferences });
  const update = useMutation({
    mutationFn: api.updateEmailNotificationPreferences,
    onSuccess: (data) => {
      queryClient.setQueryData(['notifications', 'email-preferences'], data);
      toast.push({ title: 'Email preferences saved', tone: 'success' });
    },
    onError: (error: Error) => toast.push({ title: 'Could not save email preferences', message: error.message, tone: 'danger' }),
  });
  const test = useMutation({
    mutationFn: api.sendTestEmail,
    onSuccess: (data) => toast.push({ title: 'Test email sent', message: `Check ${data.email}.`, tone: 'success' }),
    onError: (error: Error) => toast.push({ title: 'Test email failed', message: error.message, tone: 'danger' }),
  });
  const value = preferences.data;

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5">
      <header>
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Workspace settings</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">Keep important operational alerts visible without filling your inbox with routine updates.</p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,.8fr)]">
        <Card>
          <CardHeader className="border-b border-border">
            <div className="flex items-start justify-between gap-4">
              <div><CardTitle className="flex items-center gap-2"><Mail className="h-5 w-5 text-primary" />Email notifications</CardTitle><p className="mt-1 text-sm text-muted">Email is reserved for records that need attention by default.</p></div>
              {value ? <StatusPill active={value.enabled && value.has_email && value.provider_configured} /> : null}
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 pt-5">
            {preferences.isLoading ? <p className="text-sm text-muted">Loading notification preferences…</p> : null}
            {preferences.isError ? <p className="rounded-lg border border-critical/30 bg-critical/5 p-3 text-sm text-critical">Email preferences could not be loaded.</p> : null}
            {value ? <>
              <PreferenceRow title="Email alerts" detail={value.email || 'No email address is saved for this account.'} checked={value.enabled} disabled={!value.has_email || update.isPending} onChange={(enabled) => update.mutate({ enabled })} />
              <div className="rounded-xl border border-primary/25 bg-primary/5 p-4">
                <div className="flex gap-3"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" /><div><strong className="text-sm">Recommended: required action only</strong><p className="mt-1 text-sm text-muted">Sends approvals, exceptions, rejections, overdue items, returns and critical stock or budget warnings. Completed and routine status updates remain in the app.</p></div></div>
                <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm font-semibold"><input type="checkbox" checked={value.required_only} disabled={!value.enabled || update.isPending} onChange={(event) => update.mutate({ required_only: event.target.checked })} />Only email items requiring action</label>
              </div>
              <div>
                <h2 className="text-sm font-bold">Operational areas</h2>
                <p className="mb-2 text-xs text-muted">Choose where required-action emails may originate.</p>
                <div className="divide-y divide-border rounded-xl border border-border">
                  {categories.map((category) => <PreferenceRow key={category.key} title={category.label} detail={category.detail} checked={Boolean(value[category.key])} disabled={!value.enabled || update.isPending} onChange={(checked) => update.mutate({ [category.key]: checked })} compact />)}
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-slate-50 p-4">
                <div><strong className="text-sm">Delivery check</strong><p className="text-xs text-muted">{value.provider_configured ? 'The email service is configured.' : 'An administrator must add the Amazon SES credentials.'}</p></div>
                <Button variant="secondary" onClick={() => test.mutate()} loading={test.isPending} loadingLabel="Sending…" disabled={!value.has_email || !value.provider_configured}><Mail className="h-4 w-4" />Send test email</Button>
              </div>
            </> : null}
          </CardContent>
        </Card>

        <div className="grid content-start gap-5">
          <Card><CardHeader><CardTitle className="flex items-center gap-2"><Building2 className="h-5 w-5 text-primary" />Workspace</CardTitle></CardHeader><CardContent className="grid gap-3 text-sm"><InfoLine label="Company" value={user?.company_name || '—'} /><InfoLine label="Signed in as" value={user?.username || '—'} icon={<UserRound className="h-4 w-4" />} /><InfoLine label="Role" value={user?.role_display || '—'} /></CardContent></Card>
          <Card><CardHeader><CardTitle className="flex items-center gap-2"><BellRing className="h-5 w-5 text-primary" />How alerts work</CardTitle></CardHeader><CardContent className="grid gap-3 text-sm text-muted"><p><strong className="text-foreground">In-app:</strong> complete activity history and routine updates.</p><p><strong className="text-foreground">Email:</strong> selected action-required alerts and exceptions.</p><p><strong className="text-foreground">Safe delivery:</strong> email failures do not interrupt approvals, receipts or payments.</p></CardContent></Card>
        </div>
      </div>
    </div>
  );
}

function PreferenceRow({ title, detail, checked, disabled, onChange, compact = false }: { title: string; detail: string; checked: boolean; disabled: boolean; onChange: (checked: boolean) => void; compact?: boolean }) {
  return <label className={`flex cursor-pointer items-center justify-between gap-4 ${compact ? 'px-4 py-3' : 'rounded-xl border border-border p-4'}`}><span><strong className="block text-sm">{title}</strong><small className="mt-0.5 block text-muted">{detail}</small></span><input className="h-4 w-4 accent-primary" type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} /></label>;
}

function StatusPill({ active }: { active: boolean }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold ${active ? 'bg-success/10 text-success' : 'bg-slate-100 text-muted'}`}><CheckCircle2 className="h-3.5 w-3.5" />{active ? 'Ready' : 'Setup needed'}</span>;
}

function InfoLine({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return <div className="flex items-center justify-between gap-3 border-b border-border pb-2 last:border-0 last:pb-0"><span className="flex items-center gap-1.5 text-muted">{icon}{label}</span><strong className="text-right">{value}</strong></div>;
}
