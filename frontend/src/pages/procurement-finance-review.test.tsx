import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceReviewModal } from './procurement-requests';
import { financeApi } from '@/modules/finance/api';
import type { PurchaseRequest } from '@/modules/procurement/types';

vi.mock('@/modules/finance/api', () => ({ financeApi: { budgets: vi.fn(), settings: vi.fn() } }));
const request = { id: 1, number: 'MR-TEST', project: null, finance_budget_line: null, total_estimated_cost: '999999', finance_requested_amount: '6000' } as unknown as PurchaseRequest;
function mount(record = request, role = 'finance_manager', submit = vi.fn()) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><FinanceReviewModal request={record} pending={false} role={role} onClose={vi.fn()} onSubmit={submit} /></QueryClientProvider>);
}
describe('Finance review readiness', () => {
  beforeEach(() => {
    vi.mocked(financeApi.budgets).mockResolvedValue({ count: 0, results: [], next: null, previous: null });
    vi.mocked(financeApi.settings).mockResolvedValue({ count: 1, results: [{ budget_control_mode: 'warn' }], next: null, previous: null } as Awaited<ReturnType<typeof financeApi.settings>>);
  });
  it('shows the actual submitted amount, not the MR estimate', async () => {
    mount();
    expect(await screen.findByText(/UGX.*6,000/)).toBeInTheDocument();
    expect(screen.queryByText(/999,999/)).not.toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'Confirm finance decision' });
    expect(submit).toBeDisabled();
    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Approve this documented QA exception.' } });
    await waitFor(() => expect(submit).toBeEnabled());
  });
  it('blocks approval when the submitted amount is unavailable', async () => {
    mount({ ...request, finance_requested_amount: undefined });
    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'An explanation cannot replace missing data.' } });
    expect(screen.getByRole('button', { name: 'Confirm finance decision' })).toBeDisabled();
  });
  it('does not offer a bypass of the company block policy', async () => {
    vi.mocked(financeApi.settings).mockResolvedValue({ count: 1, results: [{ budget_control_mode: 'block' }], next: null, previous: null } as Awaited<ReturnType<typeof financeApi.settings>>);
    mount();
    expect(await screen.findByText(/Company policy blocks approval/)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm finance decision' })).toBeDisabled();
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'return' } });
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Please arrange the approved budget line.' } });
    expect(screen.getByRole('button', { name: 'Confirm finance decision' })).toBeEnabled();
  });
  it('passes a separate controlled Admin reason instead of dropping it', async () => {
    const submit = vi.fn(); mount({ ...request, finance_admin_override_required: true }, 'admin', submit);
    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.change(screen.getByRole('textbox', { name: 'Review comments required' }), { target: { value: 'Approve the documented budget exception.' } });
    const button = screen.getByRole('button', { name: 'Confirm finance decision' });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: 'Admin override reason required' }), { target: { value: 'Isolated QA Admin decision.' } });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(submit).toHaveBeenCalledWith('approve', 'Approve the documented budget exception.', true, 'Isolated QA Admin decision.');
  });
  it('explains independent-review policy before the user submits', async () => {
    mount({ ...request, finance_review_requires_independent_reviewer: true });
    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'This comment cannot override maker-checker.' } });
    expect(screen.getByRole('button', { name: 'Confirm finance decision' })).toBeDisabled();
    expect(screen.getByText(/requires a different Finance reviewer/)).toBeInTheDocument();
  });
});
