import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest, getTokens, setTokens } from './client';

vi.mock('@/pwa/offline', () => ({ cachedResponse: vi.fn(), cacheResponse: vi.fn(), offlineScope: () => 'test' }));
const response = (status: number, data: unknown) => new Response(JSON.stringify(data), { status });

describe('session recovery', () => {
  beforeEach(() => setTokens({ access: 'expired', refresh: 'refresh' }));
  afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });
  it('renews an invalid token returned as 403 and retries the request', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(403, { code: 'token_not_valid' }))
      .mockResolvedValueOnce(response(200, { access: 'renewed' }))
      .mockResolvedValueOnce(response(200, { ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiRequest('/api/users/me/')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getTokens()?.access).toBe('renewed');
  });
  it('does not refresh or clear a session for a permission denial', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(403, { detail: 'Permission denied.' }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiRequest('/api/users/me/')).rejects.toMatchObject({ status: 403 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getTokens()).not.toBeNull();
  });
});
