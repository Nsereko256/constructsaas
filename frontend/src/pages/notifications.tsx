import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, BellRing, CheckCheck, CircleAlert, Info } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate } from '@/lib/utils';
import type { NotificationItem } from '@/api/types';

export function NotificationsPage() {
  const list = useListState({ is_read: '' });
  const notifications = useQuery({ queryKey: qk.notifications(list.query), queryFn: () => api.notifications(list.query) });
  const queryClient = useQueryClient();
  const toast = useToast();
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushAvailable, setPushAvailable] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [selected, setSelected] = useState<NotificationItem | null>(null);
  useEffect(() => {
    void api.pushConfig().then((config) => setPushAvailable(config.enabled)).catch(() => setPushAvailable(false));
    void navigator.serviceWorker?.ready.then(async (registration) => setPushEnabled(Boolean(await registration.pushManager.getSubscription())));
  }, []);
  const togglePush = async () => {
    if (!pushAvailable || !('serviceWorker' in navigator) || !('PushManager' in window)) {
      toast.push({ title: 'Phone notifications are not available in this browser', tone: 'warning' });
      return;
    }
    setPushBusy(true);
    try {
      const registration = await navigator.serviceWorker.ready;
      const existing = await registration.pushManager.getSubscription();
      if (existing) {
        await api.removePushSubscription(existing.endpoint);
        await existing.unsubscribe();
        setPushEnabled(false);
        toast.push({ title: 'Phone notifications disabled', tone: 'success' });
      } else {
        const config = await api.pushConfig();
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') throw new Error('Notification permission was not granted.');
        const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(config.public_key) });
        await api.savePushSubscription(subscription.toJSON());
        setPushEnabled(true);
        toast.push({ title: 'Phone notifications enabled', tone: 'success' });
      }
    } catch (error) {
      toast.push({ title: error instanceof Error ? error.message : 'Could not update phone notifications.', tone: 'danger' });
    } finally { setPushBusy(false); }
  };
  const testPush = async () => {
    setPushBusy(true);
    try {
      const result = await api.sendTestPush();
      toast.push({ title: result.delivered ? 'Test notification sent' : 'No device is subscribed yet', tone: result.delivered ? 'success' : 'warning' });
    } finally { setPushBusy(false); }
  };
  const markRead = useMutation({
    mutationFn: api.markNotificationRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
  const markAll = useMutation({
    mutationFn: api.markAllNotificationsRead,
    onSuccess: () => {
      toast.push({ title: 'All notifications marked as read', tone: 'success' });
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  return (
    <div className="grid gap-3 sm:gap-4">
      <PageToolbar title="Notifications" subtitle="Tap an alert to view the full detail." search={list.search} onSearch={list.setSearch}>
        <div className="flex min-w-0 gap-2 overflow-x-auto pb-0.5 [&>button]:w-auto [&>button]:shrink-0">
        <select className="min-h-10 shrink-0 border border-border bg-white px-3 text-sm" value={list.filters.is_read} onChange={(event) => list.setFilter('is_read', event.target.value)}>
          <option value="">All</option>
          <option value="false">Unread</option>
          <option value="true">Read</option>
        </select>
        <Button variant="ghost" size="sm" onClick={() => markAll.mutate()} disabled={markAll.isPending} aria-label="Mark all notifications read"><CheckCheck className="h-4 w-4" />Read all</Button>
        <Button variant={pushEnabled ? 'secondary' : 'default'} size="sm" onClick={() => void togglePush()} disabled={pushBusy || !pushAvailable}><BellRing className="h-4 w-4" />{pushEnabled ? 'Alerts on' : 'Phone alerts'}</Button>
        {pushEnabled ? <Button variant="ghost" size="sm" onClick={() => void testPush()} disabled={pushBusy}>Test</Button> : null}
        </div>
      </PageToolbar>
      <div className="overflow-hidden rounded-2xl border border-border/80 bg-white shadow-panel">
        {(notifications.data?.results || []).map((item) => (
          <button key={item.id} type="button" onClick={() => { setSelected(item); if (!item.is_read) markRead.mutate(item.id); }} className={`grid w-full grid-cols-[40px_minmax(0,1fr)_auto] items-start gap-3 border-b border-border px-3 py-3 text-left last:border-0 hover:bg-background focus-visible:bg-background ${item.is_read ? 'opacity-70' : ''}`}>
            <span className="relative grid h-10 w-10 place-items-center rounded-xl bg-primary/10"><NotificationIcon level={item.level} />{!item.is_read ? <i className="absolute right-0 top-0 h-2 w-2 rounded-full bg-primary" aria-label="Unread" /> : null}</span>
            <span className="min-w-0">
              <span className="flex items-baseline gap-2"><strong className="truncate text-sm">{item.title}</strong><span className="shrink-0 text-[11px] text-muted">{formatDate(item.created_at)}</span></span>
              <span className="notification-preview mt-0.5 block text-sm text-muted">{item.message}</span>
            </span>
            <ArrowRight className="mt-2 h-4 w-4 shrink-0 text-muted" />
          </button>
        ))}
        {!notifications.data?.results.length ? <p className="p-6 text-center text-sm text-muted">No notifications match this view.</p> : null}
      </div>
      <Pagination page={list.page} setPage={list.setPage} data={notifications.data} />
      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent title={selected?.title || 'Notification'} description={selected ? formatDate(selected.created_at) : undefined}>
          {selected ? <div className="grid gap-4">
            <div className="flex items-center gap-2"><NotificationIcon level={selected.level} /><Badge tone={statusTone(selected.level)}>{selected.level}</Badge>{!selected.is_read ? <Badge tone="info">New</Badge> : null}</div>
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
              <Detail label="Received" value={formatDate(selected.created_at)} />
              <Detail label="Category" value={notificationLabel(selected.notification_type)} />
              <Detail label="State" value={selected.is_read ? 'Read' : 'Unread'} />
            </div>
            <p className="whitespace-pre-wrap text-sm leading-6 text-foreground">{selected.message}</p>
            <div className="flex flex-col gap-2 sm:flex-row">
              {!selected.is_read ? <Button variant="secondary" onClick={() => markRead.mutate(selected.id)}>Mark as read</Button> : null}
              {notificationDestination(selected) ? <Button asChild><Link to={notificationDestination(selected)!} onClick={() => setSelected(null)}>{notificationActionLabel(selected.notification_type)} <ArrowRight className="h-4 w-4" /></Link></Button> : null}
            </div>
          </div> : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}


function urlBase64ToUint8Array(value: string) {
  const padded = `${value}${'='.repeat((4 - (value.length % 4)) % 4)}`.replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

function NotificationIcon({ level }: { level: string }) {
  if (level === 'critical') return <CircleAlert className="h-5 w-5 shrink-0 text-critical" aria-label="Critical" />;
  if (level === 'warning') return <AlertTriangle className="h-5 w-5 shrink-0 text-warning" aria-label="Warning" />;
  return <Info className="h-5 w-5 shrink-0 text-info" aria-label="Information" />;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-border bg-background px-2.5 py-2"><span className="block text-[10px] font-bold uppercase tracking-wide text-muted">{label}</span><strong className="mt-0.5 block truncate text-xs text-foreground" title={value}>{value}</strong></div>;
}

function notificationLabel(notificationType: string) {
  return notificationType.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function notificationDestination(item: { notification_type: string; link: string }) {
  // A server-provided link identifies the actual record; only fall back to a
  // module landing page for older notifications that do not include one.
  if (item.link.startsWith('/') && !item.link.startsWith('/api/')) return item.link;
  if (item.notification_type === 'low_stock') return '/inventory';
  if (item.notification_type.includes('budget_approval') && item.link.includes('/budgets/')) return '/finance/budgets';
  if (item.notification_type.startsWith('pr_') || item.notification_type.includes('budget_approval')) return '/procurement/requests';
  if (item.notification_type === 'po_created') return '/procurement/purchase-orders';
  if (item.notification_type === 'po_received') return '/procurement/grns';
  if (item.notification_type.startsWith('invoice_')) return '/finance/payables';
  if (item.notification_type.startsWith('payment_')) return '/finance/payments';
  if (item.notification_type === 'staff_advance_overdue') return '/finance/expenses';
  if (item.notification_type === 'valuation_adjustment') return '/inventory/movements';
  if (item.notification_type === 'journal_posting_failure') return '/finance/ledger';
  if (item.notification_type === 'po_exceeding_budget') return '/procurement/requests';
  return null;
}

function notificationActionLabel(type: string) {
  if (type.startsWith('invoice_')) return 'Open invoice actions';
  if (type.startsWith('payment_')) return 'Open payment actions';
  if (type.startsWith('pr_')) return 'Open purchase request';
  if (type.startsWith('po_')) return 'Open purchase order';
  if (type.includes('budget')) return 'Open budget review';
  if (type.includes('valuation')) return 'Open inventory movements';
  return 'Open related work';
}
