import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReasonDialog } from './reason-dialog';

describe('ReasonDialog', () => {
  const props = { open: true, title: 'Return MR-1', description: 'Explain the correction.', confirmLabel: 'Return for correction', pending: false, minLength: 10, onClose: vi.fn(), onConfirm: vi.fn() };
  it('validates the reason and preserves it after submission', () => {
    render(<ReasonDialog {...props} />);
    const reason = screen.getByRole('textbox');
    const submit = screen.getByRole('button', { name: 'Return for correction' });
    expect(submit).toBeDisabled();
    fireEvent.change(reason, { target: { value: 'Please correct the requested quantity.' } });
    fireEvent.click(submit);
    expect(props.onConfirm).toHaveBeenCalledWith('Please correct the requested quantity.', undefined);
    expect(reason).toHaveValue('Please correct the requested quantity.');
  });
  it('asks before discarding an unsent reason', () => {
    const close = vi.fn(); render(<ReasonDialog {...props} onClose={close} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'My unsent explanation' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(close).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(close).toHaveBeenCalledOnce();
  });
  it('does not close or resubmit while saving', () => {
    const close = vi.fn(); render(<ReasonDialog {...props} pending onClose={close} />);
    fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }));
    expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole('textbox')).toBeDisabled();
  });
  it('requires a separate explanation for controlled Admin decisions', () => {
    const confirm = vi.fn(); render(<ReasonDialog {...props} requireOverrideReason onConfirm={confirm} error="Previous attempt was not saved." />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason required' }), { target: { value: 'Please correct the site quantity.' } });
    const submit = screen.getByRole('button', { name: 'Return for correction' });
    expect(submit).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Previous attempt was not saved.');
    fireEvent.change(screen.getByRole('textbox', { name: 'Admin override reason required' }), { target: { value: 'Independent reviewer unavailable; local QA decision.' } });
    fireEvent.click(submit);
    expect(confirm).toHaveBeenCalledWith('Please correct the site quantity.', 'Independent reviewer unavailable; local QA decision.');
  });
});
