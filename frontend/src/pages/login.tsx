import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Field, inputClass } from '@/components/ui/field';
import { ApiError } from '@/api/client';

const schema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
});

type LoginForm = z.infer<typeof schema>;

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const form = useForm<LoginForm>({ resolver: zodResolver(schema), defaultValues: { username: '', password: '' } });
  const [sessionConflict, setSessionConflict] = useState<LoginForm | null>(null);

  if (auth.isAuthenticated) return <Navigate to="/dashboard" replace />;

  async function onSubmit(values: LoginForm) {
    try {
      await auth.login(values.username, values.password);
      navigate('/dashboard', { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setSessionConflict(values);
        return;
      }
      form.setError('root', { message: error instanceof Error ? error.message : 'Login failed' });
    }
  }

  async function endOtherSession() {
    if (!sessionConflict) return;
    try {
      await auth.login(sessionConflict.username, sessionConflict.password, true);
      navigate('/dashboard', { replace: true });
    } catch (error) {
      setSessionConflict(null);
      form.setError('root', { message: error instanceof Error ? error.message : 'Could not end the other session.' });
    }
  }

  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-[1fr_480px]">
      <section className="hidden bg-sidebar p-10 text-white lg:grid">
        <div className="max-w-2xl self-center">
          <div className="mb-8 inline-grid h-12 w-12 place-items-center rounded-lg bg-primary text-xl font-black">C</div>
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-white/60">ConstructSaaS</p>
          <h1 className="mt-3 text-4xl font-black tracking-tight">Construction procurement, inventory and site control in one operating system.</h1>
          <p className="mt-4 max-w-xl text-white/70">
            Built for Ugandan construction teams managing projects, materials, suppliers, approvals and field receipts across multiple sites.
          </p>
        </div>
      </section>
      <section className="grid place-items-center p-5">
        <Card className="w-full max-w-md p-6">
          <h2 className="text-2xl font-black tracking-tight">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use your company account to continue.</p>
          <form className="mt-6 grid gap-4" onSubmit={form.handleSubmit(onSubmit)}>
            <Field label="Username" required error={form.formState.errors.username?.message}>
              <input className={inputClass} autoComplete="username" {...form.register('username')} />
            </Field>
            <Field label="Password" required error={form.formState.errors.password?.message}>
              <input className={inputClass} type="password" autoComplete="current-password" {...form.register('password')} />
            </Field>
            {form.formState.errors.root ? <p className="text-sm font-semibold text-critical">{form.formState.errors.root.message}</p> : null}
            {sessionConflict ? <div className="grid gap-3 rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm"><div><strong>Already signed in elsewhere</strong><p className="mt-1 text-muted">This account has an active session on another device. Continue only if you want to sign it out there.</p></div><div className="flex flex-col gap-2 sm:flex-row"><Button type="button" onClick={() => void endOtherSession()}>Sign out other device and continue</Button><Button type="button" variant="ghost" onClick={() => setSessionConflict(null)}>Cancel</Button></div></div> : null}
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>
          <a className="mt-4 block text-sm font-semibold text-primary" href="/forgot-password">
            Forgot password?
          </a>
        </Card>
      </section>
    </main>
  );
}
