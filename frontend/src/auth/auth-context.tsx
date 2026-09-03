import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { clearTokens, getTokens } from '@/api/client';
import { clearOfflineScope, offlineScope } from '@/pwa/offline';
import { api, login as loginRequest, logout as logoutRequest } from '@/api/services';
import type { Role, User } from '@/api/types';
import { qk } from '@/api/queryKeys';

type AuthContextValue = {
  user: User | null;
  role: Role | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string, terminateOtherSession?: boolean) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function decodeUserId(access: string) {
  try {
    const [, payload] = access.split('.');
    const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/'))) as { user_id?: number };
    return json.user_id;
  } catch {
    return undefined;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [tokenVersion, setTokenVersion] = useState(0);
  const queryClient = useQueryClient();
  const tokens = getTokens();
  const userId = tokens?.access ? decodeUserId(tokens.access) : undefined;

  const meQuery = useQuery({
    queryKey: qk.me,
    queryFn: async () => {
      if (!userId) return null;
      return api.me();
    },
    enabled: Boolean(userId),
    retry: false,
  });

  useEffect(() => {
    if (!meQuery.error) return;
    clearTokens();
    setTokenVersion((value) => value + 1);
  }, [meQuery.error]);

  useEffect(() => {
    const handleSessionEnded = () => {
      queryClient.clear();
      setTokenVersion((value) => value + 1);
    };
    window.addEventListener('construct:session-ended', handleSessionEnded);
    return () => window.removeEventListener('construct:session-ended', handleSessionEnded);
  }, [queryClient]);

  const login = useCallback(
    async (username: string, password: string, terminateOtherSession = false) => {
      await loginRequest(username, password, terminateOtherSession);
      setTokenVersion((value) => value + 1);
      await queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    const scope = offlineScope(getTokens()?.access);
    logoutRequest();
    void clearOfflineScope(scope);
    queryClient.clear();
    setTokenVersion((value) => value + 1);
  }, [queryClient]);

  void tokenVersion;
  const value: AuthContextValue = {
    user: meQuery.data ?? null,
    role: meQuery.data?.role ?? null,
    isAuthenticated: Boolean(tokens) && !meQuery.error,
    isLoading: meQuery.isLoading && Boolean(userId),
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
