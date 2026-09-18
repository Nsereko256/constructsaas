import { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { FormModal } from '@/components/common/form-modal';
import { Button } from '@/components/ui/button';
import { Field, inputClass } from '@/components/ui/field';

export function ControlledApprovalModal({
  open,
  recordNumber,
  pending,
  onClose,
  onApprove,
  recordType = 'material request',
}: {
  open: boolean;
  recordNumber: string;
  pending: boolean;
  onClose: () => void;
  onApprove: (overrideReason: string) => void;
  recordType?: string;
}) {
  const [reason, setReason] = useState('');
  useEffect(() => setReason(''), [open, recordNumber]);
  const valid = reason.trim().length >= 10;

  return (
    <FormModal open={open} title={`Approve ${recordNumber || recordType}`} onClose={onClose}>
      <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); if (valid) onApprove(reason.trim()); }}>
        <div className="flex gap-3 rounded-lg border border-warning/35 bg-warning/5 p-4 text-sm">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-warning" />
          <div><strong>Controlled administrator override</strong><p className="mt-1 text-muted">You prepared this {recordType} and are now approving it. Record why the normal maker-checker separation cannot be used. This reason is retained in the audit trail.</p></div>
        </div>
        <Field label="Override reason" required error={reason.length > 0 && !valid ? 'Enter at least 10 characters.' : undefined}>
          <textarea className={inputClass} rows={4} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Explain why this approval must be completed by the same administrator." />
        </Field>
        <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={onClose}>Cancel</Button><Button loading={pending} loadingLabel={`Approving ${recordType}`} disabled={!valid}>Approve with recorded override</Button></div>
      </form>
    </FormModal>
  );
}
