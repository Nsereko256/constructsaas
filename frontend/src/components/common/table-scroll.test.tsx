import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TableScroll } from './table-scroll';

describe('TableScroll', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('matchMedia', () => ({ matches: true }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('adds controls only when columns overflow and respects both edges', () => {
    const { container } = render(<TableScroll label="Orders"><table><tbody><tr><td>PO-1</td></tr></tbody></table></TableScroll>);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    const viewport = container.querySelector('.table-scroll-viewport')!;
    const scrollBy = vi.fn();
    Object.defineProperties(viewport, { clientWidth: { value: 400 }, scrollWidth: { value: 900 }, scrollLeft: { value: 0, writable: true }, scrollBy: { value: scrollBy } });
    fireEvent.scroll(viewport);
    expect(screen.getByRole('region', { name: 'Orders' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('button', { name: 'Scroll orders left' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Scroll orders right' }));
    expect(scrollBy).toHaveBeenCalledWith({ left: 300, behavior: 'instant' });
    viewport.scrollLeft = 500;
    fireEvent.scroll(viewport);
    expect(screen.getByRole('button', { name: 'Scroll orders right' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Scroll orders left' })).toBeEnabled();
  });
});
