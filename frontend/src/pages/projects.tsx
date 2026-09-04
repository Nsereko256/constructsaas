import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Building2, Plus, Trash2, Users } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { api } from '@/api/services';
import { Project, User } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { EngineerPicker } from '@/components/common/engineer-picker';
import { useListState } from '@/hooks/use-list-state';
import { formatUGX } from '@/lib/utils';
import { WorkspaceTabs } from '@/components/common/workspace-hub';

const columns: ColumnDef<Project>[] = [
  {
    header: 'Project',
    cell: ({ row }) => (
      <div>
        <Link className="font-bold text-primary" to={`/projects/${row.original.id}/progress`}>
          {row.original.name}
        </Link>
        <p className="text-xs text-muted">{row.original.code}</p>
        <div className="flex gap-3"><Link className="text-xs font-semibold text-primary" to={`/projects/${row.original.id}/progress`}>Progress & goals</Link><Link className="text-xs font-semibold text-muted underline" to={`/projects/${row.original.id}`}>Details</Link></div>
      </div>
    ),
  },
  { header: 'Client', cell: ({ row }) => <span>{row.original.client || '-'}</span> },
  { header: 'Status', cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status_display}</Badge> },
  { header: 'Budget', cell: ({ row }) => <span>{formatUGX(row.original.budget)}</span> },
  { header: 'Manager', cell: ({ row }) => <span>{row.original.manager_name || '-'}</span> },
  { header: 'Progress', cell: ({ row }) => <Link className="font-semibold text-primary" to={`/projects/${row.original.id}/progress`}>{row.original.progress_percent}% · {row.original.progress_basis === 'goals' ? 'Goals' : 'Sites'}</Link> },
  { header: 'Engineers', cell: ({ row }) => <span>{row.original.site_engineer_names.join(', ') || '-'}</span> },
];

export function ProjectsPage() {
  const { role } = useAuth();
  const list = useListState({ status: '', is_active: 'true' });
  const [open, setOpen] = useState(false);
  const projects = useQuery({ queryKey: qk.projects(list.query), queryFn: () => api.projects(list.query) });

  return (
    <div className="grid gap-4">
      <WorkspaceTabs links={[{ href: '/projects', label: 'Projects', description: 'Portfolio and budgets', icon: Building2 }, { href: '/projects/sites', label: 'Sites', description: 'Project locations', icon: Building2 }, { href: '/team/project-staffing', label: 'Project staffing', description: 'People and assignments', icon: Users }]} />
      <PageToolbar title="Projects" subtitle="Searchable project portfolio with assignment and budget signals." search={list.search} onSearch={list.setSearch}>
        <Button variant="secondary" asChild><Link to="/projects/sites">Manage sites</Link></Button>
        <select className={inputClass} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}>
          <option value="">All statuses</option>
          <option value="planning">Planning</option>
          <option value="active">Active</option>
          <option value="on_hold">On hold</option>
          <option value="completed">Completed</option>
        </select>
        {can.approvePr(role) ? <Button onClick={() => setOpen(true)}>Create project</Button> : null}
      </PageToolbar>
      <DataTable columns={columns} data={projects.data?.results || []} emptyTitle={projects.isLoading ? 'Loading projects...' : 'No projects found'} />
      <Pagination page={list.page} setPage={list.setPage} data={projects.data} />
      <ProjectModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function ProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { role } = useAuth();
  const managers = useQuery({ queryKey: qk.users({ role: 'project_manager', is_active: true }), queryFn: () => api.users({ role: 'project_manager', is_active: true }) });
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ name: '', code: '', client: '', location: '', description: '', budget: '0', status: 'planning', manager: '', site_engineers: [] as string[], start_date: '', end_date: '' });
  const [selectedEngineers, setSelectedEngineers] = useState<Pick<User, 'id' | 'username'>[]>([]);
  const [sites, setSites] = useState([{ code: '', name: '', location: '' }]);
  const set = (key: Exclude<keyof typeof form, 'site_engineers'>, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const setEngineers = (engineers: Pick<User, 'id' | 'username'>[]) => { setSelectedEngineers(engineers); setForm((current) => ({ ...current, site_engineers: engineers.map((engineer) => String(engineer.id)) })); };
  const mutation = useMutation({
    mutationFn: async () => {
      const project = await api.saveProject({ ...form, manager: form.manager || null, site_engineers: form.site_engineers.map(Number), start_date: form.start_date || null, end_date: form.end_date || null } as Partial<Project>);
      await Promise.all(sites.filter((site) => site.code.trim() || site.name.trim()).map((site) => api.saveProjectSite({ ...site, project: project.id, status: 'ACTIVE', is_active: true })));
      return project;
    },
    onSuccess: () => {
      toast.push({ title: 'Project saved', tone: 'success' });
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    },
    onError: (error: Error) => toast.push({ title: 'Could not save project', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title="Create project and assignments" onClose={onClose}>
      <form className="grid gap-3 md:grid-cols-2" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
        <Field label="Project name" required><input className={inputClass} value={form.name} onChange={(event) => set('name', event.target.value)} /></Field>
        <Field label="Code" required><input className={inputClass} value={form.code} onChange={(event) => set('code', event.target.value)} /></Field>
        <Field label="Client"><input className={inputClass} value={form.client} onChange={(event) => set('client', event.target.value)} /></Field>
        <Field label="Location"><input className={inputClass} value={form.location} onChange={(event) => set('location', event.target.value)} /></Field>
        <Field label="Budget"><input className={inputClass} type="number" min="0" value={form.budget} onChange={(event) => set('budget', event.target.value)} /></Field>
        <Field label="Status">
          <select className={inputClass} value={form.status} onChange={(event) => set('status', event.target.value)}>
            <option value="planning">Planning</option>
            <option value="active">Active</option>
            <option value="on_hold">On hold</option>
            <option value="completed">Completed</option>
          </select>
        </Field>
        {can.approvePr(role) ? <div className="grid gap-3 rounded-xl border border-border bg-background p-3 md:col-span-2">
          <div><strong className="text-sm">Project personnel</strong><p className="text-xs text-muted">Choose one accountable manager and the site engineers who can work on this project.</p></div>
          {role === 'admin' ? <Field label="Project manager"><select className={inputClass} value={form.manager} onChange={(event) => set('manager', event.target.value)}><option value="">Unassigned</option>{(managers.data?.results || []).map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}</select></Field> : null}
          <EngineerPicker selected={selectedEngineers} onChange={setEngineers} />
        </div> : null}
        <div className="grid gap-3 rounded-xl border border-border bg-background p-3 md:col-span-2"><div className="flex items-center justify-between gap-2"><div><strong className="text-sm">Project sites</strong><p className="text-xs text-muted">Add every physical location that belongs to this project.</p></div><Button type="button" size="sm" variant="secondary" onClick={() => setSites((current) => [...current, { code: '', name: '', location: '' }])}><Plus className="h-4 w-4" />Add site</Button></div>{sites.map((site, index) => <div key={index} className="grid gap-2 rounded-lg border border-border bg-white p-3 md:grid-cols-[0.7fr_1fr_1fr_auto]"><input className={inputClass} required={index === 0} placeholder="Site code" value={site.code} onChange={(event) => setSites((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, code: event.target.value.toUpperCase() } : item))} /><input className={inputClass} required={index === 0} placeholder="Site name" value={site.name} onChange={(event) => setSites((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))} /><input className={inputClass} placeholder="Location / address" value={site.location} onChange={(event) => setSites((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, location: event.target.value } : item))} />{sites.length > 1 ? <Button type="button" size="sm" variant="ghost" aria-label={`Remove site ${index + 1}`} onClick={() => setSites((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 className="h-4 w-4" /></Button> : <span />}</div>)}</div>
        <Field label="Start date"><input className={inputClass} type="date" value={form.start_date} onChange={(event) => set('start_date', event.target.value)} /></Field>
        <Field label="End date"><input className={inputClass} type="date" value={form.end_date} onChange={(event) => set('end_date', event.target.value)} /></Field>
        <Field label="Description" className="md:col-span-2"><textarea className={inputClass} value={form.description} onChange={(event) => set('description', event.target.value)} /></Field>
        <Button className="md:col-span-2" disabled={!form.name || !form.code || mutation.isPending}>Save project</Button>
      </form>
    </FormModal>
  );
}
