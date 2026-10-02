import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WarehouseForm } from './warehouse-form';
import { ImportWarehouseSetup } from './import-warehouse-setup';
import { api } from '@/api/services';
const actor = vi.hoisted(() => ({ role: 'admin' }));
vi.mock('@/auth/auth-context', () => ({ useAuth: () => actor }));
vi.mock('@/api/services', () => ({ api: { saveWarehouse: vi.fn(), companyWarehouses: vi.fn() } }));
const saved = vi.fn();
function wrap(ui: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>{ui}</QueryClientProvider>); }
beforeEach(() => { vi.clearAllMocks(); actor.role = 'admin'; vi.mocked(api.companyWarehouses).mockResolvedValue({ count: 0, results: [], next: null, previous: null }); });
describe('Warehouse onboarding', () => {
  it('normalizes input and saves the first receiving warehouse', async () => {
    vi.mocked(api.saveWarehouse).mockResolvedValue({ id: 1, name: 'Main', code: 'MAIN', location: '', is_default: true, is_active: true, project: null, project_name: null });
    wrap(<WarehouseForm defaultWarehouse onSaved={saved} onCancel={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Register warehouse' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: /Warehouse name/ }), { target: { value: ' Main ' } });
    fireEvent.change(screen.getByRole('textbox', { name: /Warehouse code/ }), { target: { value: ' main ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Register warehouse' }));
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    expect(api.saveWarehouse).toHaveBeenCalledWith({ name: 'Main', code: 'MAIN', location: '', is_default: true, is_active: true }, undefined);
  });
  it('keeps entered data and displays validation failure', async () => {
    vi.mocked(api.saveWarehouse).mockRejectedValue(new Error('This warehouse code is already used.'));
    wrap(<WarehouseForm onSaved={saved} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByRole('textbox', { name: /Warehouse name/ }), { target: { value: 'Main' } });
    fireEvent.change(screen.getByRole('textbox', { name: /Warehouse code/ }), { target: { value: 'MAIN' } });
    fireEvent.click(screen.getByRole('button', { name: 'Register warehouse' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('already used');
    expect(screen.getByRole('textbox', { name: /Warehouse name/ })).toHaveValue('Main');
    expect(saved).not.toHaveBeenCalled();
  });
  it('offers inline registration to Admins when there is no warehouse', async () => {
    wrap(<ImportWarehouseSetup onCreated={vi.fn()} />);
    expect(await screen.findByText(/No active warehouses. Register/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'New warehouse' }));
    expect(screen.getByRole('form', { name: 'Register warehouse' })).toBeVisible();
    expect(screen.getByRole('checkbox', { name: /default receiving/ })).toBeChecked();
  });
  it('guides a Storekeeper to Admin without exposing registration', async () => {
    actor.role = 'storekeeper';
    wrap(<ImportWarehouseSetup onCreated={vi.fn()} />);
    expect(await screen.findByText(/Ask an Admin to register/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'New warehouse' })).not.toBeInTheDocument();
  });
});
