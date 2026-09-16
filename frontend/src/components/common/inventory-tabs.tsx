import { Boxes, ReceiptText, Route } from 'lucide-react';
import { WorkspaceTabs } from './workspace-hub';

export function InventoryTabs() {
  return <div className="ops-tabs"><WorkspaceTabs links={[
    { href: '/inventory', label: 'Stock', icon: Boxes },
    { href: '/inventory/bin-locations', label: 'Bin locations', icon: ReceiptText },
    { href: '/inventory/movements', label: 'Movements', icon: Route },
    { href: '/inventory/site-custody', label: 'Site custody', icon: ReceiptText },
  ]} /></div>;
}
