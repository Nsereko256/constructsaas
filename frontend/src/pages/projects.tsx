import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AlertTriangle, Building2, CalendarDays, CircleDollarSign, Grid2X2, List, MoreVertical, Plus, Search, Target, Trash2, Upload } from 'lucide-react';
import { FormEvent, useState, type CSSProperties } from 'react';
import { api } from '@/api/services';
import { financeApi } from '@/api/finance-services';
import { Project, ProjectGoal, User } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { Badge, statusTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { EngineerPicker } from '@/components/common/engineer-picker';
import { SearchableSelect } from '@/components/ui/searchable-select';
import { useListState } from '@/hooks/use-list-state';
import { formatUGX } from '@/lib/utils';
import './projects-reference.css';

function downloadProjects(rows: Project[]) {
  const fields = ['Project', 'Code', 'Client', 'Status', 'Progress', 'Budget', 'Manager'];
  const values = rows.map((project) => [project.name, project.code, project.client, project.status_display, `${project.progress_percent}%`, project.budget, project.manager_name]);
  const csv = [fields, ...values].map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'constructsaas-projects.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

function formatCompactUGX(value: number) {
  if (value >= 1_000_000_000) return `UGX ${(value / 1_000_000_000).toFixed(value >= 10_000_000_000 ? 1 : 2).replace(/\.0+$/, '')}B`;
  if (value >= 1_000_000) return `UGX ${(value / 1_000_000).toFixed(value >= 100_000_000 ? 0 : 1).replace(/\.0$/, '')}M`;
  return formatUGX(value);
}

function projectCondition(project: Project, today: Date) {
  if (project.end_date && new Date(project.end_date) < today && project.status !== 'completed') return 'delayed';
  if (project.status === 'on_hold' || Number(project.budget_available_balance || 0) < 0) return 'at-risk';
  return 'on-track';
}

export function ProjectsPage() {
  const { role } = useAuth();
  const list = useListState({ status: '', manager: '', is_active: 'true' });
  const [open, setOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list');
  const projectQuery = { ...list.query, page_size: 4 };
  const projects = useQuery({ queryKey: qk.projects(projectQuery), queryFn: () => api.projects(projectQuery) });
  const portfolio = useQuery({ queryKey: qk.projects({ is_active: 'true', page_size: 100 }), queryFn: () => api.projects({ is_active: 'true', page_size: 100 }) });
  const workflow = useQuery({ queryKey: qk.workflowBadges, queryFn: api.workflowBadges });
  const goals = useQuery({ queryKey: ['project-goals', 'portfolio'], queryFn: () => api.projectGoals({ page_size: 100 }) });
  const projectRows = projects.data?.results || [];
  const portfolioRows = portfolio.data?.results || projectRows;
  const activeCount = portfolioRows.filter((project) => project.is_active && project.status === 'active').length;
  const totalBudget = portfolioRows.reduce((total, project) => total + Number(project.budget || 0), 0);
  const averageProgress = portfolioRows.length ? Math.round(portfolioRows.reduce((total, project) => total + Number(project.progress_percent || 0), 0) / portfolioRows.length) : 0;
  const actionTotal = Object.values(workflow.data || {}).reduce((total, count) => total + Number(count || 0), 0);
  const statusCounts = { all: portfolioRows.length, active: portfolioRows.filter((project) => project.status === 'active').length, planning: portfolioRows.filter((project) => project.status === 'planning').length, completed: portfolioRows.filter((project) => project.status === 'completed').length };
  const today = new Date();
  const health = portfolioRows.reduce((summary, project) => {
    const condition = projectCondition(project, today);
    if (condition === 'delayed') summary.delayed += 1;
    else if (condition === 'at-risk') summary.atRisk += 1;
    else summary.onTrack += 1;
    return summary;
  }, { onTrack: 0, atRisk: 0, delayed: 0 });
  const managers = Array.from(new Map(portfolioRows.filter((project) => project.manager).map((project) => [project.manager, { id: project.manager, name: project.manager_name }])).values());
  const milestones = ((goals.data?.results || []) as ProjectGoal[]).filter((goal) => goal.due_date && goal.status !== 'COMPLETED').sort((a, b) => String(a.due_date).localeCompare(String(b.due_date))).slice(0, 3);

  return (
    <div className="projects-reference">
      <section className="projects-titlebar"><div><h1>Projects</h1><p>Manage project delivery, budgets, materials and teams.</p></div><div className="projects-title-actions"><Button variant="secondary" onClick={() => downloadProjects(projectRows)}><Upload className="h-4 w-4" />Export</Button><Button onClick={() => setOpen(true)} disabled={!can.approvePr(role)}><Plus className="h-4 w-4" />Create project</Button></div></section>
      <section className="projects-alert" aria-label="Project actions requiring attention"><AlertTriangle size={17} /><strong>{actionTotal} actions require your attention</strong><Link to="/procurement/requests?action_queue=my_requests">View priority queue <span>›</span></Link></section>
      <section className="projects-kpis">{[
        { label: 'Total projects', value: portfolioRows.length, note: 'Across all sites', icon: Building2, tone: 'blue' },
        { label: 'Active', value: activeCount, note: portfolioRows.length ? `${Math.round(activeCount / portfolioRows.length * 100)}% of total` : 'No active projects', icon: Target, tone: 'teal' },
        { label: 'At risk', value: health.atRisk + health.delayed, note: 'Requires attention', icon: AlertTriangle, tone: 'amber' },
        { label: 'Total budget', value: formatCompactUGX(totalBudget), note: 'Across all projects', icon: CircleDollarSign, tone: 'indigo' },
      ].map((item) => <div className="projects-kpi" key={item.label}><span className={`projects-kpi-icon ${item.tone}`}><item.icon size={23} /></span><div><p>{item.label}</p><strong>{item.value}</strong><small>{item.note}</small></div></div>)}</section>
      <section className="projects-content-grid">
        <div className="projects-portfolio projects-panel">
          <div className="projects-panel-heading"><h2>Project portfolio</h2></div>
          <div className="projects-portfolio-toolbar"><div className="projects-status-tabs">{[['', 'All', statusCounts.all], ['active', 'Active', statusCounts.active], ['planning', 'Planning', statusCounts.planning], ['completed', 'Completed', statusCounts.completed]].map(([value, label, count]) => <button type="button" key={String(value)} className={list.filters.status === value ? 'active' : ''} onClick={() => list.setFilter('status', String(value))}>{label} <b>{count}</b></button>)}</div><label className="projects-search"><Search size={14} /><input aria-label="Search projects" placeholder="Search projects" value={list.search} onChange={(event) => list.setSearch(event.target.value)} /></label><select aria-label="Filter projects by manager" className={inputClass} value={list.filters.manager} onChange={(event) => list.setFilter('manager', event.target.value)}><option value="">Manager</option>{managers.map((manager) => <option key={manager.id} value={manager.id || ''}>{manager.name}</option>)}</select><select aria-label="Filter projects by status" className={inputClass} value={list.filters.status} onChange={(event) => list.setFilter('status', event.target.value)}><option value="">Status</option><option value="planning">Planning</option><option value="active">Active</option><option value="on_hold">On hold</option><option value="completed">Completed</option></select><span className="projects-view-toggle"><button type="button" className={viewMode === 'list' ? 'active' : ''} aria-label="List view" onClick={() => setViewMode('list')}><List size={15} /></button><button type="button" className={viewMode === 'grid' ? 'active' : ''} aria-label="Grid view" onClick={() => setViewMode('grid')}><Grid2X2 size={14} /></button></span></div>
          <div className={`projects-table-wrap ${viewMode === 'grid' ? 'is-grid' : ''}`}><table className="projects-table"><thead><tr><th>Project</th><th>Client</th><th>Status</th><th>Progress</th><th>Budget used</th><th>Manager</th><th>Sites / goals</th><th aria-label="Actions" /></tr></thead><tbody>{projectRows.map((project) => { const budget = Number(project.budget_revised || project.budget || 0); const used = Number(project.budget_actual_expenditure || 0) + Number(project.budget_commitments || 0); const condition = projectCondition(project, today); const badgeTone = condition === 'delayed' ? 'danger' : condition === 'at-risk' ? 'warning' : project.status === 'active' ? 'success' : project.status === 'planning' ? 'info' : statusTone(project.status); const statusLabel = condition === 'delayed' ? 'Delayed' : condition === 'at-risk' ? 'At risk' : project.status_display; return <tr key={project.id}><td><span className="projects-project-cell"><span className="projects-row-icon"><Building2 size={15} /></span><span><Link className="projects-name" to={`/projects/${project.id}/progress`}>{project.name}</Link><small>{project.description || project.code}</small></span></span></td><td>{project.client || '-'}</td><td><Badge tone={badgeTone}>{statusLabel}</Badge></td><td><Link className={`projects-progress ${condition}`} to={`/projects/${project.id}/progress`}><b>{project.progress_percent}%</b><span><i style={{ width: `${project.progress_percent}%` }} /></span></Link></td><td><span className="projects-budget-text">{formatCompactUGX(used)} / {formatCompactUGX(budget)}</span></td><td>{project.manager_name || '-'}</td><td><Link to={`/projects/${project.id}`}>{project.site_total || 0} / {project.goal_total || 0}</Link></td><td><Link className="projects-action" aria-label={`Open actions for ${project.name}`} to={`/projects/${project.id}`}><MoreVertical size={16} /></Link></td></tr>; })}</tbody></table>{!projectRows.length && <p className="projects-empty">{projects.isLoading ? 'Loading projects…' : 'No projects found.'}</p>}</div>
          <div className="projects-table-footer"><span>Showing {projectRows.length ? ((list.page - 1) * 4 + 1) : 0} to {(list.page - 1) * 4 + projectRows.length} of {projects.data?.count || projectRows.length} projects</span><span className="projects-page-controls"><button type="button" aria-label="Previous page" disabled={!projects.data?.previous} onClick={() => list.setPage(Math.max(1, list.page - 1))}>‹</button><b>{list.page}</b><button type="button" aria-label="Next page" disabled={!projects.data?.next} onClick={() => list.setPage(list.page + 1)}>›</button></span></div>
        </div>
        <aside className="projects-side-column">
          <section className="projects-panel projects-health"><div className="projects-panel-heading"><h2>Portfolio health</h2><span>All projects</span></div><div className="projects-health-body"><div className="projects-donut" style={{ '--health-on-track': `${portfolioRows.length ? health.onTrack / portfolioRows.length * 100 : 0}%`, '--health-at-risk': `${portfolioRows.length ? health.atRisk / portfolioRows.length * 100 : 0}%` } as CSSProperties}><div><strong>{portfolioRows.length ? Math.round(health.onTrack / portfolioRows.length * 100) : 0}%</strong><small>On track</small></div></div><div className="projects-health-legend"><HealthRow label="On track" count={health.onTrack} total={portfolioRows.length} tone="teal" /><HealthRow label="At risk" count={health.atRisk} total={portfolioRows.length} tone="amber" /><HealthRow label="Delayed" count={health.delayed} total={portfolioRows.length} tone="rose" /><small className="projects-health-total">Total projects <b>{portfolioRows.length}</b></small></div></div></section>
          <section className="projects-panel projects-milestones"><div className="projects-panel-heading"><h2>Upcoming milestones</h2><Link to="/projects">View all</Link></div>{milestones.map((goal) => <Link className="projects-milestone" to={`/projects/${goal.project}/progress`} key={goal.id}><span className="projects-milestone-icon"><CalendarDays size={16} /></span><span><strong>{goal.title}</strong><small>{goal.project_name}{goal.site_name ? ` · ${goal.site_name}` : ''}</small></span><time>{new Date(`${goal.due_date}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</time></Link>)}{!milestones.length && <p className="projects-empty">No upcoming milestones with due dates.</p>}<Link className="projects-footer-link" to="/projects">View all milestones <span>›</span></Link></section>
        </aside>
      </section>
      <ProjectModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function HealthRow({ label, count, total, tone }: { label: string; count: number; total: number; tone: string }) {
  return <div className="projects-health-row"><span><i className={tone} />{label}</span><span className="projects-health-track"><i className={tone} style={{ width: `${total ? count / total * 100 : 0}%` }} /></span><b>{count}</b><small>{total ? Math.round(count / total * 100) : 0}%</small></div>;
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
