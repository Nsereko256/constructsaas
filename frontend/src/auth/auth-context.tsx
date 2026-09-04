import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, clearTokens, getTokens } from '@/api/client';
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
  sessionMessage: string | null;
  sessionCheckFailed: boolean;
  retrySession: () => void;
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
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
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
    retry: (count, error) => !(error instanceof ApiError && (error.status === 401 || /session has ended/i.test(error.message))) && count < 2,
  });

  const authError = meQuery.error instanceof ApiError ? meQuery.error : null;
  const sessionInvalid = Boolean(authError && (authError.status === 401 || /session has ended|signed in on another device/i.test(authError.message)));

  useEffect(() => {
    if (!meQuery.error) return;
    if (sessionInvalid) {
      clearTokens();
      setTokenVersion((value) => value + 1);
    }
  }, [meQuery.error, sessionInvalid]);

  useEffect(() => {
    const handleSessionEnded = (event: Event) => {
      queryClient.clear();
      setSessionMessage((event as CustomEvent<{ reason?: string }>).detail?.reason || 'Your session has ended. Please sign in again.');
      setTokenVersion((value) => value + 1);
    };
    window.addEventListener('construct:session-ended', handleSessionEnded);
    return () => window.removeEventListener('construct:session-ended', handleSessionEnded);
  }, [queryClient]);

  const login = useCallback(
    async (username: string, password: string, terminateOtherSession = false) => {
      await loginRequest(username, password, terminateOtherSession);
      setSessionMessage(null);
      setTokenVersion((value) => value + 1);
      await queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    const scope = offlineScope(getTokens()?.access);
    void logoutRequest();
    void clearOfflineScope(scope);
    queryClient.clear();
    setTokenVersion((value) => value + 1);
  }, [queryClient]);

  void tokenVersion;
  const value: AuthContextValue = {
    user: meQuery.data ?? null,
    role: meQuery.data?.role ?? null,
    isAuthenticated: Boolean(tokens) && !sessionInvalid && !meQuery.isError,
    isLoading: (meQuery.isLoading || (meQuery.isError && !sessionInvalid)) && Boolean(userId),
    login,
    logout,
    sessionMessage,
    sessionCheckFailed: Boolean(tokens && meQuery.isError && !sessionInvalid),
    retrySession: () => { void meQuery.refetch(); },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
