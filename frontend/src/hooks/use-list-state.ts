import { useEffect, useRef, useState } from 'react';

type ListStateOptions<T extends Record<string, string>> = {
  /** Values read from a deep-link query string on the first render. */
  initialSearch?: string;
  initialPage?: number;
  initialFilters?: Partial<T>;
  /** Change this when the route query string changes to rehydrate the list. */
  syncKey?: string;
};

export function useListState<T extends Record<string, string> = Record<string, string>>(
  defaults = {} as T,
  options: ListStateOptions<T> = {},
) {
  const initialFilters = { ...defaults, ...options.initialFilters } as T;
  const [page, setPage] = useState(options.initialPage || 1);
  const [search, setSearchValue] = useState(options.initialSearch || '');
  const [filters, setFilters] = useState<T>(initialFilters);
  const lastSyncKey = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (options.syncKey === undefined || lastSyncKey.current === options.syncKey) return;
    lastSyncKey.current = options.syncKey;
    setPage(options.initialPage || 1);
    setSearchValue(options.initialSearch || '');
    setFilters((current) => ({ ...current, ...options.initialFilters } as T));
  }, [options.initialFilters, options.initialPage, options.initialSearch, options.syncKey]);

  const setSearch = (value: string) => {
    setSearchValue(value);
    setPage(1);
  };
  const setFilter = (key: string, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  };
  return {
    page,
    setPage,
    search,
    setSearch,
    filters,
    setFilter,
    query: { page, search, ...filters } as { page: number; search: string } & T,
  };
}
