import type { ApiErrorPayload, Paginated } from './types';
import { cachedResponse, cacheResponse, offlineScope } from '@/pwa/offline';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

type Tokens = {
  access: string;
  refresh: string;
};

type ApiRequestInit = Omit<RequestInit, 'body'> & {
  body?: unknown;
};

const ACCESS_KEY = 'construct.access';
const REFRESH_KEY = 'construct.refresh';

export class ApiError extends Error {
  status: number;
  payload: ApiErrorPayload | null;

  constructor(message: string, status: number, payload: ApiErrorPayload | null) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

export function getTokens(): Tokens | null {
  const access = sessionStorage.getItem(ACCESS_KEY);
  const refresh = sessionStorage.getItem(REFRESH_KEY);
  return access && refresh ? { access, refresh } : null;
}

export function setTokens(tokens: Tokens) {
  sessionStorage.setItem(ACCESS_KEY, tokens.access);
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh);
}

export function clearTokens() {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}

function endLocalSession(reason = 'Your session has expired. Please sign in again.') {
  clearTokens();
  window.dispatchEvent(new CustomEvent('construct:session-ended', { detail: { reason } }));
}

function apiUrl(path: string) {
  if (path.startsWith('http')) return path;
  return `${API_BASE_URL}${path}`;
}

function scopedPath(path: string) {
  if (typeof window === 'undefined' || !path.startsWith('/api/')) return path;
  const siteId = window.localStorage.getItem('construct.active-project-site');
  if (!siteId) return path;
  return `${path}${path.includes('?') ? '&' : '?'}project_site=${encodeURIComponent(siteId)}`;
}

function errorMessage(payload: ApiErrorPayload | null, fallback: string) {
  if (!payload) return fallback;
  if ('message' in payload && typeof payload.message === 'string') return payload.message;
  if ('detail' in payload && typeof payload.detail === 'string') return payload.detail;
  const firstValue = Object.values(payload)[0];
  if (Array.isArray(firstValue)) return firstValue.join(', ');
  if (typeof firstValue === 'string') return firstValue;
  if (firstValue && typeof firstValue === 'object') {
    const nested = Object.values(firstValue)[0];
    if (Array.isArray(nested)) return nested.join(', ');
    if (typeof nested === 'string') return nested;
  }
  return fallback;
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
  const tokens = getTokens();
  if (!tokens?.refresh) return null;
  try {
    const response = await fetch(apiUrl('/api/token/refresh/'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ refresh: tokens.refresh }),
    });
    if (!response.ok) {
      endLocalSession('Your session expired or was ended on another device. Please sign in again.');
      return null;
    }
    const data = (await response.json()) as { access: string; refresh?: string };
    setTokens({ access: data.access, refresh: data.refresh || tokens.refresh });
    return data.access;
  } catch {
    return null;
  }
  })();
  try { return await refreshPromise; } finally { refreshPromise = null; }
}

export async function apiRequest<T>(path: string, init: ApiRequestInit = {}, retry = true): Promise<T> {
  const requestPath = (init.method || 'GET').toUpperCase() === 'GET' ? scopedPath(path) : path;
  const tokens = getTokens();
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (!(init.body instanceof FormData) && init.body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }
  if (tokens?.access) headers.set('Authorization', `Bearer ${tokens.access}`);
  const requestBody = init.body && !(init.body instanceof FormData) && typeof init.body !== 'string' ? JSON.stringify(init.body) : init.body;

  let response: Response;
  try { response = await fetch(apiUrl(requestPath), {
    ...init,
    headers,
    body: requestBody as BodyInit | null | undefined,
  }); } catch {
    if ((init.method || 'GET').toUpperCase() === 'GET') {
      const cached = await cachedResponse<T>(offlineScope(tokens?.access), requestPath);
      if (cached !== undefined) return cached;
    }
    throw new ApiError(
      'Cannot reach the server. Check your internet connection, then reopen the latest public link. If you are using a temporary demo link, it may have expired.',
      0,
      null,
    );
  }

  if (response.status === 401 && retry) {
    const nextAccess = await refreshAccessToken();
    if (nextAccess) return apiRequest<T>(path, init, false);
  }

  const text = await response.text();
  let payload: ApiErrorPayload | null = null;
  if (text) {
    try {
      payload = JSON.parse(text) as ApiErrorPayload;
    } catch {
      const message = response.ok
        ? 'The server returned an unexpected response. Please refresh and try again.'
        : 'The server could not process this request. Please try again or contact an administrator.';
      throw new ApiError(message, response.status, null);
    }
  }
  const message = errorMessage(payload, response.statusText);
  if (!response.ok && /session has ended|signed in on another device/i.test(message)) endLocalSession();
  if (!response.ok) throw new ApiError(message, response.status, payload);
  if ((init.method || 'GET').toUpperCase() === 'GET') void cacheResponse(offlineScope(tokens?.access), requestPath, payload);
  return payload as T;
}

export function pageParams(params: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  });
  const qs = query.toString();
  return qs ? `?${qs}` : '';
}

export function emptyPage<T>(): Paginated<T> {
  return { count: 0, next: null, previous: null, results: [] };
}

export async function apiDownload(path: string, filename: string, retry = true) {
  const headers = new Headers({ Accept: '*/*' });
  const tokens = getTokens();
  if (tokens?.access) headers.set('Authorization', `Bearer ${tokens.access}`);

  let response: Response;
  try {
    response = await fetch(apiUrl(path), { headers });
  } catch {
    throw new ApiError(
      'Cannot reach the server. Check your internet connection, then try the download again.',
      0,
      null,
    );
  }

  if (response.status === 401 && retry) {
    const nextAccess = await refreshAccessToken();
    if (nextAccess) return apiDownload(path, filename, false);
  }

  if (!response.ok) {
    const text = await response.text();
    let payload: ApiErrorPayload | null = null;
    if (text) {
      try { payload = JSON.parse(text) as ApiErrorPayload; } catch { /* non-JSON error */ }
    }
    const message = errorMessage(payload, response.statusText || 'Download failed');
    if (/session has ended|signed in on another device/i.test(message)) endLocalSession();
    throw new ApiError(message, response.status, payload);
  }

  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
