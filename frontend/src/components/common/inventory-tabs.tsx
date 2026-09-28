import { Boxes, ReceiptText, Route } from 'lucide-react';
import { WorkspaceTabs } from './workspace-hub';
import { useAuth } from '@/auth/auth-context';
import { canReadExternalTransfers } from '@/api/external-transfers';

export function InventoryTabs() {
  const { role } = useAuth();
  return <div className="ops-tabs"><WorkspaceTabs links={[
    { href: '/inventory', label: 'Stock', icon: Boxes },
    ...(canReadExternalTransfers(role) ? [{ href: '/inventory/external-transfers', label: 'External transfers', icon: ReceiptText }] : []),
    { href: '/inventory/bin-locations', label: 'Bin locations', icon: ReceiptText },
    { href: '/inventory/movements', label: 'Movements', icon: Route },
  ]} /></div>;
}
