import type { JobMetadata } from './types';

const normalize = (value: string) => value.normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s+/g, ' ').trim();

export function jobFilterStates(jobs: JobMetadata[], selected: string) {
  return [...new Set([...jobs.map(job => job.state), ...(selected === 'all' ? [] : [selected])])].sort();
}

export function filterJobs(jobs: JobMetadata[], query: string, state: string, output: string) {
  const text = normalize(query);
  return jobs.filter(job => (!text || normalize(`${job.title} ${job.id}`).includes(text)) &&
    (state === 'all' || job.state === state) &&
    (output === 'all' || (output === 'unspecified' ? !job.output_kinds?.length : job.output_kinds?.includes(output))));
}

export function prioritizeActiveJob(jobs: JobMetadata[], activeId: string) {
  return [...jobs].sort((a,b) => Number(b.id === activeId) - Number(a.id === activeId));
}

export function includeOpenedJobs(current: JobMetadata[], opened: import('./types').Job[]): JobMetadata[] {
  const ids = new Set(opened.map(job => job.id));
  return [...opened.map(job => ({id:job.id,title:job.title,state:job.state,updated_at:job.updated_at,source_hash:job.source_hash,
    has_source:Boolean(job.source_packet?.body),output_kinds:Object.entries(job.selections ?? {}).filter(([,enabled])=>enabled === true).map(([kind])=>kind)})),
    ...current.filter(job => !ids.has(job.id))];
}
