import type { DashboardData } from '@/api/types';

export function normalizeDashboardData(data: DashboardData): DashboardData {
  return {
    ...data,
    recent_stock_movements: data.recent_stock_movements || [],
    low_stock_materials: data.low_stock_materials || [],
    pending_purchase_requests_list: data.pending_purchase_requests_list || [],
    project_budget_vs_actual: data.project_budget_vs_actual || [],
  };
}

export function mergeDashboardUpdate(
  current: DashboardData | undefined,
  update: Partial<DashboardData>,
) {
  if (!current) return current;
  return normalizeDashboardData({ ...current, ...update });
}
