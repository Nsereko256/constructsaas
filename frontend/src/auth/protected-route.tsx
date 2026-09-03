import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './auth-context';
import { Skeleton } from '@/components/ui/skeleton';

export function ProtectedRoute() {
  const auth = useAuth();
  const location = useLocation();

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
