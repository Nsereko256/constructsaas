import * as DialogPrimitive from '@radix-ui/react-dialog';
import { ClipboardPenLine, X } from 'lucide-react';
import type React from 'react';
import { cn } from '@/lib/utils';
import { Button } from './button';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;

export function DialogContent({
  title,
  description,
  children,
  className,
  variant = 'default',
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  variant?: 'default' | 'form';
}) {
  const isForm = variant === 'form';
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="dialog-overlay fixed inset-0 z-40 bg-sidebar/45" />
      <DialogPrimitive.Content
        className={cn(
          'dialog-surface fixed inset-x-0 bottom-0 z-50 grid max-h-[94vh] w-full grid-rows-[auto_1fr] overflow-hidden rounded-t-2xl border border-b-0 border-border/80 bg-white shadow-2xl sm:left-1/2 sm:right-auto sm:top-1/2 sm:bottom-auto sm:h-auto sm:max-h-[calc(100vh-3rem)] sm:w-[calc(100%-3rem)] sm:max-w-2xl sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-lg sm:border-b sm:shadow-xl',
          isForm && 'reference-form-dialog',
          className,
        )}
      >
        <div className="dialog-header sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-border/80 bg-white px-4 py-3.5 sm:px-6 sm:py-4">
          <div className="flex min-w-0 items-start gap-3">
            {isForm ? <span className="dialog-title-mark" aria-hidden="true"><ClipboardPenLine className="h-4 w-4" /></span> : null}
            <div className="min-w-0">
              <div className="mb-1 h-1 w-10 rounded-full bg-primary/25 sm:hidden" aria-hidden="true" />
              {isForm ? <p className="dialog-eyebrow">Workflow form</p> : null}
              <DialogPrimitive.Title className="dialog-title text-base font-black tracking-tight sm:text-lg">{title}</DialogPrimitive.Title>
              {description ? <DialogPrimitive.Description className="dialog-description mt-1 text-sm text-muted">{description}</DialogPrimitive.Description> : null}
            </div>
          </div>
          <DialogPrimitive.Close asChild>
            <Button variant="ghost" size="sm" className="dialog-close shrink-0 rounded-full" aria-label="Close dialog">
              <X className="h-4 w-4" />
            </Button>
          </DialogPrimitive.Close>
        </div>
        <div className="form-modal-body min-h-0 overflow-auto px-4 py-4 sm:px-6 sm:py-5">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
