import { act, renderHook } from '@testing-library/react';
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
});
