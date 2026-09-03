import { describe, expect, it } from 'vitest';
import { can, canReceivePurchaseOrder, hasRole, ROLE_LABELS } from './roles';
import type { PurchaseOrder } from './types';

describe('role permissions', () => {
  it('allows only storekeeper/admin to create stock movements', () => {
    expect(can.createMovement('storekeeper')).toBe(true);
    expect(can.createMovement('admin')).toBe(true);
    expect(can.createMovement('procurement_officer')).toBe(false);
  });

  it('keeps reports restricted to management/procurement/admin users', () => {
    expect(can.reports('project_manager')).toBe(true);
    expect(can.reports('procurement_officer')).toBe(true);
    expect(can.reports('site_engineer')).toBe(false);
  });

  it('labels all backend roles', () => {
    expect(Object.keys(ROLE_LABELS)).toHaveLength(8);
    expect(hasRole('admin', ['admin'])).toBe(true);
  });

  it('separates finance viewing, preparation and management roles', () => {
    expect(can.viewFinance('finance_viewer')).toBe(true);
    expect(can.viewFinance('project_manager')).toBe(true);
    expect(can.viewFinance('procurement_officer')).toBe(true);
    expect(can.prepareFinance('finance_officer')).toBe(true);
    expect(can.prepareFinance('finance_manager')).toBe(true);
    expect(can.prepareFinance('finance_viewer')).toBe(false);
    expect(can.manageFinance('finance_manager')).toBe(true);
    expect(can.manageFinance('finance_officer')).toBe(false);
    expect(can.manageFinance('admin')).toBe(true);
    expect(can.submitPrToFinance('project_manager')).toBe(true);
    expect(can.submitPrToFinance('procurement_officer')).toBe(true);
    expect(can.reviewPrFinance('finance_manager')).toBe(true);
    expect(can.reviewPrFinance('finance_officer')).toBe(false);
  });

  it('requires the correct receiver and dispatch state for each PO destination', () => {
    const warehouseOrder = {
      status: 'PENDING',
      delivery_destination: 'WAREHOUSE',
    } as PurchaseOrder;

    expect(canReceivePurchaseOrder('storekeeper', warehouseOrder)).toBe(false);
    expect(canReceivePurchaseOrder('storekeeper', {
      ...warehouseOrder,
      status: 'ORDERED',
    })).toBe(true);
    expect(canReceivePurchaseOrder('site_engineer', warehouseOrder)).toBe(false);
    expect(canReceivePurchaseOrder('site_engineer', {
      ...warehouseOrder,
      status: 'DISPATCH_CONFIRMED',
      delivery_destination: 'SITE',
    })).toBe(true);
    expect(canReceivePurchaseOrder('site_engineer', {
      ...warehouseOrder,
      delivery_destination: 'SITE',
    })).toBe(false);
  });
});
