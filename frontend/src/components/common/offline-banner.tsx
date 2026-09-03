import { Cloud, ListChecks, RefreshCw, Trash2, TriangleAlert, WifiOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getTokens } from '@/api/client';
import { discardOfflineAction, offlineActions, offlineScope, retryOfflineAction, syncOfflineActions, type OfflineAction } from '@/pwa/offline';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';

export function OfflineBanner() {
  const [online, setOnline] = useState(navigator.onLine);
  const [actions, setActions] = useState<OfflineAction[]>([]);
  const [open, setOpen] = useState(false);
  const scope = offlineScope(getTokens()?.access);
  const queued = actions.length;
  const needsAttention = actions.filter((item) => item.state === 'attention').length;

  useEffect(() => {
    const update = () => { setOnline(navigator.onLine); void syncOfflineActions(scope); };
    const count = () => void offlineActions(scope).then(setActions);
    count();
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    window.addEventListener('construct-offline-change', count);
    if (navigator.onLine) void syncOfflineActions(scope);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
      window.removeEventListener('construct-offline-change', count);
    };
  }, [scope]);

  if (online && !queued) return null;
  return (
    <>
      <div className="fixed bottom-3 left-3 right-3 z-50 flex max-w-lg items-center gap-2 rounded-xl border border-warning/50 bg-white px-3 py-2 text-sm font-semibold shadow-panel sm:bottom-4 sm:left-4 sm:right-auto" role="status" aria-live="polite">
        {online ? (needsAttention ? <TriangleAlert className="h-4 w-4 text-warning" /> : <Cloud className="h-4 w-4 text-info" />) : <WifiOff className="h-4 w-4 text-warning" />}
        <span className="min-w-0 flex-1">{online ? (needsAttention ? `${needsAttention} saved action${needsAttention === 1 ? '' : 's'} need review.` : `${queued} saved action${queued === 1 ? '' : 's'} waiting to sync.`) : 'Offline: requests and receipts are saved on this device.'}</span>
        <button className="inline-flex shrink-0 items-center gap-1 text-primary" onClick={() => setOpen(true)}><ListChecks className="h-3.5 w-3.5" />Review</button>
        {online && queued && !needsAttention ? <button className="inline-flex shrink-0 items-center gap-1 text-primary" onClick={() => void syncOfflineActions(scope)}><RefreshCw className="h-3.5 w-3.5" />Sync</button> : null}
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Offline sync centre" description="Only purchase requests and goods receipts can be saved offline. Approval, payment, posting, and reversal actions always require a live connection.">
          <div className="grid gap-3">
            {!actions.length ? <p className="text-sm text-muted">There are no local actions waiting to sync.</p> : actions.map((action) => {
              const attention = action.state === 'attention';
              return <article key={action.id} className="grid gap-2 rounded-lg border border-border bg-background p-3">
                <div className="flex items-start justify-between gap-3"><div><strong className="text-sm">{action.kind === 'purchase-request' ? 'Purchase request' : 'Goods receipt'}</strong><p className="mt-0.5 text-xs text-muted">Saved {new Date(action.createdAt).toLocaleString()}</p></div><span className={attention ? 'text-xs font-bold text-warning' : 'text-xs font-bold text-info'}>{attention ? 'Needs review' : action.state === 'syncing' ? 'Syncing' : 'Queued'}</span></div>
                {attention ? <p className="text-sm text-warning">{action.error || 'The server needs this draft to be reviewed before it can be synced.'}</p> : null}
                <div className="flex flex-wrap gap-2">
                  {online && attention ? <Button size="sm" variant="secondary" onClick={() => void retryOfflineAction(action.id).then(() => syncOfflineActions(scope))}><RefreshCw className="h-4 w-4" />Retry</Button> : null}
                  <Button size="sm" variant="ghost" onClick={() => { if (window.confirm('Discard this local action? It has not been sent to the server.')) void discardOfflineAction(action.id); }}><Trash2 className="h-4 w-4" />Discard</Button>
                </div>
              </article>;
            })}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
