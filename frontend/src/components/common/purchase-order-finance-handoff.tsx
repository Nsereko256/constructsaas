import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/modules/procurement/api';
import { financeApi } from '@/modules/finance/api';
import type { PurchaseOrder } from '@/modules/procurement/types';
import { FormModal } from '@/components/common/form-modal';
import { Field, inputClass } from '@/components/ui/field';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { formatUGX } from '@/lib/utils';

export function PurchaseOrderFinanceHandoffModal({ order, onClose }: { order: PurchaseOrder | null; onClose: () => void }) {
  const [comments, setComments] = useState('');
  const [budgetLine, setBudgetLine] = useState('');
  const queryClient = useQueryClient();
  const toast = useToast();

  const budgets = useQuery({
    queryKey: ['finance', 'budgets', 'purchase-order-handoff', order?.purchase_request],
    queryFn: () => financeApi.budgets({ project: order?.project, status: 'APPROVED', page_size: 20 }),
    enabled: Boolean(order?.purchase_request && order?.project),
  });
  const budgetLines = budgets.data?.results.flatMap((budget) => budget.lines.map((line) => ({ ...line, budgetName: budget.name }))) || [];

  useEffect(() => {
    if (order) {
      setComments('Please review the purchase order value and confirm budget clearance.');
      setBudgetLine('');
    }
  }, [order]);

  const submit = useMutation({
    mutationFn: () => {
      if (!order) throw new Error('Select a purchase order to send to Finance.');
      return api.submitPurchaseOrderToFinance(order.id, budgetLine ? Number(budgetLine) : null, comments.trim());
    },
    onSuccess: () => {
      toast.push({ title: 'Sent to Finance', message: `${order?.number} is now in the Finance review queue.`, tone: 'success' });
      void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] });
      void queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
      for (const key of ['purchase-order-detail', 'purchase-order-activity', 'purchase-request-detail', 'purchase-request-activity', 'workflow-badges', 'finance']) void queryClient.invalidateQueries({ queryKey: [key] });
      onClose();
    },
    onError: (error: Error) => toast.push({ title: 'Finance handoff failed', message: error.message, tone: 'danger' }),
  });

  return <FormModal open={!!order} title={`Send ${order?.number || 'purchase order'} to Finance`} onClose={() => { if (!submit.isPending) onClose(); }}>
    <form className="grid gap-3" onSubmit={(event) => { event.preventDefault(); submit.mutate(); }}>
      <p className="text-sm text-slate-600">Finance will review the order value and budget clearance before Procurement commits the order to the supplier.</p>
      {order?.project ? <Field label="Budget authorization">
        <select className={inputClass} disabled={budgets.isLoading || budgets.isError || submit.isPending} value={budgetLine} onChange={(event) => setBudgetLine(event.target.value)}>
          <option value="">Unbudgeted request — Finance Manager override required</option>
          {budgetLines.map((line) => <option key={line.id} value={line.id}>{line.budgetName} / {line.category_name || line.category_code} / available {formatUGX(line.available_balance)}</option>)}
        </select>
        {budgets.isLoading ? <small className="text-muted">Loading approved budget lines…</small> : null}
        {budgets.isError ? <div role="alert" className="text-sm text-critical">Budget lines could not be loaded. <Button type="button" variant="secondary" onClick={() => void budgets.refetch()}>Retry</Button></div> : null}
      </Field> : <p className="border border-info/20 bg-info/5 p-3 text-sm text-muted">This is a warehouse replenishment. Finance will review it as an unbudgeted stock purchase.</p>}
      <Field label="Finance review note" required>
        <textarea className={inputClass} rows={4} value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Explain what Finance should check" required />
      </Field>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" disabled={submit.isPending} onClick={onClose}>Keep pending</Button>
        <Button type="submit" loading={submit.isPending} loadingLabel="Sending" disabled={!comments.trim() || (Boolean(order?.project) && (budgets.isLoading || budgets.isError))}>Send to Finance</Button>
      </div>
    </form>
  </FormModal>;
}
