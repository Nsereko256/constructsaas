import { Download } from 'lucide-react';
import { Button, type ButtonProps } from '@/components/ui/button';

type ExportButtonProps = Omit<ButtonProps, 'children'> & {
  label?: string;
};

/** Shared compact export action used by module pages. */
export function ExportButton({ label = 'Export', ...props }: ExportButtonProps) {
  return (
    <Button type="button" variant="ghost" size="sm" {...props}>
      <Download className="h-3.5 w-3.5" />
      {label}
    </Button>
  );
}
