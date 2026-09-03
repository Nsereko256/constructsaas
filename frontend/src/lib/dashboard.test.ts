import { describe, expect, it } from 'vitest';
import type { DashboardData } from '@/api/types';
import { mergeDashboardUpdate, normalizeDashboardData } from './dashboard';

const completeDashboard = {
  active_projects: 2,
  total_active_materials: 10,
  pending_purchase_requests: 3,
  low_stock_count: 1,
  stock_in_today: '4',
  inventory_value: '100000',
  recent_stock_movements: [],
  low_stock_materials: [],
  pending_purchase_requests_list: [],
  project_budget_vs_actual: [],
} as DashboardData;

describe('dashboard real-time state', () => {
  it('merges partial socket KPIs without removing REST collections', () => {
    const result = mergeDashboardUpdate(completeDashboard, { low_stock_count: 4 });

    expect(result?.low_stock_count).toBe(4);
    expect(result?.low_stock_materials).toEqual([]);
    expect(result?.project_budget_vs_actual).toEqual([]);
  });

  it('normalizes omitted collections from defensive API data', () => {
    const result = normalizeDashboardData({
      ...completeDashboard,
      low_stock_materials: undefined,
    } as unknown as DashboardData);

    expect(result.low_stock_materials).toEqual([]);
  });
});
