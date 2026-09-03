import { useState } from 'react';
import type React from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { confirmPasswordReset, requestPasswordReset } from '@/api/services';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field, inputClass } from '@/components/ui/field';

export function ForgotPasswordPage() {
  const [params] = useSearchParams();
  const uid = params.get('uid');
  const token = params.get('token');
  const isConfirmation = Boolean(uid && token);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    setMessage('');
    if (isConfirmation && password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    try {
      setSubmitting(true);
      const response = isConfirmation
        ? await confirmPasswordReset(uid as string, token as string, password)
        : await requestPasswordReset(email);
      setMessage(response.detail);
      if (isConfirmation) {
        setPassword('');
        setConfirmPassword('');
      }
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : 'Unable to process password reset.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background p-5">
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>{isConfirmation ? 'Choose a new password' : 'Password recovery'}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-5 text-sm text-muted">
            {isConfirmation
              ? 'Set a new password for your ConstructSaaS account.'
              : 'Enter your account email and we will send a one-time password-reset link.'}
          </p>
          <form className="grid gap-4" onSubmit={submit}>
            {isConfirmation ? <>
              <Field label="New password" required><div className="relative"><input className={`${inputClass} pr-12`} type={showPassword ? 'text' : 'password'} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /><button type="button" className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-foreground" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div></Field>
              <Field label="Confirm new password" required><div className="relative"><input className={`${inputClass} pr-12`} type={showConfirmPassword ? 'text' : 'password'} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /><button type="button" className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-foreground" aria-label={showConfirmPassword ? 'Hide password' : 'Show password'} onClick={() => setShowConfirmPassword((visible) => !visible)}>{showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div></Field>
            </> : <Field label="Account email" required><input className={inputClass} type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} /></Field>}
            {error ? <p className="text-sm font-semibold text-critical">{error}</p> : null}
            {message ? <p className="text-sm font-semibold text-primary">{message}</p> : null}
            <Button type="submit" disabled={submitting || (!isConfirmation && !email) || (isConfirmation && (!password || !confirmPassword))}>
              {submitting ? 'Please wait…' : isConfirmation ? 'Reset password' : 'Send reset link'}
            </Button>
          </form>
          <a className="mt-4 block text-sm font-semibold text-primary" href="/login">Back to sign in</a>
        </CardContent>
      </Card>
    </main>
  );
}
