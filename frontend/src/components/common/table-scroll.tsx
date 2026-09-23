import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Native touch/keyboard scrolling plus visible controls for wide registers. */
export function TableScroll({ children, className, label = 'Records' }: { children: ReactNode; className?: string; label?: string }) {
  const viewport = useRef<HTMLDivElement>(null);
  const id = useId();
  const [edges, setEdges] = useState({ overflow: false, start: true, end: true });
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const measure = () => {
      const remaining = element.scrollWidth - element.clientWidth;
      const next = { overflow: remaining > 2, start: element.scrollLeft <= 2, end: element.scrollLeft >= remaining - 2 };
      setEdges((previous) => previous.overflow === next.overflow && previous.start === next.start && previous.end === next.end ? previous : next);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (element.firstElementChild) observer.observe(element.firstElementChild);
    element.addEventListener('scroll', measure, { passive: true });
    return () => { observer.disconnect(); element.removeEventListener('scroll', measure); };
  }, [children]);
  const slide = (direction: number) => {
    const element = viewport.current;
    if (element) element.scrollBy({ left: direction * element.clientWidth * .75, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  };
  return <div className="table-scroll-shell">
    {edges.overflow ? <div className="table-scroll-tools">
      <span id={`${id}-hint`}>More columns · scroll horizontally</span>
      <div><button type="button" aria-label={`Scroll ${label.toLowerCase()} left`} aria-controls={id} disabled={edges.start} onClick={() => slide(-1)}><ArrowLeft size={16} aria-hidden="true" /></button><button type="button" aria-label={`Scroll ${label.toLowerCase()} right`} aria-controls={id} disabled={edges.end} onClick={() => slide(1)}><ArrowRight size={16} aria-hidden="true" /></button></div>
    </div> : null}
    <div ref={viewport} id={id} className={cn('table-scroll-viewport', className)} role={edges.overflow ? 'region' : undefined} aria-label={edges.overflow ? label : undefined} aria-describedby={edges.overflow ? `${id}-hint` : undefined} tabIndex={edges.overflow ? 0 : undefined}>{children}</div>
  </div>;
}
