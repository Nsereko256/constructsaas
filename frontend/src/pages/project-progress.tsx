import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { api } from '@/api/services';
import { qk } from '@/api/queryKeys';
import { ProjectProgressPanel } from '@/components/projects/project-progress-panel';
import { Skeleton } from '@/components/ui/skeleton';

export function ProjectProgressPage() {
  const { projectId = '' } = useParams();
  const project = useQuery({ queryKey: qk.project(projectId), queryFn: () => api.project(projectId) });
  if (project.isLoading) return <Skeleton className="h-[520px]" />;
  if (!project.data) throw project.error;
  return <div className="grid gap-4"><div><h2 className="text-2xl font-black">{project.data.name} progress</h2><p className="mt-1 text-sm text-muted">Close accepted sites and manage smaller measurable goals for this project.</p></div><ProjectProgressPanel project={project.data} /></div>;
}
