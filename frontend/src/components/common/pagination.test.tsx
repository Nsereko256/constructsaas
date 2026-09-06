import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Pagination } from './pagination';

describe('Pagination', () => {
  it('shows controls when a compact page has more records even below the default page size', () => {
    const setPage = vi.fn();
    render(<Pagination page={1} pageSize={5} setPage={setPage} data={{ count: 9, previous: null, next: '/api/items?page=2', results: [1, 2, 3, 4, 5] }} />);

    expect(screen.getByText('Showing 1–5 of 9')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(setPage).toHaveBeenCalledWith(2);
  });

  it('stays hidden for a list that fits on one page', () => {
    const { container } = render(<Pagination page={1} setPage={vi.fn()} data={{ count: 2, previous: null, next: null, results: [1, 2] }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
