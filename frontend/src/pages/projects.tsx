import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Building2, CheckCircle2, CircleDollarSign, Plus, Target, Trash2, Users } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { api } from '@/api/services';
import { financeApi } from '@/api/finance-services';
import { Project, User } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { EngineerPicker } from '@/components/common/engineer-picker';
import { SearchableSelect } from '@/components/ui/searchable-select';
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
  const projectRows = projects.data?.results || [];
  const activeCount = projectRows.filter((project) => project.is_active && project.status !== 'completed').length;
  const totalBudget = projectRows.reduce((total, project) => total + Number(project.budget || 0), 0);
  const averageProgress = projectRows.length ? Math.round(projectRows.reduce((total, project) => total + Number(project.progress_percent || 0), 0) / projectRows.length) : 0;

  return (
    <div className="grid gap-4">
      <WorkspaceTabs links={[{ href: '/projects', label: 'Projects', description: 'Portfolio and budgets', icon: Building2 }, { href: '/projects/sites', label: 'Sites', description: 'Project locations', icon: Building2 }, { href: '/team/project-staffing', label: 'Project staffing', description: 'People and assignments', icon: Users }]} />
      <section className="rounded-2xl border border-border bg-white px-4 py-4 shadow-panel sm:px-6 sm:py-5"><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">ConstructSaaS · Operations</p><div className="mt-1 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-2xl font-black tracking-tight sm:text-3xl">Projects overview</h2><p className="mt-1 max-w-2xl text-sm text-muted">Track delivery progress, budget position, sites, and accountable project teams.</p></div><Button onClick={() => setOpen(true)} disabled={!can.approvePr(role)}><Plus className="h-4 w-4" />New project</Button></div></section>
      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        {[{ label: 'Active projects', value: activeCount, icon: Building2, tone: 'bg-info/10 text-info' }, { label: 'Total projects', value: projectRows.length, icon: CheckCircle2, tone: 'bg-success/10 text-success' }, { label: 'Portfolio budget', value: formatUGX(totalBudget), icon: CircleDollarSign, tone: 'bg-warning/10 text-warning' }, { label: 'Average progress', value: `${averageProgress}%`, icon: Target, tone: 'bg-primary/10 text-primary' }].map((item) => <Card key={item.label}><CardContent className="flex items-center gap-2.5 p-3 sm:p-4"><span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${item.tone}`}><item.icon className="h-4 w-4" /></span><div className="min-w-0"><p className="truncate text-[10px] font-bold uppercase tracking-wide text-muted">{item.label}</p><strong className="block truncate text-lg font-black sm:text-xl">{item.value}</strong></div></CardContent></Card>)}
      </section>
      <PageToolbar title="Project register" subtitle="Searchable project portfolio with assignment and budget signals." search={list.search} onSearch={list.setSearch}>
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
      <DataTable columns={columns} data={projectRows} emptyTitle={projects.isLoading ? 'Loading projects...' : 'No projects found'} mobileSummaryStacked />
      <Pagination page={list.page} setPage={list.setPage} data={projects.data} />
      <ProjectModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function ProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { role } = useAuth();
  const managers = useQuery({ queryKey: qk.users({ role: 'project_manager', is_active: true }), queryFn: () => api.users({ role: 'project_manager', is_active: true }) });
  const budgetCategories = useQuery({ queryKey: ['finance', 'budget-categories', 'project-setup'], queryFn: () => financeApi.budgetCategories({ page_size: 100, is_active: true }), enabled: can.prepareFinance(role) });
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ name: '', code: '', client: '', location: '', description: '', budget: '0', status: 'planning', manager: '', site_engineers: [] as string[], start_date: '', end_date: '' });
  const [selectedEngineers, setSelectedEngineers] = useState<Pick<User, 'id' | 'username'>[]>([]);
  const [sites, setSites] = useState([{ code: '', name: '', location: '' }]);
  const [goals, setGoals] = useState([{ title: '', description: '', weight: '1', due_date: '' }]);
  const [createFinanceBudget, setCreateFinanceBudget] = useState(false);
  const [budgetName, setBudgetName] = useState('Initial project budget');
  const [budgetLines, setBudgetLines] = useState([{ category: '', description: '', original_amount: '' }]);
  const set = (key: Exclude<keyof typeof form, 'site_engineers'>, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const setEngineers = (engineers: Pick<User, 'id' | 'username'>[]) => { setSelectedEngineers(engineers); setForm((current) => ({ ...current, site_engineers: engineers.map((engineer) => String(engineer.id)) })); };
  const mutation = useMutation({
    mutationFn: async () => {
      const project = await api.saveProject({ ...form, manager: form.manager || null, site_engineers: form.site_engineers.map(Number), start_date: form.start_date || null, end_date: form.end_date || null } as Partial<Project>);
      await Promise.all(sites.filter((site) => site.code.trim() || site.name.trim()).map((site) => api.saveProjectSite({ ...site, project: project.id, status: 'ACTIVE', is_active: true })));
      await Promise.all(goals.filter((goal) => goal.title.trim()).map((goal) => api.saveProjectGoal({ ...goal, project: project.id, weight: goal.weight || '1', due_date: goal.due_date || null })));
      if (createFinanceBudget) await financeApi.createBudget({ project: project.id, name: budgetName, lines: budgetLines.map((line) => ({ ...line, category: Number(line.category) })) });
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
        <div className="grid gap-3 rounded-xl border border-border bg-background p-3 md:col-span-2"><div className="flex items-center justify-between gap-2"><div><strong className="text-sm">Progress goals</strong><p className="text-xs text-muted">Add weighted milestones so the dashboard can show actual progress immediately.</p></div><Button type="button" size="sm" variant="secondary" onClick={() => setGoals((current) => [...current, { title: '', description: '', weight: '1', due_date: '' }])}><Plus className="h-4 w-4" />Add goal</Button></div>{goals.map((goal, index) => <div key={index} className="grid gap-2 rounded-lg border border-border bg-white p-3 md:grid-cols-[1fr_110px_150px_auto]"><input className={inputClass} placeholder="Goal or milestone" value={goal.title} onChange={(event) => setGoals((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item))} /><input className={inputClass} type="number" min="0.01" step="0.01" placeholder="Weight" value={goal.weight} onChange={(event) => setGoals((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, weight: event.target.value } : item))} /><input className={inputClass} type="date" value={goal.due_date} onChange={(event) => setGoals((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, due_date: event.target.value } : item))} />{goals.length > 1 ? <Button type="button" size="sm" variant="ghost" aria-label={`Remove goal ${index + 1}`} onClick={() => setGoals((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 className="h-4 w-4" /></Button> : <span />}</div>)}</div>
        {can.prepareFinance(role) ? <div className="grid gap-3 rounded-xl border border-primary/20 bg-primary/[0.035] p-3 md:col-span-2"><label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5" checked={createFinanceBudget} onChange={(event) => setCreateFinanceBudget(event.target.checked)} /><span><strong>Create Finance budget draft</strong><span className="block text-xs text-muted">Set up budget lines now so Finance can review and approve the project budget.</span></span></label>{createFinanceBudget ? <><Field label="Budget name" required><input className={inputClass} value={budgetName} onChange={(event) => setBudgetName(event.target.value)} /></Field><div className="grid gap-2">{budgetLines.map((line, index) => <div key={index} className="grid gap-2 md:grid-cols-[1fr_1fr_150px_auto]"><SearchableSelect required value={line.category} onChange={(category) => setBudgetLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, category } : item))} options={(budgetCategories.data?.results || []).map((category) => ({ value: category.id, label: `${category.code} / ${category.name}` }))} placeholder="Budget category" /><input className={inputClass} placeholder="Description" value={line.description} onChange={(event) => setBudgetLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, description: event.target.value } : item))} /><input className={inputClass} type="number" min="0.01" step="0.01" required placeholder="Amount" value={line.original_amount} onChange={(event) => setBudgetLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, original_amount: event.target.value } : item))} />{budgetLines.length > 1 ? <Button type="button" size="sm" variant="ghost" aria-label={`Remove budget line ${index + 1}`} onClick={() => setBudgetLines((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 className="h-4 w-4" /></Button> : <span />}</div>)}<Button type="button" size="sm" variant="secondary" onClick={() => setBudgetLines((current) => [...current, { category: '', description: '', original_amount: '' }])}><Plus className="h-4 w-4" />Add budget line</Button></div></> : null}</div> : null}
        <Field label="Start date"><input className={inputClass} type="date" value={form.start_date} onChange={(event) => set('start_date', event.target.value)} /></Field>
        <Field label="End date"><input className={inputClass} type="date" value={form.end_date} onChange={(event) => set('end_date', event.target.value)} /></Field>
        <Field label="Description" className="md:col-span-2"><textarea className={inputClass} value={form.description} onChange={(event) => set('description', event.target.value)} /></Field>
        <Button className="md:col-span-2" loading={mutation.isPending} loadingLabel="Setting up project" disabled={!form.name || !form.code || mutation.isPending || (createFinanceBudget && (!budgetName || !budgetLines.length || budgetLines.some((line) => !line.category || !line.original_amount)))}>Create project setup</Button>
      </form>
    </FormModal>
  );
}
