import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ExportButton } from './export-button';

describe('ExportButton', () => {
  it('renders the supplied label and invokes the export action', () => {
    const onClick = vi.fn();
    render(<ExportButton label="PDF" onClick={onClick} />);

    fireEvent.click(screen.getByRole('button', { name: 'PDF' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
