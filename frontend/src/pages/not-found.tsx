import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-background p-5">
      <Card className="max-w-lg p-8 text-center">
        <p className="text-sm font-bold uppercase tracking-[0.16em] text-muted">404</p>
        <h1 className="mt-2 text-3xl font-black">Page not found</h1>
        <p className="mt-2 text-muted">The workspace route you requested does not exist.</p>
        <Button className="mt-5" asChild>
          <Link to="/dashboard">Return to dashboard</Link>
        </Button>
      </Card>
    </main>
  );
}
