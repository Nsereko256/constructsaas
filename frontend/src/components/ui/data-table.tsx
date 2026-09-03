import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { cn } from '@/lib/utils';
import { EmptyState } from './empty-state';

export function DataTable<T>({
  columns,
  data,
  emptyTitle = 'No records found',
  mobileSummaryCells = 3,
  mobileSummaryStacked = false,
  mobileCardClassName,
}: {
  columns: ColumnDef<T>[];
  data: T[];
  emptyTitle?: string;
  /** Number of leading columns shown before the compact mobile detail disclosure. */
  mobileSummaryCells?: number;
  /** Stack the leading summary cells on narrow screens when one cell contains long status text. */
  mobileSummaryStacked?: boolean;
  mobileCardClassName?: string;
}) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });

  if (!data.length) return <EmptyState title={emptyTitle} />;

  return (
    <div className="card-surface overflow-hidden">
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-surface text-xs uppercase tracking-wide text-muted">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="px-4 py-3 font-bold">
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-t border-border transition-colors hover:bg-primary/[0.025]">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-3 align-top">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid gap-2 p-2.5 md:hidden">
        {table.getRowModel().rows.map((row) => {
          const cells = row.getVisibleCells();
          const actionCell = cells.find((cell) => cell.column.id === 'actions');
          const contentCells = cells.filter((cell) => cell.column.id !== 'actions');
          const primaryCells = contentCells.slice(0, mobileSummaryCells);
          const detailCells = contentCells.slice(mobileSummaryCells);
          return (
            <article key={row.id} className={cn('card-surface card-surface-interactive', mobileCardClassName)}>
              <div className={mobileSummaryStacked ? 'grid min-w-0 gap-2.5 p-2.5' : 'grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,42%)] items-start gap-2.5 p-2.5'}>
                <div className="min-w-0 text-sm">
                  {primaryCells[0] ? flexRender(primaryCells[0].column.columnDef.cell, primaryCells[0].getContext()) : null}
                </div>
                <div className={mobileSummaryStacked ? 'grid min-w-0 gap-1.5 text-left text-xs' : 'grid min-w-0 justify-items-end gap-1.5 overflow-hidden text-right text-xs'}>
                  {primaryCells.slice(1).map((cell) => (
                    <div key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</div>
                  ))}
                </div>
              </div>
              {actionCell ? <div className="flex flex-wrap gap-2 border-t border-border bg-background px-2.5 py-2.5">{flexRender(actionCell.column.columnDef.cell, actionCell.getContext())}</div> : null}
              {detailCells.length ? (
                <details className="border-t border-border">
                  <summary className="cursor-pointer px-2.5 py-2 text-xs font-bold text-primary marker:text-primary">More details and actions</summary>
                  <div className="grid gap-2 border-t border-border bg-background px-2.5 py-2.5">
                    {detailCells.map((cell) => (
                      <div key={cell.id} className="text-sm">
                        {typeof cell.column.columnDef.header === 'string' && cell.column.columnDef.header ? <p className="mb-0.5 text-[10px] font-bold uppercase tracking-wide text-muted">{cell.column.columnDef.header}</p> : null}
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </div>
                    ))}
                  </div>
                </details>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
