import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type React from 'react';
import { X } from 'lucide-react';
import { Button } from './button';

type Toast = { id: number; title: string; message?: string; tone?: 'success' | 'warning' | 'danger' | 'info' };
type ToastContextValue = { push: (toast: Omit<Toast, 'id'>) => void };

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Date.now();
    setToasts((items) => [...items, { ...toast, id }]);
    window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 5500);
  }, []);
  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-3 right-3 z-[70] grid w-[min(380px,calc(100vw-1.5rem))] gap-2 sm:bottom-4 sm:right-4">
        {toasts.map((toast) => (
          <div key={toast.id} className={`rounded-xl border bg-white p-3 shadow-panel ${toast.tone === 'danger' ? 'border-critical/35' : toast.tone === 'warning' ? 'border-warning/40' : toast.tone === 'success' ? 'border-primary/30' : 'border-border'}`} role="status">
            <div className="flex items-start justify-between gap-3">
              <div>
                <strong className="text-sm">{toast.title}</strong>
                {toast.message ? <p className="mt-1 text-sm text-muted">{toast.message}</p> : null}
              </div>
              <Button variant="ghost" size="sm" onClick={() => setToasts((items) => items.filter((item) => item.id !== toast.id))}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
