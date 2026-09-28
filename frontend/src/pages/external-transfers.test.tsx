import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ExternalTransferDetailPage, ExternalTransfersPage } from './external-transfers';
import { externalTransfers } from '@/api/external-transfers';

const auth = vi.hoisted(() => ({ role: 'admin' }));
vi.mock('@/auth/auth-context', () => ({ useAuth: () => auth }));
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ push: vi.fn() }) }));
vi.mock('@/api/external-transfers', async () => {
  const actual = await vi.importActual<typeof import('@/api/external-transfers')>('@/api/external-transfers');
  return { ...actual, allChoices: vi.fn().mockResolvedValue([]), externalTransfers: { list: vi.fn(), detail: vi.fn(), create: vi.fn(), action: vi.fn() } };
});
function mount(detail = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[detail ? '/inventory/external-transfers/1' : '/inventory/external-transfers']}><Routes><Route path="/inventory/external-transfers" element={<ExternalTransfersPage />} /><Route path="/inventory/external-transfers/:id" element={<ExternalTransferDetailPage />} /></Routes></MemoryRouter></QueryClientProvider>);
}
const fixture = {
  id: 1, sender: 'Partner', reference: 'MOVE-1', ownership: 'BORROWED' as const, warehouse: 1, warehouse_name: 'Warehouse',
  expected_date: '2026-09-25', return_due_date: '2026-09-30', notes: '', closed: false, created_at: '', created_by_name: 'Storekeeper', status: 'Awaiting admin', pending_receipts: 1,
  lines: [{ id: 1, material: 1, material_name: 'Cement', material_code: 'C', unit: 'bag', bin_code: '', quantity: '10', unit_cost: '0', received: '0', pending: '10', remaining: '0', held: '0', outstanding: '0', returned: '0', projects: {}, events: [] }],
  receipts: [{ id: 1, reference: 'DEL-1', status: 'PENDING' as const, received_date: '2026-09-25', received_by: 'Storekeeper', reviewed_by: '', reviewed_at: null, review_reason: '', notes: '', lines: [{ order_line: 1, accepted: '10', damaged: '0', rejected: '0', posted_unit_cost: null }] }],
};
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); vi.clearAllMocks(); auth.role = 'admin'; vi.mocked(externalTransfers.list).mockResolvedValue({ count: 0, next: null, previous: null, results: [] }); vi.mocked(externalTransfers.detail).mockResolvedValue(fixture); });
afterEach(() => vi.unstubAllGlobals());
describe('External transfers', () => {
  it('shows ownership guidance, five-per-page register and a usable creation form', async () => {
    mount();
    await screen.findByText('No external transfers');
    expect(externalTransfers.list).toHaveBeenCalledWith(expect.objectContaining({ page_size: 5 }));
    fireEvent.click(screen.getByRole('button', { name: 'New move order' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('No stock or invoice is created');
    fireEvent.change(screen.getAllByRole('combobox', { name: /Ownership/ }).at(-1)!, { target: { value: 'BORROWED' } });
    expect(screen.getByLabelText(/Return due date/)).toBeRequired();
    expect(screen.queryByLabelText(/Proposed unit value/)).not.toBeInTheDocument();
  });
  it('does not request or expose this priced workflow to engineers', () => {
    auth.role = 'site_engineer'; mount();
    expect(externalTransfers.list).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'New move order' })).not.toBeInTheDocument();
  });
  it('requires an explicit admin review form before posting', async () => {
    mount(true);
    await screen.findByRole('heading', { name: 'Move order MO-1' });
    fireEvent.click(screen.getByRole('button', { name: 'Review & post' }));
    expect(externalTransfers.action).not.toHaveBeenCalled();
    const reason = screen.getByLabelText(/Authorization \/ reason/);
    expect(reason).toHaveAttribute('minLength', '10');
    fireEvent.change(reason, { target: { value: 'Count and ownership verified.' } });
    vi.mocked(externalTransfers.action).mockResolvedValue(fixture);
    fireEvent.click(screen.getByRole('button', { name: 'Approve & post' }));
    await waitFor(() => expect(externalTransfers.action).toHaveBeenCalledWith(1, 'review', expect.objectContaining({ receipt_id: 1, decision: 'post', reason: 'Count and ownership verified.' })));
  });
  it('keeps posting controls away from the receiving storekeeper', async () => {
    auth.role = 'storekeeper'; mount(true);
    await screen.findByRole('heading', { name: 'Move order MO-1' });
    expect(screen.queryByRole('button', { name: 'Review & post' })).not.toBeInTheDocument();
  });
});
