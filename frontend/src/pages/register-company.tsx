import { useState } from 'react';
import type React from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { registerCompany } from '@/api/services';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Field, inputClass } from '@/components/ui/field';

export function RegisterCompanyPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ company_name: '', first_name: '', last_name: '', username: '', email: '', password: '', password_confirm: '' });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);

  function update(name: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await registerCompany(form);
      await auth.login(form.username, form.password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Company registration failed.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-[1fr_480px]">
      <section className="hidden bg-sidebar p-10 text-white lg:grid">
        <div className="max-w-2xl self-center">
          <div className="mb-8 inline-grid h-12 w-12 place-items-center rounded-lg bg-primary text-xl font-black">C</div>
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-white/60">ConstructSaaS</p>
          <h1 className="mt-3 text-4xl font-black tracking-tight">Set up your company workspace.</h1>
          <p className="mt-4 max-w-xl text-white/70">Register your company, create its first administrator, and begin managing projects, sites, materials and approvals.</p>
        </div>
      </section>
      <section className="grid place-items-center p-5">
        <Card className="w-full max-w-md p-6">
          <h2 className="text-2xl font-black tracking-tight">Register company</h2>
          <p className="mt-1 text-sm text-muted">The first account becomes the company administrator.</p>
          <form className="mt-6 grid gap-4" onSubmit={submit}>
            <Field label="Company name" required><input className={inputClass} value={form.company_name} onChange={(e) => update('company_name', e.target.value)} required /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="First name" required><input className={inputClass} value={form.first_name} onChange={(e) => update('first_name', e.target.value)} required /></Field>
              <Field label="Last name" required><input className={inputClass} value={form.last_name} onChange={(e) => update('last_name', e.target.value)} required /></Field>
            </div>
            <Field label="Administrator username" required><input className={inputClass} autoComplete="username" value={form.username} onChange={(e) => update('username', e.target.value)} required /></Field>
            <Field label="Email" required><input className={inputClass} type="email" autoComplete="email" value={form.email} onChange={(e) => update('email', e.target.value)} required /></Field>
            <Field label="Password" required><div className="relative"><input className={`${inputClass} pr-12`} type={showPassword ? 'text' : 'password'} autoComplete="new-password" value={form.password} onChange={(e) => update('password', e.target.value)} required /><button type="button" className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-foreground" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div></Field>
            <Field label="Confirm password" required><div className="relative"><input className={`${inputClass} pr-12`} type={showPasswordConfirm ? 'text' : 'password'} autoComplete="new-password" value={form.password_confirm} onChange={(e) => update('password_confirm', e.target.value)} required /><button type="button" className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-foreground" aria-label={showPasswordConfirm ? 'Hide password' : 'Show password'} onClick={() => setShowPasswordConfirm((visible) => !visible)}>{showPasswordConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div></Field>
            {error ? <p className="text-sm font-semibold text-critical">{error}</p> : null}
            <Button type="submit" disabled={submitting}>{submitting ? 'Registering...' : 'Register company'}</Button>
          </form>
          <a className="mt-4 block text-sm font-semibold text-primary" href="/login">Already registered? Sign in</a>
        </Card>
      </section>
    </main>
  );
}
