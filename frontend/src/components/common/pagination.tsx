import { Button } from '@/components/ui/button';
import type { Paginated } from '@/api/types';

export function Pagination<T>({ page, setPage, data, pageSize = 20 }: { page: number; setPage: (page: number) => void; data?: Paginated<T>; pageSize?: number }) {
  if (!data) return null;
  const totalPages = Math.max(1, Math.ceil(data.count / pageSize));
  if (totalPages <= 1 && !data.next && !data.previous) return null;
  const start = data.results.length ? (page - 1) * pageSize + 1 : 0;
  const end = data.results.length ? Math.min(start + data.results.length - 1, data.count) : 0;
  return (
    <nav className="flex flex-wrap items-center justify-between gap-3 border-t border-border/80 pt-3" aria-label="Pagination">
      <span className="text-xs font-medium text-muted">Showing {start}–{end} of {data.count}</span>
      <div className="flex items-center gap-2">
      <Button type="button" size="sm" variant="secondary" aria-label="Previous page" disabled={!data.previous || page <= 1} onClick={() => setPage(Math.max(1, page - 1))}>
        <span aria-hidden="true">‹</span><span className="hidden sm:inline">Previous</span>
      </Button>
      <span className="min-w-20 rounded-md border border-primary/20 bg-primary/5 px-3 py-1.5 text-center text-xs font-bold text-primary">{page} / {totalPages}</span>
      <Button type="button" size="sm" variant="secondary" aria-label="Next page" disabled={!data.next || page >= totalPages} onClick={() => setPage(Math.min(totalPages, page + 1))}>
        <span className="hidden sm:inline">Next</span><span aria-hidden="true">›</span>
      </Button>
      </div>
    </nav>
  );
}
