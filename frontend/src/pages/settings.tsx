import { useAuth } from '@/auth/auth-context';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function SettingsPage() {
  const { user } = useAuth();
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Workspace</CardTitle></CardHeader>
        <CardContent className="grid gap-2 text-sm">
          <p><strong>Company:</strong> {user?.company_name}</p>
          <p><strong>Signed in as:</strong> {user?.username}</p>
          <p><strong>Role:</strong> {user?.role_display}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Frontend configuration</CardTitle></CardHeader>
        <CardContent className="grid gap-2 text-sm text-muted">
          <p>Authentication uses JWT tokens from the shared Django API.</p>
          <p>WebSockets connect to the existing notifications, dashboard and project chat consumers.</p>
          <p>Offline shell caching is enabled in production builds.</p>
        </CardContent>
      </Card>
    </div>
  );
}
