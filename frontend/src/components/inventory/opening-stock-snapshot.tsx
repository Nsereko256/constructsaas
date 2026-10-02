import type { MaterialOpeningStockImportRow } from '@/api/types';
import { formatNumber, formatUGX } from '@/lib/utils';

export function OpeningStockSnapshot({ snapshot }: { snapshot: Record<string, unknown> }) {
  const rows = Array.isArray(snapshot.rows) ? snapshot.rows as MaterialOpeningStockImportRow[] : [];
  if (!rows.length) return <p role="alert">The submitted stock lines are unavailable. Do not post until the preparer resubmits a valid workbook.</p>;
  return <section aria-label="Submitted opening stock" className="mb-4 grid gap-2">
    <h3 className="font-semibold">Submitted stock lines</h3>
    <div className="max-h-64 overflow-auto rounded-md border border-border" tabIndex={0} aria-label="Scroll submitted stock lines">
      <table className="w-full min-w-[600px] text-left text-sm">
        <thead className="sticky top-0 bg-surface"><tr>{['Material', 'Warehouse code', 'Quantity', 'Unit cost', 'Value'].map((heading) => <th key={heading} className="p-3">{heading}</th>)}</tr></thead>
        <tbody>{rows.map((row, index) => <tr key={`${row.row}-${index}`} className="border-t border-border"><td className="p-3"><strong>{row.material_name}</strong><span className="block text-muted">{row.material_code}</span></td><td className="p-3">{row.warehouse_code}</td><td className="p-3 whitespace-nowrap">{formatNumber(row.opening_quantity)} {row.unit}</td><td className="p-3 whitespace-nowrap">{formatUGX(row.unit_cost)}</td><td className="p-3 whitespace-nowrap">{formatUGX(Number(row.opening_quantity) * Number(row.unit_cost))}</td></tr>)}</tbody>
      </table>
    </div>
    <p className="text-sm"><strong>Total opening value: {formatUGX(rows.reduce((sum, row) => sum + Number(row.opening_quantity) * Number(row.unit_cost), 0))}</strong></p>
  </section>;
}
