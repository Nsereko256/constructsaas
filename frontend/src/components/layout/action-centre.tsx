import { AlertTriangle, ArrowRight, Banknote, Boxes, ClipboardCheck, ClipboardList, FileText, PackageCheck, ReceiptText, Wallet, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Role, WorkflowBadges } from '@/api/types';
import { Badge } from '@/components/ui/badge';

type QueueItem = { badge: keyof WorkflowBadges; label: string; href: string; icon: LucideIcon };

const queues: Record<Role, QueueItem[]> = {
  site_engineer: [
    { badge: 'deliveries', label: 'Site deliveries to receive', href: '/procurement/deliveries?action_queue=site_receipts', icon: ReceiptText },
    { badge: 'requests', label: 'Request follow-ups', href: '/procurement/requests?action_queue=my_requests', icon: ClipboardList },
    { badge: 'supplier_claims', label: 'Site supplier replacements', href: '/procurement/supplier-claims?action_queue=site_replacements', icon: AlertTriangle },
  ],
  storekeeper: [
    { badge: 'deliveries', label: 'Warehouse receipts', href: '/procurement/deliveries?action_queue=warehouse_receipts', icon: ReceiptText },
    { badge: 'requests', label: 'Stock issues to fulfil', href: '/procurement/requests?action_queue=my_requests', icon: ClipboardCheck },
    { badge: 'inventory', label: 'Low-stock materials', href: '/inventory', icon: AlertTriangle },
    { badge: 'supplier_claims', label: 'Supplier replacements to receive', href: '/procurement/supplier-claims?action_queue=my_claims', icon: AlertTriangle },
  ],
  project_manager: [
    { badge: 'requests', label: 'Requests awaiting manager approval', href: '/procurement/requests?action_queue=my_requests', icon: ClipboardCheck },
    { badge: 'budgets', label: 'Budgets awaiting review', href: '/finance/budgets', icon: Banknote },
  ],
  procurement_officer: [
    { badge: 'requests', label: 'Manager-approved requests to quote', href: '/procurement/requests?action_queue=my_requests', icon: ClipboardList },
    { badge: 'purchase_orders', label: 'Purchase orders to progress', href: '/procurement/purchase-orders?action_queue=po_progress', icon: PackageCheck },
    { badge: 'deliveries', label: 'Site POs to dispatch', href: '/procurement/deliveries?action_queue=site_dispatch', icon: ReceiptText },
    { badge: 'supplier_claims', label: 'Supplier claims to follow up', href: '/procurement/supplier-claims?action_queue=my_claims', icon: AlertTriangle },
  ],
  finance_officer: [
    { badge: 'requests', label: 'Finance reviews and quoted POs', href: '/procurement/requests?action_queue=my_requests', icon: ClipboardCheck },
    { badge: 'supplier_invoices', label: 'Supplier invoices to prepare', href: '/finance/payables', icon: FileText },
    { badge: 'payments', label: 'Payment drafts to prepare', href: '/finance/payments', icon: Wallet },
    { badge: 'expenses', label: 'Expense drafts to prepare', href: '/finance/expenses', icon: Banknote },
  ],
  finance_manager: [
    { badge: 'requests', label: 'Quoted PO reviews', href: '/procurement/requests?action_queue=my_requests', icon: ClipboardCheck },
    { badge: 'budgets', label: 'Budget approvals', href: '/finance/budgets', icon: Banknote },
    { badge: 'supplier_invoices', label: 'Invoice authorizations', href: '/finance/payables', icon: FileText },
    { badge: 'payments', label: 'Payment approvals / posting', href: '/finance/payments', icon: Wallet },
    { badge: 'expenses', label: 'Expense decisions', href: '/finance/expenses', icon: Banknote },
    { badge: 'ledger', label: 'Draft journals', href: '/finance/ledger', icon: ClipboardCheck },
    { badge: 'supplier_claims', label: 'Supplier claims', href: '/procurement/supplier-claims?action_queue=my_claims', icon: AlertTriangle },
  ],
  finance_viewer: [],
  admin: [
    { badge: 'requests', label: 'Purchase requests', href: '/procurement/requests', icon: ClipboardList },
    { badge: 'purchase_orders', label: 'Purchase orders', href: '/procurement/purchase-orders', icon: PackageCheck },
    { badge: 'deliveries', label: 'Warehouse receipts', href: '/procurement/deliveries?delivery_destination=WAREHOUSE', icon: ReceiptText },
    { badge: 'inventory', label: 'Low-stock materials', href: '/inventory', icon: Boxes },
    { badge: 'budgets', label: 'Budget approvals', href: '/finance/budgets', icon: Banknote },
    { badge: 'supplier_invoices', label: 'Invoice actions', href: '/finance/payables', icon: FileText },
    { badge: 'payments', label: 'Payment actions', href: '/finance/payments', icon: Wallet },
    { badge: 'expenses', label: 'Expense actions', href: '/finance/expenses', icon: Banknote },
    { badge: 'ledger', label: 'Draft journals', href: '/finance/ledger', icon: ClipboardCheck },
  ],
};

export function ActionCentre({ role, workflow }: { role: Role | null; workflow: WorkflowBadges | undefined }) {
  if (!role) return null;
  const items = queues[role].map((item) => ({ ...item, count: workflow?.[item.badge] || 0 })).filter((item) => item.count > 0);
  if (!items.length) return null;
  const total = items.reduce((sum, item) => sum + item.count, 0);

  return <section aria-label="Your required actions" className="mb-3 rounded-2xl border border-warning/30 bg-warning/5 shadow-panel sm:mb-4">
    <div className="flex items-center justify-between gap-3 border-b border-warning/20 px-3 py-2.5 sm:px-4">
      <div className="flex min-w-0 items-center gap-2"><AlertTriangle className="h-4 w-4 shrink-0 text-warning" /><div><p className="text-[10px] font-black uppercase tracking-[0.14em] text-warning">Action required</p><strong className="block text-sm">Your priority queue</strong><p className="text-xs text-muted">Open a queue to act on the records assigned to your role.</p></div></div>
      <Badge tone="warning">{total} open</Badge>
    </div>
    <div className="grid gap-2 p-2 sm:grid-cols-2 sm:p-3 xl:grid-cols-4">
      {items.slice(0, 4).map((item) => <Link key={item.badge} to={item.href} className="interactive-lift group flex min-w-0 items-center gap-2 rounded-xl border border-warning/20 bg-white px-2.5 py-2.5 text-sm shadow-sm hover:border-primary/35 hover:bg-primary/5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><item.icon className="h-4 w-4" /></span><span className="min-w-0 flex-1 truncate font-semibold">{item.label}</span><Badge tone="warning">{item.count}</Badge><ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted group-hover:text-primary" />
      </Link>)}
    </div>
  </section>;
}
