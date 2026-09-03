import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, UserPlus, X } from 'lucide-react';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import { User } from '@/api/types';
import { inputClass } from '@/components/ui/field';

type SelectedEngineer = Pick<User, 'id' | 'username'>;

export function EngineerPicker({ selected, onChange }: { selected: SelectedEngineer[]; onChange: (engineers: SelectedEngineer[]) => void }) {
  const [query, setQuery] = React.useState('');
  const engineers = useQuery({
    queryKey: qk.users({ role: 'site_engineer', is_active: true, search: query, page_size: 50 }),
    queryFn: () => api.users({ role: 'site_engineer', is_active: true, search: query, page_size: 50 }),
    enabled: query.trim().length >= 1,
  });
  const results = engineers.data?.results || [];
  const selectedIds = new Set(selected.map((engineer) => engineer.id));
  const add = (engineer: SelectedEngineer) => {
    if (!selectedIds.has(engineer.id)) onChange([...selected, engineer]);
  };
  const remove = (id: number) => onChange(selected.filter((engineer) => engineer.id !== id));
  const addVisible = () => onChange([...selected, ...results.filter((engineer) => !selectedIds.has(engineer.id))]);

  return <div className="grid gap-2">
    <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold text-muted">Site engineers</span><span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-bold text-primary">{selected.length} selected</span></div>
    <p className="text-xs text-muted">Search by name or username, then add individuals or everyone currently shown.</p>
    <div className="flex min-h-11 flex-wrap items-center gap-1.5 rounded-lg border border-border bg-white p-1.5">
      {selected.map((engineer) => <span key={engineer.id} className="inline-flex max-w-full items-center gap-1 rounded-full bg-primary/10 py-1 pl-2 pr-1 text-xs font-semibold text-primary"><span className="truncate">{engineer.username}</span><button className="grid h-5 w-5 shrink-0 place-items-center rounded-full hover:bg-primary/20" type="button" onClick={() => remove(engineer.id)} aria-label={`Remove ${engineer.username}`}><X className="h-3 w-3" /></button></span>)}
      {!selected.length ? <span className="px-1 text-xs text-muted">No engineers assigned yet.</span> : null}
    </div>
    <div className="relative"><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted" /><input className={`${inputClass} pl-9`} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search engineers" aria-label="Search site engineers" /></div>
    {query.trim() ? <div className="overflow-hidden rounded-lg border border-border bg-white shadow-panel">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-background px-3 py-2 text-xs"><span className="text-muted">{engineers.isLoading ? 'Searching…' : `${results.length} engineer${results.length === 1 ? '' : 's'} shown`}</span><button type="button" className="font-semibold text-primary disabled:text-muted" disabled={!results.some((engineer) => !selectedIds.has(engineer.id))} onClick={addVisible}>Select all shown</button></div>
      {!engineers.isLoading && !results.length ? <p className="px-3 py-3 text-sm text-muted">No active site engineers match “{query}”.</p> : null}
      {results.map((engineer) => { const chosen = selectedIds.has(engineer.id); return <button key={engineer.id} type="button" disabled={chosen} onClick={() => add(engineer)} className="flex w-full items-center gap-2 border-b border-border px-3 py-2.5 text-left text-sm last:border-0 hover:bg-background disabled:cursor-default disabled:bg-primary/5"><span className="min-w-0 flex-1 truncate font-medium">{engineer.full_name || `${engineer.first_name} ${engineer.last_name}`.trim() || engineer.username}<span className="ml-2 text-xs text-muted">{engineer.username}</span></span>{chosen ? <span className="text-xs font-semibold text-primary">Selected</span> : <span className="inline-flex items-center gap-1 text-xs font-semibold text-primary"><UserPlus className="h-3.5 w-3.5" />Add</span>}</button>; })}
    </div> : null}
  </div>;
}
