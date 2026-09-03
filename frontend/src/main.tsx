import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from '@/auth/auth-context';
import { SiteScopeProvider } from '@/context/site-scope';
import { OfflineBanner } from '@/components/common/offline-banner';
import { NotificationStream } from '@/components/common/notification-stream';
import { ToastProvider } from '@/components/ui/toast';
import { App } from './App';
import './styles/globals.css';

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    // The app is served from Django routes such as /login and /dashboard;
    // register at the origin root so the worker can control the whole SPA.
    void navigator.serviceWorker.register('/sw.js', { scope: '/' });
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnMount: 'always',
      refetchOnReconnect: 'always',
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <SiteScopeProvider>
              <NotificationStream />
              <OfflineBanner />
              <App />
            </SiteScopeProvider>
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
