import { ArrowRight, Bell, BriefcaseBusiness, MessageSquare, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

type DeferredWorkspacePageProps = {
  kind: 'work-orders' | 'messages';
};

export function DeferredWorkspacePage({ kind }: DeferredWorkspacePageProps) {
  const workOrders = kind === 'work-orders';
  const title = workOrders ? 'Work orders are coming in a later release' : 'Messages are coming in a later release';
  const description = workOrders
    ? 'The work-order workspace is intentionally not part of this release. Your projects, procurement, inventory and finance workflows remain available here.'
    : 'The messages workspace is intentionally not part of this release. Use Notifications for operational alerts, approvals and follow-up actions.';
  return <div className="mx-auto grid max-w-2xl place-items-center py-16"><section className="w-full rounded-xl border border-border bg-white p-6 text-center shadow-panel sm:p-8" role="status"><div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-[#E8F5F4] text-primary">{workOrders ? <BriefcaseBusiness className="h-7 w-7" /> : <MessageSquare className="h-7 w-7" />}</div><p className="mt-4 text-[10px] font-black uppercase tracking-[0.16em] text-muted">Workspace deferred</p><h1 className="mt-2 text-xl font-black tracking-tight text-foreground">{title}</h1><p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">{description}</p><div className="mt-5 flex flex-wrap justify-center gap-2"><Link className="inline-flex min-h-9 items-center gap-2 rounded-md border border-primary bg-primary px-3 py-2 text-sm font-semibold text-white hover:bg-[#0B5F63]" to={workOrders ? '/projects' : '/notifications'}>{workOrders ? <ShieldCheck className="h-4 w-4" /> : <Bell className="h-4 w-4" />}{workOrders ? 'Open projects' : 'Open notifications'}<ArrowRight className="h-4 w-4" /></Link><Link className="inline-flex min-h-9 items-center gap-2 rounded-md border border-border bg-white px-3 py-2 text-sm font-semibold text-foreground hover:bg-background" to="/dashboard">Back to dashboard</Link></div></section></div>;
}
