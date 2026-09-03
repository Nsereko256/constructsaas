import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CheckCircle2, Truck } from 'lucide-react';
import { api } from '@/api/services';
import { getTokens } from '@/api/client';
import { offlineScope, queueOfflineAction } from '@/pwa/offline';
import type { PurchaseOrder, SupplierClaim } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can, canReceivePurchaseOrder } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { FormModal } from '@/components/common/form-modal';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { inputClass } from '@/components/ui/field';
import { Field } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatUGX } from '@/lib/utils';

export function DeliveriesPage() {
  const { role } = useAuth();
  const [searchParams] = useSearchParams();
  const replacementClaimId = Number(searchParams.get('replacement_claim') || 0);
  const list = useListState({
    status: searchParams.get('status') || '',
    delivery_destination: searchParams.get('delivery_destination') || '',
    action_queue: searchParams.get('action_queue') || '',
  });
  const orders = useQuery({ queryKey: qk.purchaseOrders(list.query), queryFn: () => api.purchaseOrders(list.query) });
  const receipts = useQuery({ queryKey: ['goods-received-notes', 'delivery-remaining'], queryFn: () => api.goodsReceivedNotes({ page_size: 100 }) });
  const replacementClaim = useQuery({ queryKey: ['supplier-claim', replacementClaimId], queryFn: () => api.supplierClaim(replacementClaimId), enabled: replacementClaimId > 0 });
  const replacementOrder = useQuery({ queryKey: ['purchase-order', replacementClaim.data?.purchase_order], queryFn: () => api.purchaseOrder(replacementClaim.data!.purchase_order), enabled: !!replacementClaim.data?.purchase_order });
  const queryClient = useQueryClient();
  const toast = useToast();
  const [receiving, setReceiving] = useState<PurchaseOrder | null>(null);
  useEffect(() => { if (replacementClaim.data && replacementOrder.data) setReceiving(replacementOrder.data); }, [replacementClaim.data, replacementOrder.data]);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['purchase-orders'] });
  const dispatch = useMutation({
    mutationFn: api.confirmDispatch,
    onSuccess: () => { toast.push({ title: 'Dispatch confirmed', tone: 'success' }); refresh(); },
    onError: (error: Error) => toast.push({ title: 'Dispatch blocked', message: error.message, tone: 'danger' }),
  });
  const receive = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Record<string, unknown> }) => {
      const withIdempotency = { ...body, client_uuid: crypto.randomUUID() };
      const queue = async () => queueOfflineAction({ scope: offlineScope(getTokens()?.access), kind: 'goods-received-note', path: `/api/purchase-orders/${id}/receive/`, body: withIdempotency });
      if (!navigator.onLine) {
        await queue();
        return { queued: true };
      }
      try { return replacementClaimId ? await api.receiveSupplierReplacement(replacementClaimId, withIdempotency) : await api.receivePurchaseOrder(id, withIdempotency); }
      catch (error) {
        // Retrying a transport failure with this same UUID cannot duplicate stock.
        if (error instanceof TypeError) { await queue(); return { queued: true }; }
        throw error;
      }
    },
    onSuccess: (order) => {
      if ('queued' in order) {
        toast.push({ title: 'Receipt saved offline — stock updates after server confirmation', tone: 'success' });
      } else {
        toast.push({ title: replacementClaimId ? 'Supplier replacement received and claim resolved' : order.status === 'PARTIAL' ? 'Partial receipt recorded' : 'Receipt confirmed', tone: 'success' });
        refresh();
      }
      setReceiving(null);
    },
    onError: (error: Error) => toast.push({ title: 'Receipt blocked', message: error.message, tone: 'danger' }),
  });
  const columns: ColumnDef<PurchaseOrder>[] = [
    { header: 'PO', cell: ({ row }) => <strong>{row.original.number}</strong> },
    { header: 'Supplier', cell: ({ row }) => row.original.supplier_name },
    { header: 'Destination', cell: ({ row }) => row.original.delivery_destination_display },
    { header: 'Project', cell: ({ row }) => row.original.project_name || '-' },
    { header: 'Status', cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status_display}</Badge> },
    { header: 'Received', cell: ({ row }) => row.original.received_at ? <div><span>{formatDate(row.original.received_at)}</span><p className="text-xs text-muted">{row.original.received_by_username || 'GRN receiver'}</p></div> : '-' },
    { header: 'Total', cell: ({ row }) => formatUGX(row.original.total_cost) },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex justify-end gap-2">
          {can.createPo(role) && row.original.delivery_destination === 'SITE' && !['DISPATCH_CONFIRMED', 'RECEIVED', 'CANCELLED'].includes(row.original.status) ? (
            <Button size="sm" variant="secondary" onClick={() => dispatch.mutate(row.original.id)}><Truck className="h-4 w-4" />Dispatch</Button>
          ) : null}
          {canReceivePurchaseOrder(role, row.original) ? (
            <Button size="sm" onClick={() => setReceiving(row.original)}><CheckCircle2 className="h-4 w-4" />Receive</Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <div className="grid gap-4">
      <PageToolbar title="Deliveries" subtitle={role === 'storekeeper' ? 'Warehouse receiving and oversight queue. Site engineers record direct-site GRNs; you remain notified and can review them.' : role === 'site_engineer' ? 'Record physical GRNs for your assigned direct-to-site deliveries after Procurement confirms dispatch.' : 'Delivery tracking and supplier dispatch oversight. Warehouse GRNs are Storekeeper-only; site GRNs are recorded by assigned site engineers.'} search={list.search} onSearch={list.setSearch}>
        <select className={inputClass} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}>
          <option value="">All statuses</option>
          <option value="PENDING">Pending</option>
          <option value="ORDERED">Ordered</option>
          <option value="DISPATCH_CONFIRMED">Dispatch confirmed</option>
          <option value="RECEIVED">Received</option>
        </select>
      </PageToolbar>
      <DataTable columns={columns} data={orders.data?.results || []} emptyTitle={orders.isLoading ? 'Loading deliveries...' : 'No deliveries found'} />
      <Pagination page={list.page} setPage={list.setPage} data={orders.data} />
      <ReceiptModal
        order={receiving}
        receipts={receipts.data?.results || []}
        pending={receive.isPending}
        role={role}
        replacementClaim={replacementClaim.data}
        onClose={() => setReceiving(null)}
        onSubmit={(body) => receiving && receive.mutate({ id: receiving.id, body: body as Record<string, unknown> })}
      />
    </div>
  );
}

type ReceiptLine = { purchase_order_item: number; accepted_quantity: string; rejected_quantity: string; damaged_quantity: string; notes: string };

function ReceiptModal({ order, receipts, pending, role, replacementClaim, onClose, onSubmit }: { order: PurchaseOrder | null; receipts: Awaited<ReturnType<typeof api.goodsReceivedNotes>>['results']; pending: boolean; role: string | null; replacementClaim?: SupplierClaim; onClose: () => void; onSubmit: (body: unknown) => void }) {
  const [receiptDate, setReceiptDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<ReceiptLine[]>([]);
  const open = Boolean(order);

  const resetForOrder = (next: PurchaseOrder | null) => {
    setReceiptDate(new Date().toISOString().slice(0, 10));
    setNotes('');
    if (replacementClaim) {
      setLines([{ purchase_order_item: replacementClaim.purchase_order_item, accepted_quantity: String(replacementClaim.replacement_quantity), rejected_quantity: '0', damaged_quantity: '0', notes: `Supplier replacement for claim #${replacementClaim.id}` }]);
      return;
    }
    const dispositioned = new Map<number, number>();
    receipts.filter((receipt) => receipt.purchase_order === next?.id && receipt.status === 'ACCEPTED').forEach((receipt) => receipt.items.forEach((item) => dispositioned.set(item.purchase_order_item, (dispositioned.get(item.purchase_order_item) || 0) + Number(item.accepted_quantity) + Number(item.rejected_quantity) + Number(item.damaged_quantity))));
    setLines(next?.items.flatMap((item) => {
      const remaining = Math.max(Number(item.quantity) - (dispositioned.get(item.id) || 0), 0);
      return remaining > 0 ? [{ purchase_order_item: item.id, accepted_quantity: String(remaining), rejected_quantity: '0', damaged_quantity: '0', notes: '' }] : [];
    }) || []);
  };
  // Receipt defaults intentionally refresh only when the selected PO or server receipt list changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { resetForOrder(order); }, [order, receipts, replacementClaim]);
  const lineTotal = (line: ReceiptLine) => Number(line.accepted_quantity || 0) + Number(line.rejected_quantity || 0) + Number(line.damaged_quantity || 0);
  const remainingQty = (purchaseOrderItemId: number) => {
    const item = order?.items.find((candidate) => candidate.id === purchaseOrderItemId);
    if (!item) return 0;
    const dispositioned = receipts.filter((receipt) => receipt.purchase_order === order?.id && receipt.status === 'ACCEPTED').flatMap((receipt) => receipt.items).filter((line) => line.purchase_order_item === item.id).reduce((total, line) => total + Number(line.accepted_quantity) + Number(line.rejected_quantity) + Number(line.damaged_quantity), 0);
    return Math.max(Number(item.quantity) - dispositioned, 0);
  };
  const valid = lines.length > 0 && (replacementClaim ? lines.every((line) => Number(line.accepted_quantity) === Number(replacementClaim.replacement_quantity) && Number(line.rejected_quantity) === 0 && Number(line.damaged_quantity) === 0) : lines.every((line) => lineTotal(line) > 0 && lineTotal(line) <= remainingQty(line.purchase_order_item) && (!((Number(line.rejected_quantity) > 0 || Number(line.damaged_quantity) > 0)) || line.notes.trim().length > 0)));

  return <FormModal open={open} title={`${replacementClaim ? 'Receive supplier replacement for' : 'Receive'} ${order?.number || 'purchase order'}`} onClose={() => { resetForOrder(null); onClose(); }}>
    <form className="grid gap-4" onSubmit={(event: FormEvent) => { event.preventDefault(); if (valid) onSubmit({ receipt_date: receiptDate, notes, items: lines }); }}>
      <p className="border border-info/20 bg-info/5 p-3 text-sm text-muted">{replacementClaim ? `This replacement closes supplier claim #${replacementClaim.id}. It must accept exactly ${replacementClaim.replacement_quantity} ${replacementClaim.material_name}; a further rejection requires Procurement to open a new claim.` : order?.delivery_destination === 'SITE' && role === 'site_engineer' ? 'You are recording the physical site GRN. Count what arrived, attach delivery details in the notes, and record any rejection or damage. Storekeeper is notified for oversight; only accepted quantities update the site store and may be invoiced.' : 'You are recording the physical Goods Received Note (GRN). Only accepted quantities update stock and may be invoiced. Rejected or damaged quantities require a line reason and remain visible to Procurement and Finance as a supplier exception.'}</p>
      <div className="grid gap-3 md:grid-cols-2"><Field label="Receipt date" required><input className={inputClass} type="date" value={receiptDate} onChange={(event) => setReceiptDate(event.target.value)} /></Field><Field label="Receipt notes"><input className={inputClass} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Delivery note, condition, or escalation reference" /></Field></div>
      <div className="grid gap-3">
        {lines.map((line) => {
          const item = order?.items.find((candidate) => candidate.id === line.purchase_order_item);
          if (!item) return null;
          const update = (key: keyof ReceiptLine, value: string) => setLines((current) => current.map((row) => row.purchase_order_item === line.purchase_order_item ? { ...row, [key]: value } : row));
          const remaining = replacementClaim ? Number(replacementClaim.replacement_quantity) : remainingQty(item.id);
          const exceeds = lineTotal(line) > remaining;
          const needsReason = Number(line.rejected_quantity) > 0 || Number(line.damaged_quantity) > 0;
          return <div key={item.id} className="grid gap-3 border border-border p-3 md:grid-cols-[minmax(180px,1.5fr)_repeat(3,110px)]">
            <div><strong>{item.material_name}</strong><p className="text-xs text-muted">Ordered: {item.quantity} / remaining to receive: {remaining}</p><input className={`${inputClass} mt-2`} value={line.notes} onChange={(event) => update('notes', event.target.value)} placeholder={needsReason ? 'Reason for rejection/damage (required)' : 'Line note'} /><p className="mt-1 text-xs text-danger">{needsReason && !line.notes.trim() ? 'Reason required for rejected or damaged goods.' : ''}</p></div>
            <Field label="Accepted"><input className={inputClass} type="number" min="0" max={remaining} step="0.01" value={line.accepted_quantity} onChange={(event) => update('accepted_quantity', event.target.value)} /></Field>
            <Field label="Rejected"><input disabled={!!replacementClaim} className={inputClass} type="number" min="0" max={remaining} step="0.01" value={line.rejected_quantity} onChange={(event) => update('rejected_quantity', event.target.value)} /></Field>
            <Field label="Damaged" error={exceeds ? `Cannot exceed remaining ${remaining}` : undefined}><input disabled={!!replacementClaim} className={inputClass} type="number" min="0" max={remaining} step="0.01" value={line.damaged_quantity} onChange={(event) => update('damaged_quantity', event.target.value)} /></Field>
          </div>;
        })}
      </div>
      <Button loading={pending} loadingLabel="Recording receipt" disabled={!valid}>Record receipt</Button>
    </form>
  </FormModal>;
}
