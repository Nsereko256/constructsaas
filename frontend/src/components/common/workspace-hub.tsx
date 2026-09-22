import { ArrowRight, ChevronDown, type LucideIcon } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export type WorkspaceLink = {
  label: string;
  description: string;
  href: string;
  icon: LucideIcon;
};

export type WorkspaceTab = {
  label: string;
  href: string;
  icon?: LucideIcon;
  description?: string;
};

export function WorkspaceTabs({ links }: { links: WorkspaceTab[] }) {
  const location = useLocation();
  const navigate = useNavigate();
  const primaryCount = links.length <= 5 ? links.length : 4;
  const primaryLinks = links.slice(0, primaryCount);
  const secondaryLinks = links.slice(primaryCount);
  const current = [...links].sort((a, b) => b.href.length - a.href.length).find(({ href }) => location.pathname === href || location.pathname.startsWith(`${href}/`));
  const secondaryActive = secondaryLinks.some(({ href }) => href === current?.href);
  return <>
    <label className="workspace-section-picker"><span>Workspace</span><select aria-label="Workspace section" value={current?.href || ''} onChange={(event) => navigate(event.target.value)}>{!current ? <option value="" disabled>Choose a section</option> : null}{links.map(({ href, label }) => <option key={href} value={href}>{label}</option>)}</select></label>
    <nav aria-label="Workspace sections" className="workspace-tabs-direct">
    {primaryLinks.map(({ href, label, icon: Icon }) => <NavLink key={href} end={href.split('/').length <= 2} to={href} className={({ isActive }) => isActive ? 'active' : ''}>{Icon ? <Icon className="h-3.5 w-3.5" /> : null}{label}</NavLink>)}
    {secondaryLinks.length ? <DropdownMenu.Root><DropdownMenu.Trigger className={secondaryActive ? 'workspace-more active' : 'workspace-more'}>{secondaryActive ? current?.label : 'More'} <ChevronDown className="h-3.5 w-3.5" /></DropdownMenu.Trigger><DropdownMenu.Portal><DropdownMenu.Content className="workspace-menu" align="end" sideOffset={6}>{secondaryLinks.map(({ href, label, icon: Icon }) => <DropdownMenu.Item key={href} asChild><NavLink to={href}>{Icon ? <Icon className="h-3.5 w-3.5" /> : null}{label}</NavLink></DropdownMenu.Item>)}</DropdownMenu.Content></DropdownMenu.Portal></DropdownMenu.Root> : null}
    </nav>
  </>;
}

export function WorkspaceHub({ eyebrow, title, description, links }: {
  eyebrow: string;
  title: string;
  description: string;
  links: WorkspaceLink[];
}) {
  return <div className="grid gap-4">
    <header>
      <p className="text-xs font-semibold uppercase tracking-widest text-muted">{eyebrow}</p>
      <h2 className="text-2xl font-semibold sm:text-3xl">{title}</h2>
      <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>
    </header>
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label={`${title} work areas`}>
      {links.map(({ label, description: detail, href, icon: Icon }) => <Link key={href} to={href} className="group block">
        <Card className="h-full transition-shadow hover:shadow-lift">
          <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2"><div className="grid h-9 w-9 place-items-center rounded-lg bg-primary/10 text-primary"><Icon className="h-5 w-5" /></div><ArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-1 group-hover:text-primary" /></CardHeader>
          <CardContent><CardTitle className="text-base">{label}</CardTitle><p className="mt-1 text-sm text-muted">{detail}</p></CardContent>
        </Card>
      </Link>)}
    </section>
  </div>;
}
