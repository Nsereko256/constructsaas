import { useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Paginated } from '@/api/types';

/** Bounded page links, even for registers with thousands of pages. */
export function paginationPages(page: number, total: number): (number | string)[] {
  const pages = [...new Set([1, total, page - 1, page, page + 1])]
    .filter((value) => value >= 1 && value <= total).sort((a, b) => a - b);
  return pages.flatMap<number | string>((value, index) => {
    const previous = pages[index - 1];
    if (index && value - previous === 2) return [previous + 1, value];
    if (index && value - previous > 2) return [`gap-${value}`, value];
    return [value];
  });
}

export function Pagination<T>({ page, setPage, data: incomingData, pageSize = 20, loading = false, itemLabel = 'records' }: {
  page: number;
  setPage: (page: number) => void;
  data?: Paginated<T>;
  pageSize?: number;
  loading?: boolean;
  itemLabel?: string;
}) {
  const navigation = useRef<HTMLElement>(null);
  const lastData = useRef<Paginated<T>>();
  useEffect(() => { if (incomingData) lastData.current = incomingData; }, [incomingData]);
  // Do not remove the focused pager while the next server page is loading.
  const data = incomingData || (loading ? lastData.current : undefined);
  if (!data) return null;
  const totalPages = Math.max(1, Math.ceil(data.count / pageSize));
  const start = data.results.length ? (page - 1) * pageSize + 1 : 0;
  const end = data.results.length ? Math.min(start + data.results.length - 1, data.count) : 0;
  const changePage = (next: number) => {
    if (loading || next === page || next < 1 || next > totalPages) return;
    setPage(next);
    // Keep the register in view rather than leaving the reader below its new rows.
    const region = navigation.current?.closest('[data-pagination-region]');
    if (region && region.getBoundingClientRect().top < 64) region.scrollIntoView({ block: 'start', behavior: 'instant' });
  };
  return (
    <nav ref={navigation} className="register-pagination" aria-label="Pagination" aria-busy={loading}>
      <span className="pagination-range" role="status">{loading ? `Loading page ${page}…` : <>Showing {start}–{end} of {data.count}<span className="pagination-item-label"> {itemLabel}</span></>}</span>
      {totalPages > 1 || data.next || data.previous ? <div className="pagination-controls">
        <button type="button" className="pagination-step" aria-label="Previous page" disabled={loading || !data.previous || page <= 1} onClick={() => changePage(page - 1)}><ChevronLeft size={16} aria-hidden="true" /><span>Previous</span></button>
        <span className="pagination-mobile-position">Page {page} of {totalPages}</span>
        <div className="pagination-pages">
          {paginationPages(page, totalPages).map((value) => typeof value === 'number'
            ? <button key={value} type="button" aria-label={`Page ${value}`} aria-current={value === page ? 'page' : undefined} disabled={loading} onClick={() => changePage(value)}>{value}</button>
            : <span key={value} aria-hidden="true">…</span>)}
        </div>
        <button type="button" className="pagination-step" aria-label="Next page" disabled={loading || !data.next || page >= totalPages} onClick={() => changePage(page + 1)}><span>Next</span><ChevronRight size={16} aria-hidden="true" /></button>
      </div> : null}
    </nav>
  );
}
