import type { PurchaseOrder, Role } from './types';

export const ROLE_LABELS: Record<Role, string> = {
  site_engineer: 'Site Engineer',
  storekeeper: 'Storekeeper',
  project_manager: 'Project Manager',
  procurement_officer: 'Procurement Officer',
  finance_officer: 'Finance Officer',
  finance_manager: 'Finance Manager',
  finance_viewer: 'Finance Viewer',
  admin: 'Admin',
};

export function hasRole(role: Role | null | undefined, allowed: Role[]) {
  return !!role && allowed.includes(role);
}

export const can = {
  manageMaterials: (role?: Role | null) => hasRole(role, ['storekeeper', 'procurement_officer', 'admin']),
  deactivateMaterials: (role?: Role | null) => role === 'admin',
  manageSuppliers: (role?: Role | null) => hasRole(role, ['procurement_officer', 'admin']),
  submitPr: (role?: Role | null) => hasRole(role, ['site_engineer', 'admin']),
  submitWarehouseReplenishment: (role?: Role | null) => hasRole(role, ['procurement_officer', 'admin']),
  approvePr: (role?: Role | null) => hasRole(role, ['project_manager', 'admin']),
  createPo: (role?: Role | null) => hasRole(role, ['procurement_officer', 'admin']),
  receivePo: (role?: Role | null) => hasRole(role, ['storekeeper', 'site_engineer']),
  createMovement: (role?: Role | null) => hasRole(role, ['storekeeper', 'admin']),
  reports: (role?: Role | null) => hasRole(role, ['project_manager', 'procurement_officer', 'admin']),
  manageTeam: (role?: Role | null) => role === 'admin',
  // These roles have company-scoped read access in the API. Keeping the UI aligned
  // lets project and procurement teams see the financial state of their handoffs
  // without granting them finance posting powers.
  viewFinance: (role?: Role | null) => hasRole(role, ['project_manager', 'procurement_officer', 'finance_officer', 'finance_manager', 'finance_viewer', 'admin']),
  prepareFinance: (role?: Role | null) => hasRole(role, ['finance_officer', 'finance_manager', 'admin']),
  manageFinance: (role?: Role | null) => hasRole(role, ['finance_manager', 'admin']),
  submitPrToFinance: (role?: Role | null) => hasRole(role, ['project_manager', 'procurement_officer', 'finance_officer', 'admin']),
  reviewPrFinance: (role?: Role | null) => hasRole(role, ['finance_officer', 'finance_manager', 'admin']),
};

export function canReceivePurchaseOrder(role: Role | null | undefined, order: PurchaseOrder) {
  if (['RECEIVED', 'CANCELLED'].includes(order.status)) return false;
  const receivableStatus = order.delivery_destination === 'WAREHOUSE'
    ? ['ORDERED', 'PARTIAL']
    : ['DISPATCH_CONFIRMED', 'PARTIAL'];
  const permittedRoles: Role[] = order.delivery_destination === 'WAREHOUSE' ? ['storekeeper'] : ['storekeeper', 'site_engineer'];
  return receivableStatus.includes(order.status) && hasRole(role, permittedRoles);
}
