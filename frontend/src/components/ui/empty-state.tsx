import type React from 'react';
import { AlertCircle } from 'lucide-react';
import { Card } from './card';

export function EmptyState({ title, message, action }: { title: string; message?: string; action?: React.ReactNode }) {
  return (
    <Card className="grid min-h-40 place-items-center border-dashed p-8 text-center">
      <div>
        <AlertCircle className="mx-auto h-8 w-8 text-muted" />
        <h3 className="mt-3 font-bold">{title}</h3>
        <p className="mt-1 text-sm text-muted">{message || 'There is nothing to act on in this view yet. Adjust filters or complete the preceding workflow step.'}</p>
        {action ? <div className="mt-3 flex justify-center">{action}</div> : null}
      </div>
    </Card>
  );
}
