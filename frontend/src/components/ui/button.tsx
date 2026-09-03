import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { LoaderCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex min-h-9 items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold shadow-sm transition-all duration-150 disabled:pointer-events-none disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-info/30 active:translate-y-px',
  {
    variants: {
      variant: {
        default: 'border-primary bg-primary text-white hover:bg-[#345F89] hover:shadow-md',
        secondary: 'border-border bg-white text-foreground hover:border-primary/30 hover:bg-[#F0F3F5] hover:shadow-md',
        ghost: 'border-transparent bg-transparent text-foreground shadow-none hover:bg-[#F0F3F5]',
        destructive: 'border-critical bg-critical text-white hover:bg-[#C83131] hover:shadow-md',
        warning: 'border-warning bg-warning text-[#201604] hover:bg-[#D38B0E] hover:shadow-md',
      },
      size: {
        sm: 'min-h-8 rounded-md px-2.5 text-xs',
        default: 'min-h-9',
        lg: 'min-h-11 px-4',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
  loadingLabel?: string;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ children, className, disabled, loading = false, loadingLabel, variant, size, asChild = false, ...props }, ref) => {
    // Radix Slot requires exactly one child. Render the composed child directly
    // so links inside buttons remain valid even when loading support exists.
    if (asChild) {
      return (
        <Slot
          aria-busy={loading || undefined}
          className={cn(buttonVariants({ variant, size }), className)}
          ref={ref}
          {...props}
        >
          {children}
        </Slot>
      );
    }
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        aria-busy={loading || undefined}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || loading}
        ref={ref}
        {...props}
      >
        {loading ? <LoaderCircle aria-hidden="true" className="h-3.5 w-3.5 animate-spin" /> : null}
        {loading && loadingLabel ? loadingLabel : children}
      </Comp>
    );
  },
);
Button.displayName = 'Button';
