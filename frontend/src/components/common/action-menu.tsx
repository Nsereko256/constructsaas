import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { MoreHorizontal } from 'lucide-react';
import type { ReactNode } from 'react';

export function ActionMenu({ label, children }: { label: string; children: ReactNode }) {
  return <DropdownMenu.Root>
    <DropdownMenu.Trigger className="row-menu-trigger" aria-label={label}><MoreHorizontal size={18} /></DropdownMenu.Trigger>
    <DropdownMenu.Portal><DropdownMenu.Content className="workspace-menu" align="end" sideOffset={6}>{children}</DropdownMenu.Content></DropdownMenu.Portal>
  </DropdownMenu.Root>;
}

export function ActionMenuItem({ children, onSelect, disabled }: { children: ReactNode; onSelect: () => void; disabled?: boolean }) {
  return <DropdownMenu.Item disabled={disabled} onSelect={onSelect}>{children}</DropdownMenu.Item>;
}
