import { Component, type ReactNode } from 'react';

export class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="mx-auto my-12 max-w-lg rounded-lg border bg-white p-6" role="alert">
      <h1 className="text-xl font-bold">We couldn’t display this workspace</h1>
      <p className="my-4 text-sm">Reload the page to try again. If it still won’t open, return to the dashboard.</p>
      <button className="rounded bg-primary px-4 py-3 text-white" onClick={() => window.location.reload()}>Reload page</button>
      <a className="ml-4 text-primary underline" href="/dashboard">Dashboard</a>
    </main>;
    return this.props.children;
  }
}
