import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/services';
import type { ProjectSite } from '@/api/types';
import { useAuth } from '@/auth/auth-context';

type SiteScopeValue = { sites: ProjectSite[]; siteId: number | null; site: ProjectSite | null; setSiteId: (siteId: number | null) => void; isLoading: boolean };
const SiteScopeContext = createContext<SiteScopeValue | null>(null);
const STORAGE_KEY = 'construct.active-project-site';

export function SiteScopeProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const [siteId, setSiteIdState] = useState<number | null>(() => { const stored = window.localStorage.getItem(STORAGE_KEY); return stored ? Number(stored) || null : null; });
  const sitesQuery = useQuery({ queryKey: ['project-sites', 'global-scope'], queryFn: () => api.projectSites({ is_active: true, page_size: 200 }), staleTime: 60_000, enabled: isAuthenticated });
  const sites = useMemo(() => sitesQuery.data?.results || [], [sitesQuery.data]);
  const site = sites.find((item) => item.id === siteId) || null;
  useEffect(() => { if (siteId && isAuthenticated && !sitesQuery.isLoading && sites.length && !site) setSiteIdState(null); }, [isAuthenticated, site, siteId, sites, sitesQuery.isLoading]);
  const value = useMemo(() => ({ sites, siteId: site?.id || null, site, isLoading: sitesQuery.isLoading, setSiteId: (next: number | null) => { setSiteIdState(next); if (next) window.localStorage.setItem(STORAGE_KEY, String(next)); else window.localStorage.removeItem(STORAGE_KEY); window.dispatchEvent(new Event('construct:site-scope-changed')); void queryClient.refetchQueries({ type: 'all' }); } }), [queryClient, site, sites, sitesQuery.isLoading]);
  return <SiteScopeContext.Provider value={value}>{children}</SiteScopeContext.Provider>;
}

export function useSiteScope() { const value = useContext(SiteScopeContext); if (!value) throw new Error('useSiteScope must be used inside SiteScopeProvider'); return value; }
