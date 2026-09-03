import { ArrowLeft, Search, Send, Users } from 'lucide-react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/services';
import { connectSocket } from '@/api/ws';
import { Button } from '@/components/ui/button';
import { inputClass } from '@/components/ui/field';
import { useAuth } from '@/auth/auth-context';

type LiveChatMessage = {
  id: number;
  sender: string;
  sender_id?: number | null;
  content: string;
  is_system_message: boolean;
  created_at: string;
  created_at_display?: string;
};

type ChatPayload = {
  type: 'chat.history' | 'chat.message';
  messages?: LiveChatMessage[];
  message?: LiveChatMessage;
};

function initials(value: string) {
  return value.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'P';
}

function displayTime(value: string, fallback?: string) {
  if (fallback) return fallback;
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}

function uniqueMessages(items: LiveChatMessage[]) {
  const byId = new Map<number, LiveChatMessage>();
  items.forEach((message) => byId.set(message.id, message));
  return [...byId.values()].sort((left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime());
}

export function MessagesPage() {
  const { user } = useAuth();
  const chatRooms = useQuery({ queryKey: ['chat-rooms'], queryFn: () => api.chatRooms({ page_size: 100 }) });
  const [projectId, setProjectId] = useState('');
  const [messages, setMessages] = useState<LiveChatMessage[]>([]);
  const [content, setContent] = useState('');
  const [search, setSearch] = useState('');
  const socketRef = useRef<ReturnType<typeof connectSocket> | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const activeProject = (chatRooms.data?.results || []).find((room) => String(room.project) === projectId);
  const visibleProjects = useMemo(() => (chatRooms.data?.results || []).filter((room) => room.project_name.toLowerCase().includes(search.toLowerCase())), [chatRooms.data?.results, search]);

  useEffect(() => {
    if (!projectId) return undefined;
    setMessages([]);
    let active = true;
    const socket = connectSocket<ChatPayload>({
      path: `/ws/chat/${projectId}/`,
      onMessage: (payload) => {
        if (!active) return;
        if (payload.type === 'chat.history') setMessages(uniqueMessages(payload.messages || []));
        if (payload.type === 'chat.message' && payload.message) setMessages((current) => uniqueMessages([...current, payload.message!]));
      },
    });
    socketRef.current = socket;
    return () => {
      active = false;
      socket.close();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [projectId]);

  useEffect(() => { scrollRef.current?.scrollIntoView({ block: 'end' }); }, [messages]);

  const sendNow = () => {
    if (!content.trim() || !socketRef.current) return;
    socketRef.current.send({ message: content.trim() });
    setContent('');
  };
  const send = (event: FormEvent) => { event.preventDefault(); sendNow(); };

  return <div className="overflow-hidden border border-border bg-white shadow-panel lg:grid lg:min-h-[calc(100vh-9.5rem)] lg:grid-cols-[340px_minmax(0,1fr)]">
    <aside className={projectId ? 'hidden border-r border-border lg:block' : 'border-r border-border'}>
      <div className="border-b border-border bg-background px-3 py-3"><div className="flex items-center gap-3"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary text-sm font-black text-white">{initials(user?.username || 'You')}</div><div className="min-w-0"><h1 className="font-bold">Project chats</h1><p className="truncate text-xs text-muted">Your authorised team conversations</p></div></div></div>
      <div className="border-b border-border p-2"><label className="relative block"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" /><input className={`${inputClass} w-full pl-9`} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search chats" aria-label="Search project chats" /></label></div>
      <div className="max-h-[calc(100vh-16rem)] overflow-y-auto lg:max-h-[calc(100vh-15rem)]">
        {visibleProjects.map((room) => { const active = projectId === String(room.project); return <button key={room.id} onClick={() => setProjectId(String(room.project))} className={`flex w-full items-center gap-3 border-b border-border px-3 py-3 text-left transition ${active ? 'bg-primary/10' : 'bg-white hover:bg-background'}`}><div className={`grid h-11 w-11 shrink-0 place-items-center rounded-full text-sm font-black ${active ? 'bg-primary text-white' : 'bg-primary/15 text-primary'}`}>{initials(room.project_name)}</div><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><strong className="truncate text-sm">{room.project_name}</strong></div><p className="mt-0.5 truncate text-xs text-muted">Project team conversation</p></div></button>; })}
        {!visibleProjects.length ? <div className="p-8 text-center text-sm text-muted">No project chats found.</div> : null}
      </div>
    </aside>

    <section className={`${projectId ? 'flex' : 'hidden lg:flex'} min-h-[calc(100vh-9.5rem)] flex-col bg-[#efeae2]`}>
      {activeProject ? <><header className="flex items-center gap-3 border-b border-border bg-white px-3 py-2.5 shadow-sm"><Button type="button" variant="ghost" size="sm" className="lg:hidden" onClick={() => setProjectId('')} aria-label="Back to chats"><ArrowLeft className="h-4 w-4" /></Button><div className="grid h-10 w-10 place-items-center rounded-full bg-primary/15 text-sm font-black text-primary">{initials(activeProject.project_name)}</div><div className="min-w-0"><h2 className="truncate text-sm font-bold">{activeProject.project_name}</h2><p className="text-xs text-muted">Project team chat</p></div></header>
        <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-5" style={{ backgroundImage: 'radial-gradient(rgba(62, 78, 83, .08) 1px, transparent 1px)', backgroundSize: '16px 16px' }}>
          {messages.length === 0 ? <div className="grid h-full place-items-center"><div className="max-w-xs rounded-2xl bg-white/90 p-5 text-center shadow-sm"><Users className="mx-auto h-7 w-7 text-primary" /><p className="mt-2 text-sm font-semibold">Start the project conversation</p><p className="mt-1 text-xs text-muted">Messages are shared with the authorised project team.</p></div></div> : messages.map((message) => {
            const mine = message.sender_id === user?.id;
            if (message.is_system_message) return <div key={message.id} className="my-4 text-center"><span className="rounded-full bg-[#fff8c5] px-3 py-1.5 text-[11px] text-muted shadow-sm">{message.content}</span></div>;
            return <div key={message.id} className={`mb-2 flex ${mine ? 'justify-end' : 'justify-start'}`}><article className={`max-w-[85%] rounded-2xl px-3 py-2 shadow-sm sm:max-w-[72%] ${mine ? 'rounded-br-md bg-[#d9fdd3]' : 'rounded-bl-md bg-white'}`}><div className="flex items-baseline gap-2"><strong className={`text-xs ${mine ? 'text-primary' : 'text-info'}`}>{mine ? 'You' : message.sender}</strong></div><p className="mt-0.5 whitespace-pre-wrap break-words text-sm leading-5">{message.content}</p><p className="mt-1 text-right text-[10px] text-muted">{displayTime(message.created_at, message.created_at_display)}</p></article></div>;
          })}<div ref={scrollRef} /></div>
        <form className="flex items-end gap-2 border-t border-border bg-[#f0f2f5] px-2 py-2 sm:px-3" onSubmit={send}><textarea className={`${inputClass} max-h-28 min-h-10 flex-1 resize-none rounded-full bg-white px-4 py-2`} disabled={!projectId} value={content} onChange={(event) => setContent(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendNow(); } }} placeholder="Type a message" rows={1} aria-label="Message" /><Button className="h-10 w-10 shrink-0 rounded-full p-0" aria-label="Send message" disabled={!content.trim()}><Send className="h-4 w-4" /></Button></form>
      </> : <div className="grid flex-1 place-items-center p-8 text-center"><div><Users className="mx-auto h-10 w-10 text-primary" /><h2 className="mt-3 font-bold">Select a project chat</h2><p className="mt-1 text-sm text-muted">Choose a conversation to view and send project messages.</p></div></div>}
    </section>
  </div>;
}
