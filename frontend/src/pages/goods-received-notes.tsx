import type { ColumnDef } from '@tanstack/react-table';
import { Eye, ReceiptText } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '@/modules/procurement/api';
import type { GoodsReceivedNote } from '@/modules/procurement/types';
import { qk } from '@/api/queryKeys';
import { FormModal } from '@/components/common/form-modal';
import { Pagination } from '@/components/common/pagination';
import { PageToolbar } from '@/components/common/page-toolbar';
import { ExportButton } from '@/components/common/export-button';
import { RecordContext } from '@/components/common/record-context';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';
import { formatDate, formatNumber } from '@/lib/utils';

export function GoodsReceivedNotesPage() {
  const list = useListState({ status: '', receipt_date: '' });
  const [selected, setSelected] = useState<GoodsReceivedNote | null>(null);
  const toast = useToast();
  const notes = useQuery({ queryKey: qk.goodsReceivedNotes(list.query), queryFn: () => api.goodsReceivedNotes(list.query) });
  const download = async (note: GoodsReceivedNote) => {
    try { await api.downloadGoodsReceivedNotePdf(note.id, note.number); toast.push({ title: `GRN ${note.number} PDF prepared`, tone: 'success' }); }
    catch (error) { toast.push({ title: 'GRN PDF failed', message: (error as Error).message, tone: 'danger' }); }
  };
  const downloadRegister = async () => {
    try { await api.downloadGoodsReceivedNoteRegisterPdf({ ...list.filters, search: list.search }); toast.push({ title: 'GRN register PDF prepared', tone: 'success' }); }
    catch (error) { toast.push({ title: 'GRN register PDF failed', message: (error as Error).message, tone: 'danger' }); }
  };
  const downloadRegisterXlsx = async () => {
    try { await api.downloadGoodsReceivedNoteRegisterXlsx({ ...list.filters, search: list.search }); toast.push({ title: 'GRN Excel register prepared', tone: 'success' }); }
    catch (error) { toast.push({ title: 'GRN Excel export failed', message: (error as Error).message, tone: 'danger' }); }
  };
  const columns: ColumnDef<GoodsReceivedNote>[] = [
    { header: 'GRN', cell: ({ row }) => <strong>{row.original.number}</strong> },
    { header: 'PO', cell: ({ row }) => row.original.purchase_order_number },
    { header: 'Received', cell: ({ row }) => <div><span>{formatDate(row.original.receipt_date)}</span><p className="text-xs text-muted">{row.original.received_by_name || row.original.received_by_username || 'Recorded receiver'}</p></div> },
    { header: 'Status', cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status}</Badge> },
    { header: 'Lines', cell: ({ row }) => `${row.original.items.length} material${row.original.items.length === 1 ? '' : 's'}` },
    { id: 'actions', header: '', cell: ({ row }) => <div className="flex justify-end gap-1"><Button size="sm" variant="ghost" onClick={() => setSelected(row.original)}><Eye className="h-4 w-4" />View</Button><ExportButton label="PDF" variant="secondary" onClick={() => void download(row.original)} /></div> },
  ];

  return <div className="grid gap-4">
    <PageToolbar title="Goods received notes" subtitle="Permanent record of physical receipt, condition, quantities and receiver for every purchase order." search={list.search} onSearch={list.setSearch}>
      <select className={inputClass} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}>
        <option value="">All statuses</option><option value="ACCEPTED">Accepted</option><option value="REVERSED">Reversed</option>
      </select>
      <input className={inputClass} type="date" value={list.filters.receipt_date} aria-label="Filter GRNs by receipt date" onChange={(event) => list.setFilter('receipt_date', event.target.value)} />
      <ExportButton label="All GRNs PDF" variant="secondary" onClick={() => void downloadRegister()} />
      <ExportButton label="All GRNs Excel" variant="secondary" onClick={() => void downloadRegisterXlsx()} />
    </PageToolbar>
    <DataTable columns={columns} data={notes.data?.results || []} mobileSummaryCells={2} emptyTitle={notes.isLoading ? 'Loading goods received notes...' : 'No GRNs found'} />
    <Pagination page={list.page} setPage={list.setPage} data={notes.data} />
    <GrnDetail note={selected} onClose={() => setSelected(null)} />
  </div>;
}

function GrnDetail({ note, onClose }: { note: GoodsReceivedNote | null; onClose: () => void }) {
  return <FormModal open={!!note} title={note ? `GRN ${note.number}` : 'Goods received note'} onClose={onClose}>
    {note ? <div className="grid gap-4">
      <RecordContext items={[{ label: 'Purchase order', value: note.purchase_order_number }, { label: 'Receipt date', value: formatDate(note.receipt_date) }, { label: 'Received by', value: note.received_by_name || note.received_by_username || 'Recorded receiver' }, { label: 'Status', value: note.status, tone: statusTone(note.status) }]} />
      {note.notes ? <Field label="Receipt notes"><p className="rounded-lg border border-border bg-background p-3 text-sm">{note.notes}</p></Field> : null}
      <div className="grid gap-2">
        <h3 className="flex items-center gap-2 font-bold"><ReceiptText className="h-4 w-4" />Received material lines</h3>
        {note.items.map((item) => <div key={item.id} className="grid gap-2 rounded-lg border border-border p-3 text-sm sm:grid-cols-[1fr_repeat(3,auto)] sm:items-center sm:gap-5">
          <div><strong>{item.material_name}</strong>{item.notes ? <p className="mt-1 text-xs text-muted">{item.notes}</p> : null}</div>
          <Quantity label="Accepted" value={item.accepted_quantity} />
          <Quantity label="Rejected" value={item.rejected_quantity} warning={Number(item.rejected_quantity) > 0} />
          <Quantity label="Damaged" value={item.damaged_quantity} warning={Number(item.damaged_quantity) > 0} />
        </div>)}
      </div>
    </div> : null}
  </FormModal>;
}

function Quantity({ label, value, warning = false }: { label: string; value: string; warning?: boolean }) {
  return <div className={warning ? 'text-warning' : ''}><span className="text-xs text-muted">{label}</span><strong className="block">{formatNumber(value)}</strong></div>;
}
