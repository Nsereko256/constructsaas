import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Pagination, paginationPages } from './pagination';

describe('Pagination', () => {
  it('shows controls when a compact page has more records even below the default page size', () => {
    const setPage = vi.fn();
    render(<Pagination page={1} pageSize={5} setPage={setPage} data={{ count: 9, previous: null, next: '/api/items?page=2', results: [1, 2, 3, 4, 5] }} />);

    expect(screen.getByText('Showing 1–5 of 9')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(setPage).toHaveBeenCalledWith(2);
  });

  it('keeps the record count without unnecessary controls for one page', () => {
    render(<Pagination page={1} setPage={vi.fn()} data={{ count: 2, previous: null, next: null, results: [1, 2] }} />);
    expect(screen.getByRole('status')).toHaveTextContent('Showing 1–2 of 2');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('supports direct navigation and shows the current page', () => {
    const setPage = vi.fn();
    render(<Pagination page={3} pageSize={5} setPage={setPage} data={{ count: 52, previous: '/previous', next: '/next', results: [1, 2, 3, 4, 5] }} />);
    expect(screen.getByRole('button', { name: 'Page 3' })).toHaveAttribute('aria-current', 'page');
    fireEvent.click(screen.getByRole('button', { name: 'Page 11' }));
    expect(setPage).toHaveBeenCalledWith(11);
    expect(screen.getByRole('status')).toHaveTextContent('Showing 11–15 of 52');
  });

  it('prevents paging past the last page or while loading', () => {
    const setPage = vi.fn();
    const { rerender } = render(<Pagination page={2} pageSize={5} setPage={setPage} data={{ count: 6, previous: '/previous', next: null, results: [6] }} />);
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('Showing 6–6 of 6');
    rerender(<Pagination page={2} pageSize={5} loading setPage={setPage} data={{ count: 6, previous: '/previous', next: null, results: [6] }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }));
    expect(setPage).not.toHaveBeenCalled();
  });

  it('handles empty results and keeps page links bounded', () => {
    render(<Pagination page={1} setPage={vi.fn()} data={{ count: 0, previous: null, next: null, results: [] }} />);
    expect(screen.getByRole('status')).toHaveTextContent('Showing 0–0 of 0');
    expect(paginationPages(50, 100)).toEqual([1, 'gap-49', 49, 50, 51, 'gap-100', 100]);
    expect(paginationPages(1, 1)).toEqual([1]);
  });

  it('keeps navigation visible while a server page loads', () => {
    const setPage = vi.fn();
    const { rerender } = render(<Pagination page={1} pageSize={5} setPage={setPage} data={{ count: 9, previous: null, next: '/next', results: [1, 2, 3, 4, 5] }} />);
    rerender(<Pagination page={2} pageSize={5} setPage={setPage} loading />);
    expect(screen.getByRole('navigation', { name: 'Pagination' })).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('Loading page 2');
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });
});
