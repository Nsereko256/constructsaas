import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './auth-context';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';

export function ProtectedRoute() {
  const auth = useAuth();
  const location = useLocation();

  if (auth.sessionCheckFailed) {
    return <div className="grid min-h-screen place-items-center bg-background p-5"><div className="w-full max-w-md rounded-2xl border border-border bg-white p-6 text-center shadow-panel"><h1 className="text-lg font-black">Session check unavailable</h1><p className="mt-2 text-sm text-muted">We could not verify your session because the server or network is temporarily unavailable. Your sign-in has been kept.</p><Button className="mt-4" onClick={auth.retrySession}>Try again</Button></div></div>;
  }

  if (auth.isLoading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <div className="w-80 space-y-3">
          <Skeleton className="h-8" />
          <Skeleton className="h-24" />
        </div>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
