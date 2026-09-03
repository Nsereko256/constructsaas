import {
  Bell,
  Boxes,
  Building2,
  ClipboardList,
  Wrench,
  FileBarChart,
  FileWarning,
  BadgeDollarSign,
  Banknote,
  BookOpenCheck,
  CircleDollarSign,
  Landmark,
  Home,
  MessageSquare,
  PackageCheck,
  ReceiptText,
  Settings,
  ShieldCheck,
  Truck,
  PackageOpen,
  Users,
} from 'lucide-react';
import type React from 'react';
import type { Role, WorkflowBadges } from '@/api/types';

export type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: Role[];
  section?: 'Operations' | 'Finance' | 'Workspace';
  badgeKey?: keyof WorkflowBadges;
};

const all: Role[] = ['admin', 'project_manager', 'procurement_officer', 'storekeeper', 'site_engineer', 'finance_officer', 'finance_manager', 'finance_viewer'];
const reports: Role[] = ['admin', 'project_manager', 'procurement_officer'];
const finance: Role[] = ['admin', 'finance_officer', 'finance_manager', 'finance_viewer'];
const financeStakeholders: Role[] = ['admin', 'project_manager', 'procurement_officer', 'finance_officer', 'finance_manager', 'finance_viewer'];
const financeCore: Role[] = ['admin', 'finance_officer', 'finance_manager', 'finance_viewer'];

export const navItems: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: Home, roles: all, section: 'Operations' },
  { label: 'Projects', href: '/projects', icon: Building2, roles: all },
  { label: 'Project staffing', href: '/team/project-staffing', icon: Users, roles: ['admin', 'project_manager'] },
  { label: 'Requests', href: '/procurement/requests', icon: ClipboardList, roles: all, badgeKey: 'requests' },
  { label: 'Work orders', href: '/work-orders', icon: Wrench, roles: all, badgeKey: 'work_orders' },
  { label: 'Work order invoices', href: '/work-orders/invoices', icon: ReceiptText, roles: all },
  { label: 'Site progress', href: '/work-orders/progress', icon: ClipboardList, roles: ['admin', 'project_manager', 'site_engineer'] },
  { label: 'Purchase Orders', href: '/procurement/purchase-orders', icon: PackageCheck, roles: ['admin', 'project_manager', 'procurement_officer', 'storekeeper', 'site_engineer', 'finance_officer', 'finance_manager', 'finance_viewer'], badgeKey: 'purchase_orders' },
  { label: 'Goods received notes', href: '/procurement/grns', icon: ReceiptText, roles: all },
  { label: 'Supplier claims', href: '/procurement/supplier-claims', icon: FileWarning, roles: all, badgeKey: 'supplier_claims' },
  { label: 'Deliveries', href: '/procurement/deliveries', icon: Truck, roles: ['admin', 'project_manager', 'procurement_officer', 'storekeeper', 'site_engineer'], badgeKey: 'deliveries' },
  { label: 'Inventory', href: '/inventory', icon: Boxes, roles: all, badgeKey: 'inventory' },
  { label: 'Bin locations', href: '/inventory/bin-locations', icon: Boxes, roles: ['admin', 'storekeeper'] },
  { label: 'Movements', href: '/inventory/movements', icon: Truck, roles: ['admin', 'storekeeper', 'project_manager'] },
  { label: 'Site custody', href: '/inventory/site-custody', icon: PackageOpen, roles: ['admin', 'storekeeper', 'project_manager', 'site_engineer'] },
  { label: 'Suppliers', href: '/suppliers', icon: Users, roles: ['admin', 'procurement_officer'] },
  { label: 'Messages', href: '/messages', icon: MessageSquare, roles: ['admin', 'project_manager', 'site_engineer'] },
  { label: 'Notifications', href: '/notifications', icon: Bell, roles: all },
  { label: 'Reports', href: '/reports', icon: FileBarChart, roles: reports },
  { label: 'Overview', href: '/finance', icon: Landmark, roles: financeStakeholders, section: 'Finance' },
  { label: 'Budgets', href: '/finance/budgets', icon: CircleDollarSign, roles: financeStakeholders, section: 'Finance', badgeKey: 'budgets' },
  { label: 'Supplier Invoices', href: '/finance/payables', icon: BadgeDollarSign, roles: financeCore, section: 'Finance', badgeKey: 'supplier_invoices' },
  { label: 'Cash & Payments', href: '/finance/payments', icon: Banknote, roles: finance, section: 'Finance', badgeKey: 'payments' },
  { label: 'Payment batches', href: '/finance/payment-batches', icon: Banknote, roles: finance, section: 'Finance' },
  { label: 'Reconciliation', href: '/finance/reconciliation', icon: Landmark, roles: finance, section: 'Finance' },
  { label: 'Expenses & Advances', href: '/finance/expenses', icon: ClipboardList, roles: finance, section: 'Finance', badgeKey: 'expenses' },
  { label: 'Ledger', href: '/finance/ledger', icon: BookOpenCheck, roles: finance, section: 'Finance', badgeKey: 'ledger' },
  { label: 'Month end', href: '/finance/month-end', icon: BookOpenCheck, roles: finance, section: 'Finance' },
  { label: 'Finance Reports', href: '/finance/reports', icon: FileBarChart, roles: financeCore, section: 'Finance' },
  { label: 'Setup & Audit', href: '/finance/settings', icon: Settings, roles: finance, section: 'Finance' },
  { label: 'Team', href: '/team', icon: ShieldCheck, roles: ['admin', 'project_manager'], section: 'Workspace' },
  { label: 'Settings', href: '/settings', icon: Settings, roles: ['admin'], section: 'Workspace' },
];

export function visibleNav(role: Role | null) {
  if (!role) return [];
  return navItems.filter((item) => item.roles.includes(role)).map((item) => ({ ...item, section: item.section || 'Operations' }));
}
