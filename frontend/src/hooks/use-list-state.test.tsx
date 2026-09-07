import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useListState } from './use-list-state';

describe('useListState', () => {
  it('resets pagination when search or filters change', () => {
    const { result } = renderHook(() => useListState({ status: '' }));

    act(() => result.current.setPage(3));
    expect(result.current.page).toBe(3);

    act(() => result.current.setSearch('late'));
    expect(result.current.page).toBe(1);
    expect(result.current.query).toEqual({ page: 1, search: 'late', status: '' });

    act(() => {
      result.current.setPage(4);
      result.current.setFilter('status', 'OPEN');
    });
    expect(result.current.page).toBe(1);
    expect(result.current.query.status).toBe('OPEN');
  });

  it('hydrates search and filters from a deep link and rehydrates when it changes', async () => {
    const { result, rerender } = renderHook(
      ({ key, search, queue }) => useListState(
        { status: '', action_queue: '' },
        { syncKey: key, initialSearch: search, initialFilters: { action_queue: queue } },
      ),
      { initialProps: { key: '?search=PO-1', search: 'PO-1', queue: 'my_requests' } },
    );

    expect(result.current.query).toEqual({ page: 1, search: 'PO-1', status: '', action_queue: 'my_requests' });

    rerender({ key: '?search=PO-2', search: 'PO-2', queue: '' });
    await waitFor(() => expect(result.current.query).toEqual({ page: 1, search: 'PO-2', status: '', action_queue: '' }));
  });
});
