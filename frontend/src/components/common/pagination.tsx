import { Button } from '@/components/ui/button';
import type { Paginated } from '@/api/types';

export function Pagination<T>({ page, setPage, data }: { page: number; setPage: (page: number) => void; data?: Paginated<T> }) {
  if (!data || data.count <= 20) return null;
  return (
    <div className="flex items-center justify-end gap-2">
      <Button variant="secondary" disabled={!data.previous} onClick={() => setPage(Math.max(1, page - 1))}>
        Previous
      </Button>
      <span className="rounded-md border border-border bg-white px-3 py-2 text-sm font-semibold">Page {page}</span>
      <Button variant="secondary" disabled={!data.next} onClick={() => setPage(page + 1)}>
        Next
      </Button>
    </div>
  );
}
