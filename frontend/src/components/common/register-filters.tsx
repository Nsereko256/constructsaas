import { Children, useId, useState, type ReactNode } from 'react';
import { SlidersHorizontal, X } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Keep search visible; disclose the remaining controls together on phones. */
export function RegisterFilters({ children, className, activeCount = 0, onClear }: {
  children: ReactNode;
  className?: string;
  activeCount?: number;
  onClear?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const controlsId = useId();
  const [search, ...filters] = Children.toArray(children);
  return <div className={cn(className, 'register-filters')}>
    {search}
    <button type="button" className="register-filter-toggle" aria-controls={controlsId} aria-expanded={open} onClick={() => setOpen(!open)}>
      <SlidersHorizontal size={16} aria-hidden="true" />Filters{activeCount > 0 ? <span>{activeCount}</span> : null}
    </button>
    <div id={controlsId} className={cn('register-filter-controls', open && 'is-open')}>{filters}</div>
    {activeCount > 0 ? <div className="register-filter-state" role="status">
      <span>{activeCount} active filter{activeCount === 1 ? '' : 's'}</span>
      {onClear ? <button type="button" onClick={onClear}><X size={14} aria-hidden="true" />Clear filters</button> : null}
    </div> : null}
  </div>;
}
