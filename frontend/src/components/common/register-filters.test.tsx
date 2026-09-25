import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RegisterFilters } from './register-filters';

describe('RegisterFilters', () => {
  it('keeps search separate and connects the mobile disclosure to its controls', () => {
    render(<RegisterFilters><input aria-label="Search inventory" /><select aria-label="Stock level"><option>All</option></select></RegisterFilters>);
    const toggle = screen.getByRole('button', { name: 'Filters' });
    const controls = document.getElementById(toggle.getAttribute('aria-controls')!);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(controls).toContainElement(screen.getByRole('combobox'));
    expect(controls).not.toContainElement(screen.getByRole('textbox'));
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(controls).toHaveClass('is-open');
    fireEvent.click(toggle);
    expect(controls).not.toHaveClass('is-open');
  });

  it('shows the active count and delegates reset to the page without changing data', () => {
    const clear = vi.fn();
    const { rerender } = render(<RegisterFilters activeCount={2} onClear={clear}><input aria-label="Search" /></RegisterFilters>);
    expect(screen.getByRole('status')).toHaveTextContent('2 active filters');
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(clear).toHaveBeenCalledOnce();
    rerender(<RegisterFilters activeCount={0} onClear={clear}><input aria-label="Search" /></RegisterFilters>);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
