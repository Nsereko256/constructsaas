import type React from 'react';
import { Dialog, DialogContent } from '@/components/ui/dialog';

export function FormModal({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent title={title} className="max-w-3xl">
        {children}
      </DialogContent>
    </Dialog>
  );
}
