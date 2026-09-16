import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowDownToLine, CheckCircle2, Download, FileSpreadsheet, XCircle } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { api } from '@/api/services';
import type { MaterialOpeningStockImportPreview, MaterialOpeningStockImportResult } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { formatNumber, formatUGX } from '@/lib/utils';

function localDate() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

const importColumns = [
  { name: 'Material code', required: true },
  { name: 'Material name', required: true },
  { name: 'Category', required: true },
  { name: 'Unit', required: true },
  { name: 'Warehouse code', required: true },
  { name: 'Opening quantity', required: true },
  { name: 'Unit cost', required: true },
  { name: 'Minimum stock', required: false },
  { name: 'Description', required: false },
] as const;

function downloadErrors(preview: MaterialOpeningStockImportPreview) {
  const quote = (value: string | number) => `"${String(value).replaceAll('"', '""')}"`;
  const rows = [
    ['Excel row', 'Material code', 'Material name', 'Warehouse', 'Errors'],
    ...preview.rows.filter((row) => row.errors.length).map((row) => [row.row, row.material_code, row.material_name, row.warehouse_code, row.errors.join(' | ')]),
  ];
  const blob = new Blob([rows.map((row) => row.map(quote).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'materials-opening-stock-errors.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

export function OpeningStockImportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [openingDate, setOpeningDate] = useState(localDate);
  const [reason, setReason] = useState('Company onboarding opening stock');
  const [preview, setPreview] = useState<MaterialOpeningStockImportPreview | null>(null);
  const [result, setResult] = useState<MaterialOpeningStockImportResult | null>(null);

  const close = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setOpeningDate(localDate());
    setReason('Company onboarding opening stock');
    onClose();
  };

  const previewMutation = useMutation({
    mutationFn: () => api.previewOpeningStockImport(file as File),
    onSuccess: (data) => setPreview(data),
    onError: (error: Error) => toast.push({ title: 'Workbook could not be previewed', message: error.message, tone: 'danger' }),
  });
  const confirmMutation = useMutation({
    mutationFn: () => api.confirmOpeningStockImport(file as File, openingDate, reason),
    onSuccess: (data) => {
      setResult(data);
      void queryClient.invalidateQueries({ queryKey: ['materials'] });
      void queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
      toast.push({ title: 'Opening stock imported', message: `${data.opening_balances} opening balances were posted.`, tone: 'success' });
    },
    onError: (error: Error) => toast.push({ title: 'Import was not posted', message: error.message, tone: 'danger' }),
  });

  const downloadTemplate = async () => {
    try {
      await api.downloadOpeningStockTemplate();
      toast.push({ title: 'Excel template downloaded', tone: 'success' });
    } catch (error) {
      toast.push({ title: 'Template download failed', message: (error as Error).message, tone: 'danger' });
    }
  };

  return (
    <Dialog open={open} onOpenChange={(value) => !value && close()}>
      <DialogContent title="Import materials with opening stock" description="Create or match materials and post their verified opening balances from Excel." variant="form" className="max-w-6xl">
        {result ? (
          <div className="grid gap-5">
            <div className="rounded-lg border border-success/30 bg-success/5 p-5">
              <div className="flex items-center gap-3"><CheckCircle2 className="h-7 w-7 text-success" /><div><h3 className="font-black">Import completed</h3><p className="text-sm text-muted">The workbook was posted as one controlled transaction and recorded in the audit trail.</p></div></div>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Summary label="Rows" value={result.rows} />
              <Summary label="Materials created" value={result.materials_created} />
              <Summary label="Materials matched" value={result.materials_matched} />
              <Summary label="Categories created" value={result.categories_created} />
              <Summary label="Balances posted" value={result.opening_balances} />
            </div>
            <div className="flex justify-end"><Button onClick={close}>Done</Button></div>
          </div>
        ) : (
          <div className="grid gap-4">
            <div className="flex flex-col gap-3 rounded-lg border border-warning/35 bg-warning/5 p-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" /><div><strong className="block">Use only for company onboarding</strong><p className="text-sm text-muted">Opening stock is blocked where a material and warehouse already have ledger activity. Replace or remove the example row before upload.</p></div></div>
              <Button variant="secondary" className="shrink-0" onClick={() => void downloadTemplate()}><Download className="h-4 w-4" />Download template</Button>
            </div>

            <section aria-label="Excel import requirements" className="rounded-lg border border-border bg-surface/55 p-4">
              <div className="mb-3 flex items-start gap-2">
                <FileSpreadsheet className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div><h3 className="font-black">Excel file requirements</h3><p className="text-xs text-muted">Use the downloaded template and keep the required headings unchanged.</p></div>
              </div>
              <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
                <Requirement title="File"><strong>.xlsx only</strong><span>Maximum 5 MB and 1,000 material rows.</span></Requirement>
                <Requirement title="Column order"><strong>9 columns, left to right</strong><span>Keep the names and sequence shown below.</span></Requirement>
                <Requirement title="Accepted units"><strong>bag · ton · kg · litre</strong><span>piece · metre · sqm · cbm</span></Requirement>
                <Requirement title="Stock rules"><strong>Use active warehouse codes</strong><span>See the Warehouse reference sheet. Values must be zero or greater.</span></Requirement>
              </div>
              <div className="mt-3 rounded-md border border-primary/20 bg-white p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-black uppercase tracking-wide text-foreground">Excel columns in template order</p>
                    <p className="text-xs text-muted">Name each heading exactly as shown and arrange the columns from 1 to 9.</p>
                  </div>
                  <span className="rounded-full bg-surface-muted px-2.5 py-1 text-[11px] font-bold text-muted">Columns 8–9 are optional</span>
                </div>
                <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {importColumns.map((column, index) => (
                    <li key={column.name} className="flex min-w-0 items-center gap-2 rounded-md border border-border bg-surface/60 px-3 py-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-black text-white">{index + 1}</span>
                      <strong className="min-w-0 flex-1 text-sm">{column.name}</strong>
                      <span className={`text-[10px] font-bold uppercase tracking-wide ${column.required ? 'text-primary' : 'text-muted'}`}>{column.required ? 'Required' : 'Optional'}</span>
                    </li>
                  ))}
                </ol>
              </div>
              <p className="mt-3 border-t border-border pt-3 text-xs text-muted"><strong className="text-foreground">Important:</strong> repeat a material only when loading it into a different warehouse, keep its name/category/unit identical, and do not load opening stock where that material and warehouse already have movement history.</p>
            </section>

            <div className="grid gap-3 md:grid-cols-[1.3fr_.7fr_1fr]">
              <Field label="Completed Excel template (.xlsx)" required>
                <label className="flex min-h-10 cursor-pointer items-center gap-2 rounded-md border border-border bg-white px-3 text-sm font-semibold hover:border-primary">
                  <FileSpreadsheet className="h-4 w-4 text-primary" />
                  <span className="min-w-0 flex-1 truncate">{file?.name || 'Choose an .xlsx workbook'}</span>
                  <input className="sr-only" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); }} />
                </label>
              </Field>
              <Field label="Opening stock date" required><input className={inputClass} type="date" max={localDate()} value={openingDate} onChange={(event) => setOpeningDate(event.target.value)} /></Field>
              <Field label="Audit reason" required><input className={inputClass} value={reason} onChange={(event) => setReason(event.target.value)} /></Field>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">Previewing validates the workbook without changing inventory.</p>
              <Button disabled={!file || previewMutation.isPending} onClick={() => previewMutation.mutate()}><ArrowDownToLine className="h-4 w-4" />{previewMutation.isPending ? 'Checking workbook…' : preview ? 'Refresh preview' : 'Preview import'}</Button>
            </div>

            {preview ? (
              <>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                  <Summary label="Rows" value={preview.total_rows} />
                  <Summary label="Valid" value={preview.valid_rows} tone="success" />
                  <Summary label="Need correction" value={preview.invalid_rows} tone={preview.invalid_rows ? 'danger' : ''} />
                  <Summary label="New materials" value={preview.new_materials} />
                  <Summary label="Matched" value={preview.existing_materials} />
                  <Summary label="New categories" value={preview.new_categories} />
                </div>
                {preview.invalid_rows ? <div className="flex items-center justify-between gap-3 rounded-md border border-critical/25 bg-critical/5 p-3 text-sm"><span className="flex items-center gap-2"><XCircle className="h-4 w-4 text-critical" /><strong>Correct every flagged row and preview the workbook again.</strong></span><Button variant="secondary" size="sm" onClick={() => downloadErrors(preview)}><Download className="h-4 w-4" />Error report</Button></div> : null}
                <div className="max-h-[42vh] overflow-auto rounded-lg border border-border">
                  <table className="w-full min-w-[980px] text-left text-sm">
                    <thead className="sticky top-0 z-10 bg-surface-muted text-xs uppercase tracking-wide text-muted"><tr><th className="p-3">Row</th><th className="p-3">Material</th><th className="p-3">Category</th><th className="p-3">Warehouse</th><th className="p-3">Opening stock</th><th className="p-3">Unit cost</th><th className="p-3">Resolution</th><th className="p-3">Validation</th></tr></thead>
                    <tbody>{preview.rows.map((row) => <tr key={`${row.row}-${row.material_code}-${row.warehouse_code}`} className="border-t border-border align-top"><td className="p-3 font-semibold">{row.row}</td><td className="p-3"><strong>{row.material_name}</strong><small className="block text-muted">{row.material_code} · {row.unit}</small></td><td className="p-3">{row.category}<small className="block text-muted">{row.category_status}</small></td><td className="p-3 font-semibold">{row.warehouse_code}</td><td className="p-3">{formatNumber(row.opening_quantity)}</td><td className="p-3">{formatUGX(row.unit_cost)}</td><td className="p-3"><Badge tone={row.material_status === 'New' ? 'info' : 'neutral'}>{row.material_status}</Badge></td><td className="max-w-xs p-3">{row.errors.length ? <ul className="grid gap-1 text-xs font-semibold text-critical">{row.errors.map((error) => <li key={error}>• {error}</li>)}</ul> : <span className="flex items-center gap-1 font-semibold text-success-foreground"><CheckCircle2 className="h-4 w-4" />Ready</span>}</td></tr>)}</tbody>
                  </table>
                </div>
                <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-xs text-muted">Confirmation creates new master records where needed and posts all balances atomically. If one row fails, nothing is saved.</p>
                  <Button disabled={preview.invalid_rows > 0 || !openingDate || reason.trim().length < 5 || confirmMutation.isPending} onClick={() => confirmMutation.mutate()}><CheckCircle2 className="h-4 w-4" />{confirmMutation.isPending ? 'Posting opening stock…' : `Confirm ${preview.total_rows} rows`}</Button>
                </div>
              </>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Summary({ label, value, tone = '' }: { label: string; value: number; tone?: 'success' | 'danger' | '' }) {
  return <div className={`rounded-lg border p-3 ${tone === 'success' ? 'border-success-border bg-success' : tone === 'danger' ? 'border-critical/30 bg-critical/5' : 'border-border bg-white'}`}><p className="text-xs font-semibold text-muted">{label}</p><strong className="mt-1 block text-xl">{value}</strong></div>;
}

function Requirement({ title, children }: { title: string; children: ReactNode }) {
  return <div className="rounded-md border border-border bg-white p-3"><p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-muted">{title}</p><div className="grid gap-0.5"><>{children}</></div></div>;
}
