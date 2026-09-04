import {
  Bell,
  Boxes,
  Building2,
  Wrench,
  FileBarChart,
  Landmark,
  Home,
  MessageSquare,
  PackageCheck,
  Settings,
  ShieldCheck,
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
const financeStakeholders: Role[] = ['admin', 'project_manager', 'procurement_officer', 'finance_officer', 'finance_manager', 'finance_viewer'];

export const navItems: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: Home, roles: all, section: 'Operations' },
  { label: 'Projects', href: '/projects', icon: Building2, roles: all },
  { label: 'Procurement', href: '/procurement', icon: PackageCheck, roles: all },
  { label: 'Work orders', href: '/work-orders', icon: Wrench, roles: all, badgeKey: 'work_orders' },
  { label: 'Inventory', href: '/inventory', icon: Boxes, roles: all, badgeKey: 'inventory' },
  { label: 'Suppliers', href: '/suppliers', icon: Users, roles: ['admin', 'procurement_officer'] },
  { label: 'Messages', href: '/messages', icon: MessageSquare, roles: ['admin', 'project_manager', 'site_engineer'] },
  { label: 'Notifications', href: '/notifications', icon: Bell, roles: all },
  { label: 'Reports', href: '/reports', icon: FileBarChart, roles: reports },
  { label: 'Finance', href: '/finance', icon: Landmark, roles: financeStakeholders, section: 'Finance' },
  { label: 'Team', href: '/team', icon: ShieldCheck, roles: ['admin', 'project_manager'], section: 'Workspace' },
  { label: 'Settings', href: '/settings', icon: Settings, roles: ['admin'], section: 'Workspace' },
];

export function visibleNav(role: Role | null) {
  if (!role) return [];
  return navItems.filter((item) => item.roles.includes(role)).map((item) => ({ ...item, section: item.section || 'Operations' }));
}
