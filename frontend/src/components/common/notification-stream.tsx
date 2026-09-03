import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { connectSocket } from '@/api/ws';
import { qk } from '@/api/queryKeys';
import { useToast } from '@/components/ui/toast';
import { useAuth } from '@/auth/auth-context';

type NotificationSocketMessage = {
  type?: string;
  unread_count?: number;
  title?: string;
  message?: string;
  level?: 'info' | 'success' | 'warning' | 'danger';
};

export function NotificationStream() {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();

  useEffect(() => {
    if (!isAuthenticated) return undefined;
    const socket = connectSocket<NotificationSocketMessage>({
      path: '/ws/notifications/',
      onMessage: (payload) => {
        if (typeof payload.unread_count === 'number') {
          queryClient.setQueryData(qk.unreadCount, { unread_count: payload.unread_count });
        }
        if (payload.title || payload.message) {
          toast.push({
            title: payload.title || 'Notification',
            message: payload.message || '',
            tone: payload.level || 'info',
          });
          void queryClient.invalidateQueries({ queryKey: qk.notifications() });
          void queryClient.invalidateQueries({ queryKey: qk.workflowBadges });
        }
      },
    });
    return () => socket.close();
  }, [isAuthenticated, queryClient, toast]);

  return null;
}
