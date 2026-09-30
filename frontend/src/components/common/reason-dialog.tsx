import { useEffect, useState } from 'react';
import { FormModal } from './form-modal';
import { Button } from '@/components/ui/button';
import { Field, inputClass } from '@/components/ui/field';

export function ReasonDialog({ open, title, description, confirmLabel, pending, onClose, onConfirm, minLength = 1, requireOverrideReason = false, error }: {
  open: boolean; title: string; description: string; confirmLabel: string; pending: boolean;
  onClose: () => void; onConfirm: (reason: string, overrideReason?: string) => void; minLength?: number;
  requireOverrideReason?: boolean; error?: string;
}) {
  const [reason, setReason] = useState('');
  const [overrideReason, setOverrideReason] = useState('');
  const [discarding, setDiscarding] = useState(false);
  useEffect(() => { if (open) { setReason(''); setOverrideReason(''); setDiscarding(false); } }, [open, title]);
  useEffect(() => {
    if (!open || (!reason.trim() && !overrideReason.trim())) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [open, reason, overrideReason]);
  const reasonValid = reason.trim().length >= minLength;
  const valid = reasonValid && (!requireOverrideReason || overrideReason.trim().length >= 10);
  const close = () => { if (pending) return; if (reason.trim() || overrideReason.trim()) setDiscarding(true); else onClose(); };
  return <FormModal open={open} title={title} onClose={close}>
    <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); if (valid && !pending) onConfirm(reason.trim(), requireOverrideReason ? overrideReason.trim() : undefined); }}>
      <p className="text-sm text-muted">{description}</p>
      <Field label="Reason" required error={reason.length > 0 && !reasonValid ? `Enter at least ${minLength} characters.` : undefined}>
        <textarea autoFocus required minLength={minLength} className={inputClass} rows={4} value={reason} disabled={pending} onChange={(event) => setReason(event.target.value)} />
      </Field>
      {requireOverrideReason ? <>
        <p className="mb-2 text-sm text-muted">You also prepared this request. Explain why you are making this decision instead of an independent reviewer. Both reasons are recorded.</p>
        <Field label="Admin override reason" required error={overrideReason.length > 0 && overrideReason.trim().length < 10 ? 'Enter at least 10 characters.' : undefined}>
        <textarea required minLength={10} className={inputClass} rows={3} disabled={pending} value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} />
      </Field></> : null}
      {error ? <p role="alert" className="rounded border border-critical/30 bg-critical/5 p-3 text-sm">{error}</p> : null}
      {discarding ? <div role="alert" className="rounded border border-border bg-background p-3 text-sm"><p>Discard this unsent reason?</p><div className="mt-3 flex gap-2"><Button type="button" variant="secondary" onClick={() => setDiscarding(false)}>Keep editing</Button><Button type="button" variant="destructive" onClick={onClose}>Discard changes</Button></div></div> : null}
      <div className="flex justify-end gap-2"><Button type="button" variant="secondary" disabled={pending} onClick={close}>Cancel</Button><Button disabled={!valid || discarding} loading={pending} loadingLabel="Saving decision">{confirmLabel}</Button></div>
    </form>
  </FormModal>;
}
