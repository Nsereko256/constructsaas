import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { inputClass } from './field';

export type SearchableOption = { value: string | number; label: string; disabled?: boolean };

/** Search-first picker for long, business-record option lists. */
export function SearchableSelect({ value, onChange, options, placeholder = 'Search and select', disabled = false, required = false, className }: {
  value: string | number; onChange: (value: string) => void; options: SearchableOption[]; placeholder?: string; disabled?: boolean; required?: boolean; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selected = options.find((option) => String(option.value) === String(value));
  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    return term ? options.filter((option) => option.label.toLowerCase().includes(term)) : options;
  }, [options, query]);
  useEffect(() => () => { if (closeTimer.current) clearTimeout(closeTimer.current); }, []);
  const choose = (option: SearchableOption) => { onChange(String(option.value)); setQuery(''); setOpen(false); };
  return <div className={cn('relative min-w-0', className)}>
    <div className={cn(inputClass, 'flex items-center gap-2 px-3', disabled && 'cursor-not-allowed opacity-60')}>
      <Search className="h-4 w-4 shrink-0 text-muted" />
      <input
        className="inline-search-input min-w-0 flex-1 bg-transparent outline-none"
        value={open ? query : (selected?.label || '')}
        placeholder={selected ? undefined : placeholder}
        disabled={disabled}
        required={required}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        onFocus={() => { if (closeTimer.current) clearTimeout(closeTimer.current); setQuery(''); setOpen(true); }}
        onBlur={() => { closeTimer.current = setTimeout(() => setOpen(false), 150); }}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
      />
      {selected && !disabled ? <button type="button" className="text-muted hover:text-foreground" aria-label="Clear selection" onMouseDown={(event) => event.preventDefault()} onClick={() => { onChange(''); setQuery(''); }}><X className="h-3.5 w-3.5" /></button> : null}
    </div>
    {open && !disabled ? <div className="absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-border bg-white p-1 shadow-lg" role="listbox">
      {matches.length ? matches.map((option) => <button key={String(option.value)} type="button" role="option" aria-selected={String(option.value) === String(value)} disabled={option.disabled} className={cn('block w-full rounded-md px-2.5 py-2 text-left text-sm hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-50', String(option.value) === String(value) && 'bg-primary/10 font-semibold text-primary')} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(option)}>{option.label}</button>) : <p className="px-2.5 py-2 text-sm text-muted">No matching options.</p>}
    </div> : null}
  </div>;
}
