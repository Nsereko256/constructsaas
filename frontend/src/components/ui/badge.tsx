import type React from 'react';
import { cn } from '@/lib/utils';

const tones: Record<string, string> = {
  success: 'border-success-border bg-success text-success-foreground',
  warning: 'border-warning/25 bg-warning/10 text-[#8A5A00]',
  danger: 'border-critical/20 bg-critical/10 text-critical',
  info: 'border-info/20 bg-info/10 text-info',
  neutral: 'border-border bg-surface text-muted',
};

export type BadgeTone = keyof typeof tones;

export function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: BadgeTone }) {
  return (
    <span className={cn('inline-flex items-center rounded-md border px-2 py-1 text-[11px] font-semibold leading-none tracking-[0.01em]', tones[tone])}>
      {children}
    </span>
  );
}

export function statusTone(status?: string) {
  if (!status) return 'neutral';
  if (['REJECTED', 'CANCELLED', 'BLOCKED', 'MATCH_EXCEPTION', 'OVERDUE', 'REVERSED', 'danger'].includes(status)) return 'danger';
  if (['PENDING', 'LOW', 'DRAFT', 'SUBMITTED', 'HOLD', 'ON_HOLD', 'STOCK_ISSUE_REQUESTED', 'PARTIALLY_PAID', 'warning'].includes(status)) return 'warning';
  if (['APPROVED', 'RECEIVED', 'STOCK_ISSUED', 'DISPATCH_CONFIRMED', 'IN', 'ADJUST_IN', 'MATCHED', 'VERIFIED', 'POSTED', 'PAID', 'COMPLETED', 'CLOSED', 'success'].includes(status)) {
    return 'success';
  }
  if (['IN_PROGRESS', 'ASSIGNED', 'PO_CREATED', 'FINANCE_REVIEW', 'info'].includes(status)) return 'info';
  return 'neutral';
}
