import { Search, X } from 'lucide-react';
import type React from 'react';
import { inputClass } from '@/components/ui/field';
import { cn } from '@/lib/utils';

export function PageToolbar({
  title,
  subtitle,
  action,
  search,
  onSearch,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  search?: string;
  onSearch?: (value: string) => void;
  children?: React.ReactNode;
}) {
  return (
    <header className="workspace-toolbar">
      <div className="workspace-toolbar-heading">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {subtitle ? <p className="mt-1 max-w-2xl text-sm text-muted">{subtitle}</p> : null}
      </div>
      <div className="workspace-toolbar-controls">
        {onSearch ? (
          <div className={cn(inputClass, 'flex w-full items-center gap-2 px-3 sm:min-w-[190px] lg:min-w-[220px]')}>
            <Search className="h-4 w-4 text-muted" />
            <input
              className="inline-search-input w-full bg-transparent outline-none"
              value={search || ''}
              onChange={(event) => onSearch(event.target.value)}
              placeholder="Search"
              aria-label={`Search ${title}`}
            />
            {search ? <button type="button" className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-muted hover:bg-muted hover:text-foreground" onClick={() => onSearch('')} aria-label={`Clear ${title} search`}><X className="h-3.5 w-3.5" /></button> : null}
          </div>
        ) : null}
        {children}
        {action}
      </div>
    </header>
  );
}
