import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Bell, ChevronsLeft, HardHat, LogOut, Menu, ShieldCheck, Wifi, WifiOff } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { visibleNav } from './navigation';
import { ActionCentre } from './action-centre';
import { useSiteScope } from '@/context/site-scope';

export function AppShell() {
  const { user, role, logout } = useAuth();
  const { sites, site, siteId, setSiteId, isLoading: sitesLoading } = useSiteScope();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [online, setOnline] = useState(() => navigator.onLine);
  const location = useLocation();
  const nav = useMemo(() => visibleNav(role), [role]);
  const currentNav = [...nav].sort((a, b) => b.href.length - a.href.length).find((item) =>
    item.href === '/dashboard' ? location.pathname === item.href : location.pathname.startsWith(item.href),
  );
  const unread = useQuery({ queryKey: qk.unreadCount, queryFn: api.unreadCount, refetchInterval: 30000 });
  const workflowBadges = useQuery({ queryKey: qk.workflowBadges, queryFn: api.workflowBadges, refetchInterval: 30000 });
  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);
  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[min(82vw,296px)] flex-col border-r border-sidebar-border bg-sidebar py-3 text-white transition-all md:w-auto md:translate-x-0',
          collapsed ? 'md:!w-[62px]' : 'md:!w-[170px]',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-center gap-2 px-2.5">
          <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-primary text-white"><HardHat className="h-3.5 w-3.5" /></div>
          {!collapsed ? (
            <div className="min-w-0">
              <strong className="block truncate font-display text-[11px]">ConstructSaaS</strong>
              <span className="block truncate text-[9px] uppercase tracking-wide text-white/60">NM Pro</span>
            </div>
          ) : null}
        </div>
        <nav className="mt-5 grid gap-0.5 overflow-auto px-2 pb-4 scrollbar-thin">
          {nav.map((item, index) => {
            const badgeCount = item.href === '/notifications'
              ? unread.data?.unread_count || 0
              : item.badgeKey ? workflowBadges.data?.[item.badgeKey] || 0 : 0;
            return (
            <div key={item.href}>
              {!collapsed && item.section && item.section !== nav[index - 1]?.section ? (
                <p className="mb-1 mt-4 px-2 text-[9px] font-semibold uppercase tracking-widest text-white/50 first:mt-0">{item.section}</p>
              ) : null}
            <NavLink
              to={item.href}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                cn(
                'relative flex min-h-9 items-center gap-2 rounded-md px-2 py-1.5 text-xs text-white/85 transition-colors hover:bg-white/10 hover:text-white',
                  isActive && 'bg-sidebar-accent font-medium text-white',
                )
              }
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed ? <span>{item.label}</span> : null}
              {badgeCount > 0 ? (
                <span
                  className={cn(
                    'ml-auto min-w-5 border border-white/25 bg-white px-1 text-center text-[10px] font-black leading-5 text-sidebar',
                    collapsed && 'absolute right-1 top-1 ml-0 min-w-4 px-0.5 leading-4',
                  )}
                  aria-label={`${badgeCount} pending ${item.label.toLowerCase()}`}
                >
                  {badgeCount > 99 ? '99+' : badgeCount}
                </span>
              ) : null}
            </NavLink>
            </div>
          ); })}
        </nav>
        <div className="mt-auto border-t border-sidebar-border p-2">
          <Button className="hidden w-full border-white/10 bg-transparent text-white hover:bg-white/10 md:inline-flex" onClick={() => setCollapsed((v) => !v)}>
            <ChevronsLeft className={cn('h-4 w-4', collapsed && 'rotate-180')} />
            {!collapsed ? 'Collapse' : null}
          </Button>
        </div>
      </aside>

      <div className={cn('transition-all', collapsed ? 'md:pl-[62px]' : 'md:pl-[170px]')}>
        <header className="sticky top-0 z-30 flex min-h-[48px] items-center gap-2 border-b border-border bg-white/95 px-3 backdrop-blur sm:gap-3 sm:px-5">
          <Button variant="ghost" size="sm" className="md:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
            <Menu className="h-5 w-5" />
          </Button>
          {currentNav ? <div className="min-w-0"><p className="hidden text-[10px] font-bold uppercase tracking-[0.14em] text-muted sm:block">ConstructSaaS</p><p className="truncate text-sm font-bold sm:text-base">{currentNav.label}</p></div> : null}
          <div className="ml-auto" />
          <label className="flex min-w-0 items-center gap-2 text-xs">
            <span className="sr-only">Active site</span>
            <select aria-label="Active site" className="max-w-[180px] rounded-md border border-border bg-white px-2 py-1.5 text-xs" value={siteId || ''} onChange={(event) => setSiteId(event.target.value ? Number(event.target.value) : null)} disabled={sitesLoading}>
              <option value="">All sites</option>
              {sites.map((item) => <option key={item.id} value={item.id}>{item.project_name} · {item.name}</option>)}
            </select>
          </label>
          <div className={cn('hidden h-9 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium sm:inline-flex', online ? 'border-[#B9DEC8] bg-[#EFF9F1] text-[#2E6944]' : 'border-[#E5CC8E] bg-[#FFF8E7] text-[#7A5D1B]')}>
            {online ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
            {online ? 'Online' : 'Offline'}
          </div>
          <NavLink to="/notifications" aria-label={`Notifications${unread.data?.unread_count ? `, ${unread.data.unread_count} unread` : ''}`} className="relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-border transition-colors hover:bg-[#EEF2F6]">
            <Bell className="h-4 w-4" />
            {unread.data?.unread_count ? (
              <span className="absolute -right-2 -top-2 rounded-md bg-critical px-1.5 text-xs font-bold text-white">{unread.data.unread_count}</span>
            ) : null}
          </NavLink>
          <div className="hidden items-center gap-2 lg:flex"><span className="grid h-8 w-8 place-items-center rounded-full bg-[#5C322E] text-xs font-bold text-white">{(user?.first_name || user?.username || 'U').slice(0, 1).toUpperCase()}</span><div className="text-right text-xs"><strong className="block">{user?.username}</strong><span className="inline-flex items-center gap-1 text-muted"><ShieldCheck className="h-3 w-3" />{user?.role_display}</span></div></div>
          <Button variant="ghost" size="sm" className="px-2 sm:px-3" onClick={logout} aria-label="Logout"><LogOut className="h-4 w-4" /><span className="hidden sm:inline">Logout</span></Button>
        </header>
        <main className="app-sheen min-h-[calc(100vh-4rem)] min-w-0 p-2.5 sm:p-4 md:px-5 md:py-2"><div className="mx-auto max-w-[1600px]">
          {site ? <div className="mb-3 rounded-md border border-info/20 bg-info/5 px-3 py-2 text-xs text-info">Site scope: <strong>{site.project_name} · {site.name}</strong>. Use “All sites” to return to the company view.</div> : null}
          {location.pathname !== '/dashboard' && !location.pathname.startsWith('/projects') ? <ActionCentre role={role} workflow={workflowBadges.data} /> : null}
          <Outlet />
        </div></main>
      </div>

      {mobileOpen ? <button className="fixed inset-0 z-30 bg-sidebar/40 md:hidden" aria-label="Close navigation" onClick={() => setMobileOpen(false)} /> : null}
    </div>
  );
}
