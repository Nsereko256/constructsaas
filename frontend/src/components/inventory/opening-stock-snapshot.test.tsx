import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OpeningStockSnapshot } from './opening-stock-snapshot';

describe('Opening-stock review snapshot', () => {
  it('shows the exact warehouse, per-material units and total value without summing unlike quantities', () => {
    render(<OpeningStockSnapshot snapshot={{ rows: [
      { row: 2, material_code: 'CEM', material_name: 'Cement', warehouse_code: 'QA-MAIN', opening_quantity: '12', unit: 'bag', unit_cost: '35000' },
      { row: 3, material_code: 'PAINT', material_name: 'Paint', warehouse_code: 'QA-MAIN', opening_quantity: '6', unit: 'litre', unit_cost: '20000' },
    ] }} />);
    expect(screen.getByText('12 bag')).toBeVisible();
    expect(screen.getByText('6 litre')).toBeVisible();
    expect(screen.getAllByText('QA-MAIN')).toHaveLength(2);
    expect(screen.getByText('Total opening value: UGX 540,000')).toBeVisible();
  });
  it('does not present missing lines as a valid zero stock snapshot', () => {
    render(<OpeningStockSnapshot snapshot={{}} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Do not post');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
