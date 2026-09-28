import { apiDownload, apiRequest, pageParams } from './client';
import type { Paginated } from './types';

export type ExternalEvent = { id: number; action: string; quantity: string; project_name: string; reason: string; actor: string; created_at: string };
export type ExternalLine = {
  id: number; material: number; material_name: string; material_code: string; unit: string; bin_code: string;
  quantity: string; unit_cost: string; received: string; pending: string; remaining: string;
  held: string | null; outstanding: string | null; returned: string; projects: Record<string, string>; events: ExternalEvent[];
};
export type ExternalReceipt = {
  id: number; reference: string; status: 'PENDING' | 'POSTED' | 'REJECTED' | 'REVERSED'; received_date: string;
  received_by: string; reviewed_by: string; reviewed_at: string | null; review_reason: string; notes: string;
  lines: { order_line: number; accepted: string; damaged: string; rejected: string; posted_unit_cost: string | null }[];
};
export type ExternalOrder = {
  id: number; sender: string; reference: string; ownership: 'PERMANENT' | 'BORROWED'; warehouse: number; warehouse_name: string;
  expected_date: string; return_due_date: string | null; notes: string; closed: boolean; created_at: string;
  created_by_name: string; status: string; pending_receipts: number; lines: ExternalLine[]; receipts: ExternalReceipt[];
};
export const externalTransfers = {
  list: (params: Record<string, string | number>) => apiRequest<Paginated<ExternalOrder>>(`/api/external-move-orders/${pageParams(params)}`),
  detail: (id: string) => apiRequest<ExternalOrder>(`/api/external-move-orders/${id}/`),
  create: (body: unknown) => apiRequest<ExternalOrder>('/api/external-move-orders/', { method: 'POST', body }),
  action: (id: number, action: string, body: unknown) => apiRequest<ExternalOrder>(`/api/external-move-orders/${id}/${action}/`, { method: 'POST', body }),
  download: (kind: 'pdf' | 'xlsx', id?: number, params: Record<string, string> = {}) => {
    const site = typeof window !== 'undefined' ? window.localStorage.getItem('construct.active-project-site') : null;
    const filters = id ? {} : { ...params, ...(site ? { project_site: site } : {}) };
    return apiDownload(`/api/external-move-orders/${id ? `${id}/` : ''}download/${kind}/${pageParams(filters)}`, `${id ? `move-order-MO-${id}` : 'move-orders'}.${kind}`);
  },
};
export const canReadExternalTransfers = (role: string | null) => ['admin', 'storekeeper', 'procurement_officer', 'finance_manager', 'finance_officer', 'finance_viewer'].includes(role || '');

// Selector data must not silently stop at the first page.
export async function allChoices<T>(path: string): Promise<T[]> {
  const rows: T[] = [];
  for (let page = 1; ; page++) {
    const result = await apiRequest<Paginated<T>>(`${path}${path.includes('?') ? '&' : '?'}page=${page}&page_size=100`, {}, true, false);
    rows.push(...result.results);
    if (!result.next) return rows;
  }
}
