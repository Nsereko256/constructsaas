import type React from 'react';
import { Badge, type BadgeTone } from '@/components/ui/badge';

type ContextItem = { label: string; value: React.ReactNode; tone?: BadgeTone };

/** A compact, consistent operational header for controlled business records. */
export function RecordContext({ items }: { items: ContextItem[] }) {
  return <div className="grid grid-cols-2 gap-2 rounded-xl border border-border bg-background p-2.5 text-xs sm:grid-cols-3 sm:p-3">
    {items.map((item) => <div key={item.label} className="min-w-0"><span className="block text-[10px] font-bold uppercase tracking-wide text-muted">{item.label}</span><div className="mt-0.5 truncate font-semibold text-foreground" title={typeof item.value === 'string' ? item.value : undefined}>{item.tone ? <Badge tone={item.tone}>{item.value}</Badge> : item.value}</div></div>)}
  </div>;
}
