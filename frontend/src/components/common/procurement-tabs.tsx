import { WorkspaceTabs } from '@/components/common/workspace-hub';

const procurementLinks = [
  { label: 'Overview', href: '/procurement' },
  { label: 'Material requests', href: '/procurement/requests' },
  { label: 'Purchase orders', href: '/procurement/purchase-orders' },
  { label: 'Receipts', href: '/procurement/grns' },
  { label: 'Deliveries', href: '/procurement/deliveries' },
];

export function ProcurementTabs() {
  return <WorkspaceTabs links={procurementLinks} />;
}
