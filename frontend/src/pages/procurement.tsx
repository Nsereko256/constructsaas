import { ClipboardList, FileWarning, PackageCheck, ReceiptText, Truck, Users } from 'lucide-react';
import { WorkspaceHub, WorkspaceTabs } from '@/components/common/workspace-hub';

export function ProcurementPage() {
  const links = [
      { label: 'Purchase requests', description: 'Create, approve, and follow requests through Finance review.', href: '/procurement/requests', icon: ClipboardList },
      { label: 'Supplier quotes', description: 'Collect and compare supplier pricing before raising a PO.', href: '/procurement/rfqs', icon: Users },
      { label: 'Purchase orders', description: 'Progress approved orders, amendments, dispatch, and closure.', href: '/procurement/purchase-orders', icon: PackageCheck },
      { label: 'Receipts', description: 'Record warehouse and site goods-received notes.', href: '/procurement/grns', icon: ReceiptText },
      { label: 'Deliveries', description: 'Track dispatches and handoffs to each project site.', href: '/procurement/deliveries', icon: Truck },
      { label: 'Supplier claims', description: 'Resolve shortages, damage, replacements, returns, and credits.', href: '/procurement/supplier-claims', icon: FileWarning },
    ];
  return <div className="grid gap-4"><WorkspaceTabs links={links.map(({ label, href, icon }) => ({ label, href, icon }))} /><WorkspaceHub
    eyebrow="Operations workspace"
    title="Procurement"
    description="Follow one purchasing flow from demand and supplier pricing through approval, purchase order, receipt, delivery, and claim resolution."
    links={links}
  /></div>;
}
