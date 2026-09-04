import { ArrowRight, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export type WorkspaceLink = {
  label: string;
  description: string;
  href: string;
  icon: LucideIcon;
};

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
