import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Bell, BellRing, Check, CheckCheck, CircleAlert, FileText, Info, PackageCheck, Search, Settings, WalletCards, X } from 'lucide-react';
import { useEffect, useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import type { NotificationItem } from '@/api/types';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Pagination } from '@/components/common/pagination';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate } from '@/lib/utils';
import './notifications-reference.css';

const tabs = [
  ['All', ''], ['Action required', 'action'], ['Approvals', 'approvals'],
  ['Procurement', 'procurement'], ['Inventory', 'inventory'], ['Projects', 'projects'],
] as const;

export function NotificationsPage() {
  const list = useListState({ is_read: '', category: '' });
  const notificationQuery = { ...list.query, page_size: 5 };
  const notifications = useQuery({ queryKey: qk.notifications(notificationQuery), queryFn: () => api.notifications(notificationQuery) });
  const summary = useQuery({ queryKey: ['notifications', 'summary'], queryFn: api.notificationSummary });
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
  const markRead = useMutation({ mutationFn: api.markNotificationRead, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['notifications'] }); } });
  const markAll = useMutation({
    mutationFn: api.markAllNotificationsRead,
    onSuccess: () => { toast.push({ title: 'All notifications marked as read', tone: 'success' }); void queryClient.invalidateQueries({ queryKey: ['notifications'] }); },
  });
  const stats = summary.data;
  const categories = stats?.categories || [];
  const categoryTotal = categories.reduce((total, category) => total + category.count, 0);
  const categoryColors = ['#0f777b', '#e89819', '#4f86b9', '#7a58c7', '#68757b', '#22935d'];
  let categoryStart = 0;
  const categoryGradient = categories.length ? categories.map((category, index) => {
    const start = categoryStart;
    categoryStart += (category.count / Math.max(categoryTotal, 1)) * 100;
    return `${categoryColors[index % categoryColors.length]} ${start}% ${categoryStart}%`;
  }).join(', ') : '#e4e9ea 0 100%';

  return (
    <div className="notifications-reference">
      <header className="notifications-titlebar">
        <div><p className="notifications-eyebrow">Notifications</p><h1>Notifications</h1><p>Review alerts, approvals and updates across your operations.</p></div>
        <div className="notifications-title-actions"><Button asChild variant="secondary"><Link to="/settings"><Settings className="h-4 w-4" />Notification settings</Link></Button><Button onClick={() => markAll.mutate()} disabled={markAll.isPending}><CheckCheck className="h-4 w-4" />Mark all as read</Button></div>
      </header>
      <section className="notifications-kpis" aria-label="Notification summary">
        <NotificationKpi icon={Bell} tone="teal" label="Unread" value={stats?.unread ?? 0} detail={`${stats?.today ?? 0} new today`} />
        <NotificationKpi icon={AlertTriangle} tone="amber" label="Action required" value={stats?.action_required ?? 0} detail="Needs your attention" />
        <NotificationKpi icon={Check} tone="green" label="Approvals" value={stats?.approvals ?? 0} detail="Awaiting approval" />
        <NotificationKpi icon={Info} tone="blue" label="System updates" value={stats?.system_updates ?? 0} detail="Information only" />
      </section>
      <div className="notifications-workspace-grid">
        <section className="notifications-register">
          <div className="notifications-panel-heading"><h2>All notifications</h2><span>{stats?.total ?? 0} total</span></div>
          <nav className="notifications-tabs" aria-label="Notification filters">
            {tabs.map(([label, value]) => <button key={value || 'all'} type="button" className={list.filters.category === value ? 'active' : ''} onClick={() => list.setFilter('category', value)}>{label}{value && stats ? <b>{value === 'action' ? stats.action_required : value === 'approvals' ? stats.approvals : categoryCount(categories, label)}</b> : stats ? <b>{stats.total}</b> : null}</button>)}
          </nav>
          <div className="notifications-filters"><label><Search className="h-4 w-4" /><input value={list.search} onChange={(event) => list.setSearch(event.target.value)} placeholder="Search notifications" aria-label="Search notifications" />{list.search ? <button type="button" aria-label="Clear notification search" onClick={() => list.setSearch('')}><X className="h-3.5 w-3.5" /></button> : null}</label><select value={list.filters.is_read} onChange={(event) => list.setFilter('is_read', event.target.value)} aria-label="Notification status"><option value="">All types</option><option value="false">Unread only</option><option value="true">Read only</option></select><label className="notifications-switch"><input type="checkbox" checked={list.filters.is_read === 'false'} onChange={(event) => list.setFilter('is_read', event.target.checked ? 'false' : '')} /><span>Unread only</span></label></div>
          <div className="notifications-list">
            {(notifications.data?.results || []).map((item) => <NotificationRow key={item.id} item={item} onOpen={() => { setSelected(item); if (!item.is_read) markRead.mutate(item.id); }} />)}
            {!notifications.data?.results.length ? <p className="notifications-empty">No notifications match this view.</p> : null}
          </div>
          <Pagination page={list.page} setPage={list.setPage} data={notifications.data} pageSize={5} />
        </section>
        <aside className="notifications-side-column">
          <section className="notifications-side-panel"><div className="notifications-panel-heading"><h2>Priority queue</h2><span className="notifications-side-link">{stats?.priority.filter((item) => item.count > 0).reduce((total, item) => total + item.count, 0) ?? 0} open</span></div>{(stats?.priority || []).map((item) => <button key={item.label} type="button" className="notifications-priority-row" onClick={() => list.setFilter('category', priorityCategory(item.label))}><span className={`notifications-priority-icon ${item.tone}`}><PriorityIcon label={item.label} /></span><span><strong>{item.label}</strong><small>{item.detail}</small></span><b>{item.count}</b><Badge tone={item.tone === 'urgent' ? 'danger' : item.tone === 'high' ? 'warning' : item.tone === 'medium' ? 'info' : 'neutral'}>{item.tone === 'neutral' ? '—' : item.tone[0].toUpperCase() + item.tone.slice(1)}</Badge></button>)}</section>
          <section className="notifications-side-panel notifications-summary-panel"><div className="notifications-panel-heading"><h2>Notification summary</h2><Link to="/notifications">View all</Link></div><div className="notifications-summary-body"><div className="notifications-donut" style={{ background: categoryGradient } as CSSProperties}><div><strong>{stats?.total ?? 0}</strong><small>Total</small></div></div><div className="notifications-category-list">{categories.map((category, index) => <div key={category.label}><span><i style={{ background: categoryColors[index % categoryColors.length] }} />{category.label}</span><b>{category.count}</b><small>{Math.round((category.count / Math.max(stats?.total || 1, 1)) * 100)}%</small></div>)}</div></div></section>
          <section className="notifications-side-panel notifications-delivery-panel"><div className="notifications-panel-heading"><h2>Delivery preferences</h2><Link to="/settings">Manage</Link></div><div className="notifications-preference-row"><span className="notifications-preference-icon"><BellRing className="h-4 w-4" /></span><span><strong>Push notifications</strong><small>Receive in-app notifications</small></span><Badge tone={pushEnabled ? 'success' : 'neutral'}>{pushEnabled ? 'On' : 'Off'}</Badge></div><div className="notifications-preference-actions"><Button size="sm" variant={pushEnabled ? 'secondary' : 'default'} onClick={() => void togglePush()} disabled={pushBusy || !pushAvailable}>{pushEnabled ? 'Turn off' : 'Turn on'}</Button>{pushEnabled ? <Button size="sm" variant="ghost" onClick={() => void testPush()} disabled={pushBusy}>Test</Button> : null}{!pushAvailable ? <small>Browser push is unavailable.</small> : null}</div></section>
        </aside>
      </div>
      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}><DialogContent title={selected?.title || 'Notification'} description={selected ? formatDate(selected.created_at) : undefined}>{selected ? <div className="grid gap-4"><div className="flex items-center gap-2"><NotificationIcon level={selected.level} /><Badge tone={statusTone(selected.level)}>{selected.level}</Badge>{!selected.is_read ? <Badge tone="info">New</Badge> : null}</div><div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3"><Detail label="Received" value={formatDate(selected.created_at)} /><Detail label="Category" value={notificationLabel(selected.notification_type)} /><Detail label="State" value={selected.is_read ? 'Read' : 'Unread'} /></div><p className="whitespace-pre-wrap text-sm leading-6 text-foreground">{selected.message}</p><div className="flex flex-col gap-2 sm:flex-row">{!selected.is_read ? <Button variant="secondary" onClick={() => markRead.mutate(selected.id)}>Mark as read</Button> : null}{notificationDestination(selected) ? <Button asChild><Link to={notificationDestination(selected)!} onClick={() => setSelected(null)}>{notificationActionLabel(selected.notification_type)} <span aria-hidden="true">→</span></Link></Button> : null}</div></div> : null}</DialogContent></Dialog>
    </div>
  );
}

function NotificationKpi({ icon: Icon, tone, label, value, detail }: { icon: typeof Bell; tone: string; label: string; value: number; detail: string }) { return <div className={`notifications-kpi ${tone}`}><span className="notifications-kpi-icon"><Icon className="h-6 w-6" /></span><span><p>{label}</p><strong>{value}</strong><small>{detail}</small></span></div>; }
function NotificationRow({ item, onOpen }: { item: NotificationItem; onOpen: () => void }) { return <button type="button" onClick={onOpen} className={`notifications-row ${item.is_read ? 'read' : 'unread'}`}><span className="notifications-row-icon"><NotificationIcon level={item.level} />{!item.is_read ? <i aria-label="Unread" /> : null}</span><span className="notifications-row-content"><span className="notifications-row-title"><strong>{item.title}</strong><small>{formatDate(item.created_at)}</small></span><span className="notifications-row-message">{item.message}</span></span><span className="notifications-row-action">{item.is_read ? <span>View</span> : <span className="review">Review</span>}</span></button>; }
function PriorityIcon({ label }: { label: string }) { if (label.includes('Stock')) return <PackageCheck className="h-4 w-4" />; if (label.includes('Budget')) return <Check className="h-4 w-4" />; if (label.includes('Other')) return <WalletCards className="h-4 w-4" />; return <FileText className="h-4 w-4" />; }
function priorityCategory(label: string) { if (label.includes('Stock')) return 'inventory'; if (label.includes('Budget')) return 'projects'; if (label.includes('Other')) return 'approvals'; return 'procurement'; }
function categoryCount(categories: { label: string; count: number }[], label: string) { return categories.find((category) => category.label === label)?.count ?? 0; }
function urlBase64ToUint8Array(value: string) { const padded = `${value}${'='.repeat((4 - (value.length % 4)) % 4)}`.replace(/-/g, '+').replace(/_/g, '/'); return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0)); }
function NotificationIcon({ level }: { level: string }) { if (level === 'danger') return <CircleAlert className="h-5 w-5 shrink-0 text-critical" aria-label="Critical" />; if (level === 'warning') return <AlertTriangle className="h-5 w-5 shrink-0 text-warning" aria-label="Warning" />; if (level === 'success') return <Check className="h-5 w-5 shrink-0 text-success-foreground" aria-label="Success" />; return <Info className="h-5 w-5 shrink-0 text-info" aria-label="Information" />; }
function Detail({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-border bg-background px-2.5 py-2"><span className="block text-[10px] font-bold uppercase tracking-wide text-muted">{label}</span><strong className="mt-0.5 block truncate text-xs text-foreground" title={value}>{value}</strong></div>; }
function notificationLabel(notificationType: string) { return notificationType.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function notificationDestination(item: { notification_type: string; link: string }) { if (item.link.startsWith('/') && !item.link.startsWith('/api/')) return item.link; if (item.notification_type === 'low_stock') return '/inventory'; if (item.notification_type.includes('budget_approval') && item.link.includes('/budgets/')) return '/finance/budgets'; if (item.notification_type.startsWith('pr_') || item.notification_type.includes('budget_approval')) return '/procurement/requests'; if (item.notification_type === 'po_created') return '/procurement/purchase-orders'; if (item.notification_type === 'po_received') return '/procurement/grns'; if (item.notification_type.startsWith('invoice_')) return '/finance/payables'; if (item.notification_type.startsWith('payment_')) return '/finance/payments'; if (item.notification_type === 'staff_advance_overdue') return '/finance/expenses'; if (item.notification_type === 'valuation_adjustment') return '/inventory/movements'; if (item.notification_type === 'journal_posting_failure') return '/finance/reports'; if (item.notification_type === 'po_exceeding_budget') return '/procurement/requests'; return null; }
function notificationActionLabel(type: string) { if (type.startsWith('invoice_')) return 'Open invoice actions'; if (type.startsWith('payment_')) return 'Open payment actions'; if (type.startsWith('pr_')) return 'Open purchase request'; if (type.startsWith('po_')) return 'Open purchase order'; if (type.includes('budget')) return 'Open budget review'; if (type.includes('valuation')) return 'Open inventory movements'; return 'Open related work'; }
