import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProcurementRequestsPage } from './procurement-requests';
import { api } from '@/modules/procurement/api';

vi.mock('@/auth/auth-context', () => ({ useAuth: () => ({ role: 'admin', user: { id: 1 } }) }));
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ push: vi.fn() }) }));
vi.mock('@/modules/procurement/api', async () => {
  const actual = await vi.importActual<typeof import('@/modules/procurement/api')>('@/modules/procurement/api');
  return { api: { ...actual.api, purchaseRequests: vi.fn(), purchaseRequestSummary: vi.fn(), projects: vi.fn() } };
});
function mount() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><ProcurementRequestsPage /></MemoryRouter></QueryClientProvider>);
}
describe('Material request register', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
    vi.mocked(api.projects).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(api.purchaseRequests).mockResolvedValue({ count: 103, next: '/next', previous: null, results: [] });
    vi.mocked(api.purchaseRequestSummary).mockResolvedValue({ count: 103, statuses: {}, my_queue: 10, awaiting_approval: 8, urgent_approval: 2, stock_queue: 2, stock_fulfilled: 5, estimated_value: '6000' });
  });
  afterEach(() => vi.unstubAllGlobals());
  it('uses full server counts and ordering rather than loading a hundred records', async () => {
    mount();
    expect(await screen.findByRole('button', { name: /^All\s*103$/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^My queue\s*10$/ })).toBeInTheDocument();
    expect(api.purchaseRequests).toHaveBeenCalledWith(expect.objectContaining({ page_size: 5, ordering: 'queue_rank,created_at,id' }));
    expect(vi.mocked(api.purchaseRequests).mock.calls.every(([params]) => (params as { page_size: number }).page_size === 5)).toBe(true);
    fireEvent.change(screen.getByRole('combobox', { name: 'Sort material requests' }), { target: { value: 'newest' } });
    await waitFor(() => expect(api.purchaseRequests).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, ordering: '-created_at,-id' })));
  });
  it('stock tab and status filters cannot silently conflict', async () => {
    mount();
    fireEvent.click(await screen.findByRole('button', { name: /^Stock issue\s*2$/ }));
    await waitFor(() => expect(api.purchaseRequests).toHaveBeenLastCalledWith(expect.objectContaining({ register_queue: 'stock', status: '', action_queue: '' })));
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter material requests by status' }), { target: { value: 'RETURNED' } });
    await waitFor(() => expect(api.purchaseRequests).toHaveBeenLastCalledWith(expect.objectContaining({ register_queue: '', status: 'RETURNED' })));
  });
});
