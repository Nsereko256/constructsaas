import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Button } from './button';

describe('Button', () => {
  it('locks and announces an action while it is loading', () => {
    render(<Button loading loadingLabel="Approving">Approve</Button>);

    const button = screen.getByRole('button', { name: 'Approving' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });

  it('restores the normal label when it is idle', () => {
    render(<Button loading={false} loadingLabel="Submitting">Submit</Button>);

    expect(screen.getByRole('button', { name: 'Submit' })).toBeEnabled();
  });
});
