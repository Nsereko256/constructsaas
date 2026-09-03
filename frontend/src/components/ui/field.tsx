import type React from 'react';
import { cn } from '@/lib/utils';

type FieldProps = {
  label: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
  className?: string;
};

export function Field({ label, required, error, children, className }: FieldProps) {
  return (
    <label className={cn('field-group grid min-w-0 gap-1.5 text-[13px] sm:text-sm', className)}>
      <span className="field-label flex items-center gap-1 font-bold tracking-[-0.01em] text-foreground">
        {label}
        {required ? <span className="field-required" aria-label="required">Required</span> : null}
      </span>
      {children}
      {error ? <span className="field-error text-xs font-semibold text-critical">{error}</span> : null}
    </label>
  );
}

export const inputClass =
  'field-control min-h-11 w-full rounded-md border border-border bg-white px-3 py-2 text-sm leading-5 text-foreground placeholder:text-muted/65 transition-[border-color,box-shadow,background-color] duration-150 hover:border-muted/70 focus:border-info focus:outline-none focus:ring-4 focus:ring-info/10 disabled:cursor-not-allowed disabled:bg-surface disabled:text-muted';
