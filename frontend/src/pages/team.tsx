import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Save } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { api } from '@/api/services';
import type { Project, Role, User } from '@/api/types';
import { qk } from '@/api/queryKeys';
import { ROLE_LABELS, can } from '@/api/roles';
import { useAuth } from '@/auth/auth-context';
import { FormModal } from '@/components/common/form-modal';
import { PageToolbar } from '@/components/common/page-toolbar';
import { Pagination } from '@/components/common/pagination';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Field, inputClass } from '@/components/ui/field';
import { useToast } from '@/components/ui/toast';
import { useListState } from '@/hooks/use-list-state';

const roles = Object.keys(ROLE_LABELS) as Role[];

export function TeamPage() {
  const { role } = useAuth();
  const list = useListState({ role: '', is_active: 'true' });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const users = useQuery({ queryKey: qk.users(list.query), queryFn: () => api.users(list.query) });
  const columns: ColumnDef<User>[] = [
    { header: 'User', cell: ({ row }) => <strong>{row.original.username}</strong> },
    { header: 'Name', cell: ({ row }) => `${row.original.first_name || ''} ${row.original.last_name || ''}`.trim() || '-' },
    { header: 'Role', cell: ({ row }) => <Badge tone="info">{row.original.role_display}</Badge> },
    { header: 'Phone', cell: ({ row }) => row.original.phone || '-' },
    { header: 'Email', cell: ({ row }) => row.original.email || '-' },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <Button variant="secondary" size="sm" onClick={() => setEditing(row.original)}>
          Edit access
        </Button>
      ),
    },
  ];

  if (role === 'project_manager') return <EngineerAccess />;
  if (!can.manageTeam(role)) return <div className="border border-border bg-white p-5">Your role cannot manage team access.</div>;

  return (
    <div className="grid gap-4">
      <PageToolbar title="Team access" subtitle="Admins grant access to every role in the company." search={list.search} onSearch={list.setSearch}>
        <select className={inputClass} value={list.filters.role} onChange={(event) => list.setFilter('role', event.target.value)}>
          <option value="">All roles</option>
          {roles.map((item) => <option key={item} value={item}>{ROLE_LABELS[item]}</option>)}
        </select>
        <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />User</Button>
      </PageToolbar>
      <DataTable columns={columns} data={users.data?.results || []} emptyTitle={users.isLoading ? 'Loading users...' : 'No users found'} />
      <Pagination page={list.page} setPage={list.setPage} data={users.data} />
      <UserModal open={open || Boolean(editing)} user={editing} onClose={() => { setOpen(false); setEditing(null); }} />
    </div>
  );
}

function UserModal({ open, user, onClose }: { open: boolean; user: User | null; onClose: () => void }) {
  const [form, setForm] = useState({ username: '', first_name: '', last_name: '', email: '', phone: '', role: 'site_engineer' as Role, is_active: 'true', password: '' });
  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const queryClient = useQueryClient();
  const toast = useToast();

  useEffect(() => {
    setForm(user ? {
      username: user.username,
      first_name: user.first_name,
      last_name: user.last_name,
      email: user.email,
      phone: user.phone,
      role: user.role,
      is_active: String(user.is_active),
      password: '',
    } : {
      username: '',
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      role: 'site_engineer',
      is_active: 'true',
      password: '',
    });
  }, [user]);

  const mutation = useMutation({
    mutationFn: () => user
      ? api.updateUser(user.id, {
        ...form,
        is_active: form.is_active === 'true',
        password: form.password || undefined,
      })
      : api.createUser({ ...form, is_active: form.is_active === 'true' }),
    onSuccess: () => {
      toast.push({ title: user ? 'User access updated' : 'User created', tone: 'success' });
      onClose();
      void queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (error: Error) => toast.push({ title: 'Could not create user', message: error.message, tone: 'danger' }),
  });

  return (
    <FormModal open={open} title={user ? `Edit ${user.username}` : 'Create user access'} onClose={onClose}>
      <form className="grid gap-3 md:grid-cols-2" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}>
        <Field label="Username" required><input className={inputClass} value={form.username} onChange={(event) => set('username', event.target.value)} /></Field>
        <Field label="Role" required>
          <select className={inputClass} value={form.role} onChange={(event) => set('role', event.target.value)}>
            {roles.map((item) => <option key={item} value={item}>{ROLE_LABELS[item]}</option>)}
          </select>
        </Field>
        <Field label="Access">
          <select className={inputClass} value={form.is_active} onChange={(event) => set('is_active', event.target.value)}>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </Field>
        <Field label="First name"><input className={inputClass} value={form.first_name} onChange={(event) => set('first_name', event.target.value)} /></Field>
        <Field label="Last name"><input className={inputClass} value={form.last_name} onChange={(event) => set('last_name', event.target.value)} /></Field>
        <Field label="Email"><input className={inputClass} type="email" value={form.email} onChange={(event) => set('email', event.target.value)} /></Field>
        <Field label="Phone"><input className={inputClass} value={form.phone} onChange={(event) => set('phone', event.target.value)} /></Field>
        <Field label={user ? 'New password (optional)' : 'Temporary password'} required={!user} className="md:col-span-2"><input className={inputClass} type="password" value={form.password} onChange={(event) => set('password', event.target.value)} /></Field>
        <Button className="md:col-span-2" disabled={!form.username || (!user && !form.password) || mutation.isPending}>
          {user ? 'Save access' : 'Create user'}
        </Button>
      </form>
    </FormModal>
  );
}

function EngineerAccess() {
  const projects = useQuery({
    queryKey: qk.projects({ engineer_access: true }),
    queryFn: () => api.projects({ is_active: true, page_size: 100 }),
  });
  const engineers = useQuery({
    queryKey: qk.users({ role: 'site_engineer', engineer_access: true }),
    queryFn: () => api.users({ role: 'site_engineer', is_active: true, page_size: 100 }),
  });

  return (
    <div className="grid gap-4">
      <PageToolbar
        title="Engineer access"
        subtitle="Assign one or several site engineers to each project you manage."
      />
      <div className="grid gap-3">
        {(projects.data?.results || []).map((project) => (
          <EngineerProjectAccess
            key={project.id}
            project={project}
            engineers={engineers.data?.results || []}
          />
        ))}
        {!projects.isLoading && !projects.data?.results.length ? (
          <div className="border border-border bg-white p-5 text-sm text-muted">
            No projects are assigned to you yet.
          </div>
        ) : null}
      </div>
    </div>
  );
}

function EngineerProjectAccess({ project, engineers }: { project: Project; engineers: User[] }) {
  const [selected, setSelected] = useState(() => new Set(project.site_engineers.map(String)));
  const queryClient = useQueryClient();
  const toast = useToast();
  const mutation = useMutation({
    mutationFn: () => api.saveProject(
      { site_engineers: [...selected].map(Number) } as Partial<Project>,
      project.id,
    ),
    onSuccess: () => {
      toast.push({ title: `Access saved for ${project.name}`, tone: 'success' });
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (error: Error) => toast.push({
      title: 'Could not save engineer access',
      message: error.message,
      tone: 'danger',
    }),
  });

  const toggle = (engineerId: number) => {
    setSelected((current) => {
      const next = new Set(current);
      const key = String(engineerId);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="border border-border bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-3">
        <div>
          <strong>{project.name}</strong>
          <p className="text-xs text-muted">{project.code} · {project.location || 'No location'}</p>
        </div>
        <Button size="sm" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
          <Save className="h-4 w-4" />
          Save access
        </Button>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {engineers.map((engineer) => (
          <label key={engineer.id} className="flex cursor-pointer items-center gap-3 border border-border bg-background px-3 py-2 text-sm">
            <input
              type="checkbox"
              checked={selected.has(String(engineer.id))}
              onChange={() => toggle(engineer.id)}
            />
            <span>
              <strong className="block">{engineer.first_name || engineer.username} {engineer.last_name}</strong>
              <small className="text-muted">{engineer.phone || engineer.username}</small>
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
