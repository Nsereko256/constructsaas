import { useState } from 'react';

export function useListState<T extends Record<string, string> = Record<string, string>>(defaults = {} as T) {
  const [page, setPage] = useState(1);
  const [search, setSearchValue] = useState('');
  const [filters, setFilters] = useState<T>(defaults);
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
