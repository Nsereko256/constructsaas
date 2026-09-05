import { useQuery } from '@tanstack/react-query';
import { Box, CalendarDays, CheckCircle2, ChevronDown, ChevronRight, CircleAlert, Download, EllipsisVertical, Eye, FileText, PackageCheck, Search, Truck } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '@/modules/procurement/api';
import type { GoodsReceivedNote, PurchaseOrder } from '@/modules/procurement/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { RecordContext } from '@/components/common/record-context';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatDate, formatNumber, formatUGX } from '@/lib/utils';
import './goods-received-notes-reference.css';

type ReceiptQueue = 'all' | 'accepted' | 'exceptions' | 'reversed';
type ReceiptSummary = { note: GoodsReceivedNote; order?: PurchaseOrder; accepted: number; rejected: number; damaged: number; value: number; hasException: boolean };
const EMPTY_NOTES: GoodsReceivedNote[] = [];
const EMPTY_ORDERS: PurchaseOrder[] = [];

export function GoodsReceivedNotesPage() {
  const { role } = useAuth();
  const toast = useToast();
  const [selected, setSelected] = useState<GoodsReceivedNote | null>(null);
  const [queue, setQueue] = useState<ReceiptQueue>('all');
  const [search, setSearch] = useState('');
  const [destination, setDestination] = useState('');
  const [status, setStatus] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [sort, setSort] = useState<'newest' | 'oldest'>('newest');
  const [page, setPage] = useState(1);
  const notes = useQuery({ queryKey: qk.goodsReceivedNotes({ page_size: 100 }), queryFn: () => api.goodsReceivedNotes({ page_size: 100 }) });
  const orders = useQuery({ queryKey: qk.purchaseOrders({ page_size: 100 }), queryFn: () => api.purchaseOrders({ page_size: 100 }) });

  const allNotes = notes.data?.results ?? EMPTY_NOTES;
  const allOrders = orders.data?.results ?? EMPTY_ORDERS;
  const ordersById = useMemo(() => new Map(allOrders.map((order) => [order.id, order])), [allOrders]);
  const rows = useMemo<ReceiptSummary[]>(() => allNotes.map((note) => {
    const order = ordersById.get(note.purchase_order);
    const linePrices = new Map(order?.items.map((item) => [item.id, Number(item.unit_price || 0)]) || []);
    const accepted = note.items.reduce((sum, item) => sum + Number(item.accepted_quantity || 0), 0);
    const rejected = note.items.reduce((sum, item) => sum + Number(item.rejected_quantity || 0), 0);
    const damaged = note.items.reduce((sum, item) => sum + Number(item.damaged_quantity || 0), 0);
    const value = note.items.reduce((sum, item) => sum + Number(item.accepted_quantity || 0) * (linePrices.get(item.purchase_order_item) || 0), 0);
    return { note, order, accepted, rejected, damaged, value, hasException: rejected > 0 || damaged > 0 };
  }), [allNotes, ordersById]);

  const activeRows = rows.filter((row) => row.note.status === 'ACCEPTED');
  const acceptedRows = activeRows.filter((row) => !row.hasException);
  const exceptionRows = activeRows.filter((row) => row.hasException);
  const reversedRows = rows.filter((row) => row.note.status === 'REVERSED');
  const today = new Date().toISOString().slice(0, 10);
  const todayRows = activeRows.filter((row) => row.note.receipt_date === today);
  const stockPosted = activeRows.filter((row) => row.accepted > 0);
  const totalQuality = activeRows.reduce((sum, row) => sum + row.accepted + row.rejected + row.damaged, 0);
  const acceptedPercent = totalQuality ? Math.round(activeRows.reduce((sum, row) => sum + row.accepted, 0) / totalQuality * 100) : 0;
  const rejectedPercent = totalQuality ? Math.round(activeRows.reduce((sum, row) => sum + row.rejected, 0) / totalQuality * 100) : 0;
  const damagedPercent = totalQuality ? Math.round(activeRows.reduce((sum, row) => sum + row.damaged, 0) / totalQuality * 100) : 0;
  const warehouseRows = activeRows.filter((row) => row.order?.delivery_destination === 'WAREHOUSE');
  const siteRows = activeRows.filter((row) => row.order?.delivery_destination === 'SITE');

  const filteredRows = useMemo(() => rows.filter((row) => {
    const haystack = [row.note.number, row.note.purchase_order_number, row.order?.supplier_name, row.order?.project_name, ...row.note.items.map((item) => item.material_name)].join(' ').toLowerCase();
    const matchesQueue = queue === 'all' || (queue === 'accepted' && row.note.status === 'ACCEPTED' && !row.hasException) || (queue === 'exceptions' && row.note.status === 'ACCEPTED' && row.hasException) || (queue === 'reversed' && row.note.status === 'REVERSED');
    const matchesDestination = !destination || row.order?.delivery_destination === destination;
    const matchesStatus = !status || row.note.status === status;
    const matchesDate = (!fromDate || row.note.receipt_date >= fromDate) && (!toDate || row.note.receipt_date <= toDate);
    return matchesQueue && matchesDestination && matchesStatus && matchesDate && haystack.includes(search.trim().toLowerCase());
  }).sort((a, b) => sort === 'newest' ? Date.parse(b.note.created_at) - Date.parse(a.note.created_at) : Date.parse(a.note.created_at) - Date.parse(b.note.created_at)), [rows, queue, destination, status, fromDate, toDate, search, sort]);

  const pageSize = 5;
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const displayedRows = filteredRows.slice((page - 1) * pageSize, page * pageSize);
  const pageStart = filteredRows.length ? (page - 1) * pageSize + 1 : 0;
  const pageEnd = filteredRows.length ? Math.min(page * pageSize, filteredRows.length) : 0;
  const updateQueue = (value: ReceiptQueue) => { setQueue(value); setPage(1); };
  const updateFilter = (update: () => void) => { update(); setPage(1); };
  const download = async (note: GoodsReceivedNote) => {
    try { await api.downloadGoodsReceivedNotePdf(note.id, note.number); toast.push({ title: `GRN ${note.number} PDF prepared`, tone: 'success' }); }
    catch (error) { toast.push({ title: 'GRN PDF failed', message: (error as Error).message, tone: 'danger' }); }
  };
  const exportRegister = async (kind: 'pdf' | 'xlsx') => {
    try {
      const params = { status, receipt_date: fromDate && fromDate === toDate ? fromDate : undefined, search };
      if (kind === 'pdf') await api.downloadGoodsReceivedNoteRegisterPdf(params);
      else await api.downloadGoodsReceivedNoteRegisterXlsx(params);
      toast.push({ title: `GRN ${kind === 'pdf' ? 'PDF' : 'Excel'} register prepared`, tone: 'success' });
    } catch (error) { toast.push({ title: 'GRN register export failed', message: (error as Error).message, tone: 'danger' }); }
  };

  return <div className="goods-received-reference">
    <section className="grn-top">
      <div className="grn-titlebar"><div><h1>Goods received notes</h1><p>Verify quantities, condition and destination before materials enter stock.</p></div><div className="grn-title-actions"><details className="grn-export-menu"><summary><Download size={15} />Export <ChevronDown size={13} /></summary><div><button type="button" onClick={() => void exportRegister('pdf')}>PDF register</button><button type="button" onClick={() => void exportRegister('xlsx')}>Excel register</button></div></details><Button asChild><Link to="/procurement/deliveries">{can.receivePo(role) ? <><PackageCheck className="h-4 w-4" />Record receipt</> : <><Truck className="h-4 w-4" />Receipt queue</>}</Link></Button></div></div>
      <nav className="grn-tabs" aria-label="Procurement sections"><Link to="/procurement">Overview</Link><Link to="/procurement/requests">Purchase requests</Link><Link to="/procurement/rfqs">Supplier quotes</Link><Link to="/procurement/purchase-orders">Purchase orders</Link><Link className="active" to="/procurement/grns">Receipts</Link><Link to="/procurement/deliveries">Deliveries</Link><Link to="/procurement/supplier-claims">Supplier claims</Link></nav>
    </section>
    <section className="grn-guidance"><CircleAlert size={17} /><span><strong>Accepted GRNs are permanent inventory records.</strong><small>Corrections require an approved reversal; recorded quantities cannot be silently edited.</small></span><Link to="/procurement/supplier-claims">Exception policy <ChevronRight size={14} /></Link></section>
    <section className="grn-kpis"><ReceiptKpi icon={FileText} tone="blue" label="Total GRNs" value={rows.length} note="Across selected sites" /><ReceiptKpi icon={CheckCircle2} tone="green" label="Accepted" value={activeRows.length} note={rows.length ? `${Math.round(activeRows.length / rows.length * 100)}% active records` : 'No records yet'} /><ReceiptKpi icon={CalendarDays} tone="indigo" label="Received today" value={todayRows.length} note={todayRows.length ? 'Physical receipts recorded' : 'No receipts today'} /><ReceiptKpi icon={Box} tone="green" label="Stock posted" value={stockPosted.length} note="Accepted quantities updated" /><ReceiptKpi icon={CircleAlert} tone="amber" label="Exceptions" value={exceptionRows.length} note={exceptionRows.length ? 'Rejected or damaged lines' : 'No quantity exceptions'} /></section>
    <section className="grn-workspace-grid"><div className="grn-register-panel"><div className="grn-panel-heading"><h2>Receipt register</h2></div><div className="grn-queue-tabs">{([['all', 'All', rows.length], ['accepted', 'Accepted', acceptedRows.length], ['exceptions', 'With exceptions', exceptionRows.length], ['reversed', 'Reversed', reversedRows.length]] as const).map(([value, label, count]) => <button type="button" key={value} className={queue === value ? 'active' : ''} onClick={() => updateQueue(value)}>{label}<b>{count}</b></button>)}</div><div className="grn-filters"><label><Search size={14} /><input aria-label="Search goods received notes" placeholder="Search GRN, PO, supplier or material" value={search} onChange={(event) => updateFilter(() => setSearch(event.target.value))} /></label><select aria-label="Filter GRNs by destination" className={inputClass} value={destination} onChange={(event) => updateFilter(() => setDestination(event.target.value))}><option value="">Warehouse / Site</option><option value="WAREHOUSE">Main warehouse</option><option value="SITE">Direct to site</option></select><select aria-label="Filter GRNs by status" className={inputClass} value={status} onChange={(event) => updateFilter(() => setStatus(event.target.value))}><option value="">Status</option><option value="ACCEPTED">Accepted</option><option value="REVERSED">Reversed</option></select><label className="grn-date-range"><CalendarDays size={14} /><input aria-label="Filter GRNs from date" type="date" value={fromDate} onChange={(event) => updateFilter(() => setFromDate(event.target.value))} /><span>–</span><input aria-label="Filter GRNs to date" type="date" value={toDate} onChange={(event) => updateFilter(() => setToDate(event.target.value))} /></label><select aria-label="Sort goods received notes" className={inputClass} value={sort} onChange={(event) => updateFilter(() => setSort(event.target.value as typeof sort))}><option value="newest">Sort: Newest first</option><option value="oldest">Sort: Oldest first</option></select></div><div className="grn-table-wrap"><table className="grn-table"><thead><tr><th>GRN</th><th>Purchase order</th><th>Supplier</th><th>Destination</th><th>Received</th><th>Receiver</th><th>Materials</th><th>Condition</th><th>Stock posting</th><th>Status</th><th>Actions</th><th aria-label="More actions" /></tr></thead><tbody>{displayedRows.map((row) => <ReceiptRow key={row.note.id} row={row} onView={() => setSelected(row.note)} onDownload={() => void download(row.note)} />)}</tbody></table>{!displayedRows.length ? <p className="grn-empty">{notes.isLoading || orders.isLoading ? 'Loading goods received notes…' : 'No GRNs match this view.'}</p> : null}</div><footer className="grn-table-footer"><span>Showing {pageStart} to {pageEnd} of {filteredRows.length} goods received notes</span><span><button type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>‹</button><b>{page}</b><button type="button" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>›</button></span></footer></div><aside className="grn-side-column"><section className="grn-quality-panel"><div className="grn-panel-heading"><h2>Receiving quality</h2></div><div className="grn-quality-body"><div className="grn-donut" style={{ background: totalQuality ? `conic-gradient(#138d68 0 ${acceptedPercent}%, #ef9c27 ${acceptedPercent}% ${acceptedPercent + rejectedPercent}%, #db4a56 ${acceptedPercent + rejectedPercent}% ${acceptedPercent + rejectedPercent + damagedPercent}%, #e9edef ${acceptedPercent + rejectedPercent + damagedPercent}% 100%)` : '#e9edef' }}><strong>{totalQuality ? `${acceptedPercent}%` : '—'}</strong><small>{totalQuality ? 'accepted' : 'no receipts'}</small></div><div className="grn-quality-list"><QualityRow label="Accepted quantities" tone="accepted" value={acceptedPercent} quantity={activeRows.reduce((sum, row) => sum + row.accepted, 0)} /><QualityRow label="Rejected" tone="rejected" value={rejectedPercent} quantity={activeRows.reduce((sum, row) => sum + row.rejected, 0)} /><QualityRow label="Damaged" tone="damaged" value={damagedPercent} quantity={activeRows.reduce((sum, row) => sum + row.damaged, 0)} /></div></div></section><section className="grn-summary-panel"><div className="grn-panel-heading"><h2>Receipt destinations</h2></div><Link to="/procurement/deliveries?action_queue=warehouse_receipts"><Box size={17} /><span>Main warehouse<small>{warehouseRows.length} receipts</small></span><strong>{formatUGX(warehouseRows.reduce((sum, row) => sum + row.value, 0))}</strong></Link><Link to="/procurement/deliveries?action_queue=site_receipts"><Truck size={17} /><span>Direct to site<small>{siteRows.length} receipts</small></span><strong>{formatUGX(siteRows.reduce((sum, row) => sum + row.value, 0))}</strong></Link><div className="grn-total-value"><span>Total received value</span><strong>{formatUGX(activeRows.reduce((sum, row) => sum + row.value, 0))}</strong></div></section><section className="grn-verification-panel"><div className="grn-panel-heading"><h2>Verification queue</h2><Badge tone={exceptionRows.length ? 'warning' : 'success'}>{exceptionRows.length ? 'Attention' : 'All clear'}</Badge></div><Link to="/procurement/grns"><FileText size={17} /><span>Accepted GRNs<small>Permanent stock records</small></span><strong>{activeRows.length}</strong></Link><Link to="/procurement/deliveries?action_queue=site_receipts"><Truck size={17} /><span>Site confirmations<small>Direct-to-site receipt queue</small></span><strong>{allOrders.filter((order) => order.delivery_destination === 'SITE' && ['DISPATCH_CONFIRMED', 'PARTIAL'].includes(order.status)).length}</strong></Link><Link to="/procurement/supplier-claims"><CircleAlert size={17} /><span>Exceptions to resolve<small>Rejected or damaged receipt lines</small></span><strong>{exceptionRows.length}</strong></Link></section><section className="grn-reminder-panel"><CircleAlert size={17} /><div><strong>Control reminder</strong><p>A GRN records physical receipt; acceptance posts stock and becomes an auditable inventory record.</p></div></section></aside></section>
    <GrnDetail note={selected} onClose={() => setSelected(null)} />
  </div>;
}

function ReceiptRow({ row, onView, onDownload }: { row: ReceiptSummary; onView: () => void; onDownload: () => void }) {
  const condition = row.hasException ? 'Exception' : 'Good';
  return <tr><td><button type="button" className="grn-document-link" onClick={onView}>{row.note.number}</button><small>{row.note.items.length} material{row.note.items.length === 1 ? '' : 's'}</small></td><td><Link to={`/procurement/purchase-orders?search=${encodeURIComponent(row.note.purchase_order_number)}`}>{row.note.purchase_order_number}</Link></td><td>{row.order?.supplier_name || 'Supplier not recorded'}</td><td><Badge tone={row.order?.delivery_destination === 'SITE' ? 'info' : 'success'}>{row.order?.delivery_destination_display || 'Destination unavailable'}</Badge></td><td>{formatDate(row.note.receipt_date)}<small>{formatNumber(row.accepted)} accepted</small></td><td>{row.note.received_by_name || row.note.received_by_username || 'Recorded receiver'}</td><td>{row.note.items.length} material{row.note.items.length === 1 ? '' : 's'}<small><button type="button" onClick={onView}>View lines</button></small></td><td><Badge tone={row.hasException ? 'warning' : 'success'}>{condition}</Badge></td><td><Badge tone={row.note.status === 'ACCEPTED' && row.accepted > 0 ? 'success' : 'neutral'}>{row.note.status === 'ACCEPTED' && row.accepted > 0 ? 'Posted' : 'Not posted'}</Badge></td><td><Badge tone={statusTone(row.note.status)}>{row.note.status === 'ACCEPTED' ? 'Accepted' : 'Reversed'}</Badge></td><td><Button size="sm" variant="ghost" className="grn-view-action" onClick={onView}><Eye size={13} />View</Button></td><td><details className="grn-row-menu"><summary aria-label={`More actions for ${row.note.number}`}><EllipsisVertical size={16} /></summary><div><button type="button" onClick={onView}><Eye size={13} />View receipt</button><button type="button" onClick={onDownload}><Download size={13} />Download PDF</button></div></details></td></tr>;
}

function ReceiptKpi({ icon: Icon, tone, label, value, note }: { icon: typeof FileText; tone: string; label: string; value: number; note: string }) {
  return <article className="grn-kpi"><span className={`grn-kpi-icon ${tone}`}><Icon size={23} /></span><div><p>{label}</p><strong>{value}</strong><small>{note}</small></div></article>;
}

function QualityRow({ label, tone, value, quantity }: { label: string; tone: string; value: number; quantity: number }) {
  return <div className="grn-quality-row"><span><i className={tone} />{label}</span><b><strong>{formatNumber(quantity)}</strong><small>{value}%</small></b></div>;
}

function GrnDetail({ note, onClose }: { note: GoodsReceivedNote | null; onClose: () => void }) {
  return <FormModal open={!!note} title={note ? `GRN ${note.number}` : 'Goods received note'} onClose={onClose}>
    {note ? <div className="grid gap-4"><RecordContext items={[{ label: 'Purchase order', value: note.purchase_order_number }, { label: 'Receipt date', value: formatDate(note.receipt_date) }, { label: 'Received by', value: note.received_by_name || note.received_by_username || 'Recorded receiver' }, { label: 'Status', value: note.status, tone: statusTone(note.status) }]} />{note.notes ? <Field label="Receipt notes"><p className="rounded-lg border border-border bg-background p-3 text-sm">{note.notes}</p></Field> : null}<div className="grid gap-2"><h3 className="flex items-center gap-2 font-bold"><FileText className="h-4 w-4" />Received material lines</h3>{note.items.map((item) => <div key={item.id} className="grid gap-2 rounded-lg border border-border p-3 text-sm sm:grid-cols-[1fr_repeat(3,auto)] sm:items-center sm:gap-5"><div><strong>{item.material_name}</strong>{item.notes ? <p className="mt-1 text-xs text-muted">{item.notes}</p> : null}</div><Quantity label="Accepted" value={item.accepted_quantity} /><Quantity label="Rejected" value={item.rejected_quantity} warning={Number(item.rejected_quantity) > 0} /><Quantity label="Damaged" value={item.damaged_quantity} warning={Number(item.damaged_quantity) > 0} /></div>)}</div></div> : null}
  </FormModal>;
}

function Quantity({ label, value, warning = false }: { label: string; value: string; warning?: boolean }) {
  return <div className={warning ? 'text-warning' : ''}><span className="text-xs text-muted">{label}</span><strong className="block">{formatNumber(value)}</strong></div>;
}
